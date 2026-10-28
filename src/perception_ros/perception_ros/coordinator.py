"""Jazzy ROS bridge: immutable frames, bounded workers, atomic selection commits."""
import copy
import json
import time
import uuid
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from queue import SimpleQueue

import cv2
import numpy as np
import rclpy
from cv_bridge import CvBridge
from geometry_msgs.msg import PointStamped
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data, QoSProfile, DurabilityPolicy
from rclpy.time import Time
from sensor_msgs.msg import Image, CameraInfo
from std_msgs.msg import String
from tf2_ros import Buffer, TransformListener
from tf2_geometry_msgs import do_transform_point

from perception_core.contracts import API_VERSION, load_config, encode_image, decode_image
from perception_core.state import SelectionState, BackendPool, Ticket, StaleRequest
from perception_core.quality import depth_estimate
from perception_interfaces.msg import Selection, TrackingResult
from perception_interfaces.srv import SwitchBackend, SelectTarget
from scene_interfaces.msg import VisionCommand


def header_dict(header):
    return {'sec':header.stamp.sec,'nanosec':header.stamp.nanosec,'frame_id':header.frame_id}


def stamp_ns(header):
    return header.stamp.sec*10**9+header.stamp.nanosec


class Coordinator(Node):
    def __init__(self):
        super().__init__('perception_coordinator')
        self.declare_parameter('config', '/config/platform.yaml')
        self.config=load_config(self.get_parameter('config').value)
        self.state=SelectionState(self.config['active'])
        self.session=uuid.uuid4().hex
        self.pool=BackendPool(self.config)
        self.bridge=CvBridge()
        self.frames={}
        self.depth={c:deque(maxlen=30) for c in ('front','rear')}
        self.calibration={}
        self.history=[]
        self.pending=None
        self.busy=set()
        self.last_frame={}
        self.last_failure={}
        self.results=SimpleQueue()
        self.executor_pool=ThreadPoolExecutor(max_workers=max(2,len(self.config['backends'])))
        self.last_clock=None
        self.tf_buffer=Buffer()
        self.tf_listener=TransformListener(self.tf_buffer,self)
        self.topics=self.config['topics']
        self.subscriptions_keep=[]
        self.image_pub=self.create_publisher(Image,self.topics['tracking'],qos_profile_sensor_data)
        self.reply_pub=self.create_publisher(String,self.topics['reply'],10)
        self.target_pub=self.create_publisher(String,self.topics['target'],10)
        self.camera_pub=self.create_publisher(String,self.topics['camera'],10)
        state_qos=QoSProfile(depth=1,durability=DurabilityPolicy.TRANSIENT_LOCAL)
        self.selection_pub=self.create_publisher(Selection,'/perception/selection',state_qos)
        self.status_pub=self.create_publisher(String,'/perception/status',state_qos)
        self.event_pub=self.create_publisher(String,'/perception/events',100)
        self.result_pubs={}
        self.compare_pubs={}
        for name, cfg in self.config['backends'].items():
            if cfg['kind']=='segmentation':
                self.result_pubs[name]=self.create_publisher(TrackingResult,f'/models/{name}/result',qos_profile_sensor_data)
            else:
                self.compare_pubs[name]=self.create_publisher(String,f'/models/{name}/selection',10)
        for camera in ('front','rear'):
            cfg=self.config['cameras'][camera]
            self.subscriptions_keep.append(self.create_subscription(Image,cfg['rgb'],partial(self.on_frame,camera),qos_profile_sensor_data))
            if cfg.get('depth_enabled',False):
                self.subscriptions_keep.append(self.create_subscription(Image,cfg['depth'],partial(self.on_depth,camera),qos_profile_sensor_data))
                self.subscriptions_keep.append(self.create_subscription(CameraInfo,cfg['camera_info'],partial(self.on_info,camera),qos_profile_sensor_data))
        for topic in (self.topics['query'],self.topics['speech']):
            self.subscriptions_keep.append(self.create_subscription(String,topic,self.on_query,10))
        # /sam/* remain compatibility outputs. Separate manual inputs prevent
        # command echo loops: Jazzy MessageInfo does not expose a publisher GID.
        self.subscriptions_keep.append(self.create_subscription(String,
            '/perception/input/target',self.legacy_target,10))
        self.subscriptions_keep.append(self.create_subscription(String,
            '/perception/input/camera',self.legacy_camera,10))
        self.subscriptions_keep.append(self.create_subscription(VisionCommand,'/vision/command',self.legacy_vision,10))
        self.create_service(SwitchBackend,'/perception/switch_backend',self.switch_backend)
        self.create_service(SelectTarget,'/perception/select_target',self.select_target)
        self.create_timer(.02,self.drain)
        self.create_timer(1/max(.1,self.config.get('inference_hz',5)),self.schedule)
        self.create_timer(1,self.publish_status)
        self.publish_status()

    def event(self, event_type, **data):
        self.event_pub.publish(String(data=json.dumps({'event':event_type,'session_id':self.session,
            'generation':self.state.generation,'wall_time_ns':time.time_ns(),**data},allow_nan=False)))

    def reply(self, text):
        self.reply_pub.publish(String(data=text))

    def publish_status(self):
        with self.state.lock:
            value={'session_id':self.session,'generation':self.state.generation,
                   'active':self.state.active,'camera':self.state.camera,'target':self.state.target,
                   'busy':sorted(self.busy),'backends':list(self.config['backends'])}
        self.status_pub.publish(String(data=json.dumps(value)))

    def on_frame(self, camera, msg):
        try:
            frame=self.bridge.imgmsg_to_cv2(msg,'bgr8').copy()
            self.frames[camera]=(frame,copy.deepcopy(msg.header))
            if not self.state.target and camera==self.state.camera:
                self.image_pub.publish(msg)
        except Exception as exc:
            self.event('image_error',camera=camera,error=str(exc))

    def on_depth(self, camera, msg):
        self.depth[camera].append(msg)

    def on_info(self, camera, msg):
        self.calibration[camera]=msg

    def on_query(self, msg):
        query=msg.data.strip()
        if not query:
            return
        if query.lower() in ('stop','stop tracking','__stop__'):
            self.set_target(self.state.camera,'')
            self.reply('Tracking stopped.')
            return
        frames=self.fresh_frames()
        if not frames:
            self.reply('No recent camera image is available.')
            return
        self.state.advance()
        self.pending=(query,frames,self.state.generation,copy.deepcopy(self.history))
        self.publish_status()

    def fresh_frames(self):
        now=self.get_clock().now().nanoseconds
        age=self.config.get('max_frame_age_s',2)*1e9
        return {c:(f.copy(),copy.deepcopy(h)) for c,(f,h) in self.frames.items()
                if 0 <= now-stamp_ns(h) <= age}

    def legacy_target(self, msg):
        value=msg.data.strip()
        if value:
            self.set_target(self.state.camera,'' if value=='__STOP__' else value)

    def legacy_camera(self, msg):
        if msg.data in ('front','rear'):
            self.set_target(msg.data,self.state.target)

    def legacy_vision(self, msg):
        if msg.action=='track':
            self.set_target(self.state.camera,msg.target)
        elif msg.action=='stop_tracking':
            self.set_target(self.state.camera,'')
        if msg.reply:
            self.reply(msg.reply)

    def set_target(self, camera, target, advance=True, backend='manual', request_id='', source_header=None):
        if camera not in ('front','rear') or len(target)>256:
            raise ValueError('Invalid camera or target')
        with self.state.lock:
            if advance:
                self.state.advance()
            self.state.camera=camera
            self.state.target=target
            self.pending=None
            self.last_frame.clear()
            selection=Selection()
            if source_header is not None:
                selection.header=copy.deepcopy(source_header)
            elif camera in self.frames:
                selection.header=copy.deepcopy(self.frames[camera][1])
            else:
                selection.header.stamp=self.get_clock().now().to_msg()
            selection.session_id=self.session
            selection.request_id=request_id
            selection.generation=self.state.generation
            selection.backend=backend
            selection.action='track' if target else 'stop_tracking'
            selection.camera=camera
            selection.target=target
            self.selection_pub.publish(selection)
            self.camera_pub.publish(String(data=camera))
            self.target_pub.publish(String(data=target or '__STOP__'))
        self.publish_status()

    def select_target(self, request, response):
        try:
            self.set_target(request.camera or self.state.camera,'' if request.stop else request.target)
            response.accepted=True
            response.message='Selection applied atomically'
        except ValueError as exc:
            response.message=str(exc)
        response.generation=self.state.generation
        return response

    def switch_backend(self, request, response):
        cfg=self.config['backends'].get(request.backend)
        if request.kind not in ('vlm','segmentation') or not cfg or cfg['kind']!=request.kind:
            response.accepted=False
            response.message='Unknown backend or kind'
        else:
            self.state.switch(request.kind,request.backend)
            self.pending=None
            self.history=[]
            self.last_frame.clear()
            response.accepted=True
            response.message='Route selected; readiness is checked on inference. Old requests are fenced.'
            self.event('backend_switched',kind=request.kind,backend=request.backend)
            self.publish_status()
        response.generation=self.state.generation
        return response

    def submit(self, name, request, context, shadow):
        ticket=Ticket(request['generation'],name,request['kind'])
        self.busy.add(name)
        def work():
            started=time.perf_counter()
            try:
                result=self.pool.invoke(name,request,lambda:self.state.valid(ticket,shadow))
                self.results.put((ticket,result,context,shadow,(time.perf_counter()-started)*1000,None))
            except Exception as exc:
                self.results.put((ticket,None,context,shadow,(time.perf_counter()-started)*1000,exc))
        self.executor_pool.submit(work)

    def schedule(self):
        now=self.get_clock().now().nanoseconds
        if self.last_clock is not None and now < self.last_clock:
            self.state.advance()
            self.frames.clear()
            for values in self.depth.values(): values.clear()
            self.pending=None
            self.history=[]
            self.last_frame.clear()
            self.event('clock_reset')
        self.last_clock=now
        if self.pending:
            query,frames,generation,history=self.pending
            active=self.state.active['vlm']
            if active not in self.busy:
                self.pending=None
                images=[{'camera':c,'header':header_dict(h),'data':encode_image(f,'.jpg',
                    self.config.get('vlm_max_width',960),self.config.get('jpeg_quality',85))}
                    for c,(f,h) in frames.items()]
                request={'api_version':API_VERSION,'kind':'vlm','request_id':uuid.uuid4().hex,
                         'generation':generation,'query':query,'history':history,'images':images}
                names=[active]+[n for n in self.config.get('comparison',{}).get('vlm',[]) if n!=active]
                for name in names:
                    if name not in self.busy:
                        self.submit(name,request,{'query':query,'frames':frames},name!=active)
        # Freeze segmentation scheduling while the active VLM is selecting a new
        # target. Existing work was invalidated at query acceptance.
        if self.pending or self.state.active['vlm'] in self.busy:
            return
        if not self.state.target:
            return
        camera=self.state.camera
        frame=self.fresh_frames().get(camera)
        if frame is None:
            return
        image,header=frame
        active=self.state.active['segmentation']
        names=[active]+[n for n in self.config.get('comparison',{}).get('segmentation',[]) if n!=active]
        frame_key=(self.state.generation,stamp_ns(header),header.frame_id,camera)
        for name in names:
            if name in self.busy or self.last_frame.get(name)==frame_key:
                continue
            if time.monotonic()-self.last_failure.get(name,0)<self.config.get('retry_backoff_s',2):
                continue
            self.last_frame[name]=frame_key
            request={'api_version':API_VERSION,'kind':'segmentation','request_id':uuid.uuid4().hex,
                     'generation':self.state.generation,'target':self.state.target,'camera':camera,
                     'header':header_dict(header),'image':encode_image(image)}
            self.submit(name,request,{'image':image,'header':header,'target':self.state.target,
                'camera':camera,'depth':self.match_depth(camera,header)},name!=active)

    def match_depth(self, camera, header):
        cfg=self.config['cameras'][camera]
        info=self.calibration.get(camera)
        values=list(self.depth[camera])
        if not cfg.get('depth_enabled') or not cfg.get('depth_registered') or not info or not values:
            return None
        depth=min(values,key=lambda d:abs(stamp_ns(d.header)-stamp_ns(header)))
        offset=(stamp_ns(depth.header)-stamp_ns(header))/1e6
        if abs(offset)>cfg.get('sync_slop_ms',50):
            return None
        if depth.header.frame_id!=header.frame_id or info.header.frame_id!=header.frame_id:
            return None
        if (info.width,info.height)!=(depth.width,depth.height) or any(abs(d)>1e-9 for d in info.d):
            return None  # Require rectified aligned input; do not invent calibration.
        if stamp_ns(info.header) and abs(stamp_ns(info.header)-stamp_ns(header))>cfg.get('calibration_max_age_s',30)*1e9:
            return None
        return depth,info,offset

    def drain(self):
        while not self.results.empty():
            ticket,result,context,shadow,elapsed,error=self.results.get()
            self.busy.discard(ticket.backend)
            if not self.state.valid(ticket,shadow):
                self.event('stale_result_discarded',backend=ticket.backend)
                continue
            if error:
                if not isinstance(error,StaleRequest):
                    self.last_failure[ticket.backend]=time.monotonic()
                    self.last_frame.pop(ticket.backend,None)
                    self.event('backend_error',backend=ticket.backend,error=str(error))
                    if ticket.kind=='vlm' and not shadow: self.reply(f'Vision backend failed: {error}')
                continue
            try:
                if ticket.kind=='vlm':
                    self.compare_pubs[ticket.backend].publish(String(data=json.dumps(result)))
                    if not shadow:
                        value=result['selection']
                        if value['action']=='track':
                            age=(self.get_clock().now().nanoseconds-stamp_ns(context['frames'][value['camera']][1]))/1e9
                            if not 0<=age<=self.config.get('max_selection_age_s',120):
                                raise ValueError('VLM selected from an expired frame; issue a new query')
                        self.history.extend([{'role':'user','content':context['query']},
                                             {'role':'assistant','content':json.dumps(value)}])
                        limit=max(0,int(self.config.get('history_messages',8)))
                        self.history=self.history[-limit:] if limit else []
                        if value['action']=='track':
                            self.set_target(value['camera'],value['target'],advance=False,
                                            backend=ticket.backend,request_id=result['request_id'],
                                            source_header=context['frames'][value['camera']][1])
                        elif value['action']=='stop_tracking':
                            self.set_target(self.state.camera,'',advance=False,backend=ticket.backend,
                                            request_id=result['request_id'])
                        self.reply(value['reply'] or 'Done.')
                    self.event('vlm_completed',backend=ticket.backend,request_id=result['request_id'],
                               request_ms=elapsed,inference_ms=result['inference_ms'],shadow=shadow)
                else:
                    self.publish_tracking(ticket,result,context,shadow,elapsed)
            except Exception as exc:
                self.event('invalid_backend_result',backend=ticket.backend,error=str(exc))

    def publish_tracking(self,ticket,result,context,shadow,elapsed):
        frame=context['image']
        display=frame.copy()
        mask=np.zeros(frame.shape[:2],np.uint8)
        detections=sorted(result['detections'],key=lambda d:d['score'],reverse=True)
        for i,detection in enumerate(detections):
            current=decode_image(detection['mask'],True)
            if current.shape!=frame.shape[:2]:
                raise ValueError('Backend mask resolution differs from source RGB')
            if i==0: mask=current
            selected=current>0
            display[selected]=(display[selected]*.55+np.array([0,220,80])*.45).astype(np.uint8)
            box=detection['box']
            if len(box)!=4 or not np.isfinite(box).all(): raise ValueError('Invalid box')
            x1,y1,x2,y2=map(int,box)
            cv2.rectangle(display,(x1,y1),(x2,y2),(0,255,0),2)
        cv2.putText(display,f'{context["camera"]} | {context["target"]} | {ticket.backend} | {len(detections)}',
                    (10,25),cv2.FONT_HERSHEY_SIMPLEX,.55,(255,255,255),1,cv2.LINE_AA)
        msg=TrackingResult()
        msg.header=context['header']
        msg.session_id=self.session
        msg.request_id=result['request_id']
        msg.generation=ticket.generation
        msg.backend=ticket.backend
        msg.camera=context['camera']
        msg.target=context['target']
        msg.active=not shadow
        msg.detected=bool(detections)
        msg.detections=len(detections)
        msg.mask=self.bridge.cv2_to_imgmsg(mask,'mono8')
        msg.mask.header=msg.header
        msg.confidence=float(detections[0]['score']) if detections else 0.
        msg.inference_ms=float(result['inference_ms'])
        msg.request_ms=elapsed
        delta=(self.get_clock().now().nanoseconds-stamp_ns(msg.header))/1e6
        msg.frame_age_valid=delta>=0
        msg.frame_age_ms=delta if delta>=0 else 0.
        if context['depth'] is not None and detections:
            try:
                depth,info,offset=context['depth']
                estimate=depth_estimate(mask,self.bridge.imgmsg_to_cv2(depth,'passthrough'),depth.encoding,info.k)
                if estimate:
                    msg.depth_valid=True
                    msg.depth_z_m=estimate['z_m']
                    msg.depth_range_m=estimate['range_m']
                    msg.depth_mad_m=estimate['mad_m']
                    msg.depth_valid_fraction=estimate['valid_fraction']
                    msg.depth_offset_ms=offset
                    point=PointStamped()
                    point.header=msg.header
                    point.point.x,point.point.y,point.point.z=estimate['point']
                    target_frame=self.config.get('output_frame','')
                    if target_frame and target_frame!=point.header.frame_id:
                        try:
                            transform=self.tf_buffer.lookup_transform(target_frame,point.header.frame_id,
                                                                      Time.from_msg(point.header.stamp))
                            point=do_transform_point(point,transform)
                            point.header.stamp=msg.header.stamp
                        except Exception:
                            self.event('transform_unavailable',frame=target_frame)
                    msg.position=point  # Header explicitly states optical or transformed frame.
            except Exception as exc:
                self.event("depth_unavailable",error=str(exc),camera=context["camera"])
        self.result_pubs[ticket.backend].publish(msg)
        if not shadow:
            output=self.bridge.cv2_to_imgmsg(display,'bgr8')
            output.header=msg.header
            self.image_pub.publish(output)

    def destroy_node(self):
        self.state.advance()
        self.executor_pool.shutdown(wait=False,cancel_futures=True)
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node=Coordinator()
    try:
        rclpy.spin(node)  # Single ROS executor serializes commits, switch services and input callbacks.
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok(): rclpy.shutdown()
