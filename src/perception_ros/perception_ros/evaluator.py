"""Separate ROS quality observer; writes one JSONL record per processed mask."""
import json
import os
import time
from pathlib import Path

import rclpy
from cv_bridge import CvBridge
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from std_msgs.msg import String
from perception_interfaces.msg import TrackingResult
from perception_core.contracts import load_config
from perception_core.quality import QualityTracker


class Evaluator(Node):
    def __init__(self):
        super().__init__('perception_evaluator')
        self.declare_parameter('config','/config/platform.yaml')
        config=load_config(self.get_parameter('config').value)
        directory=Path(os.getenv('EVALUATION_DIR',config.get('evaluation_dir','/data/evaluation')))
        directory.mkdir(parents=True,exist_ok=True)
        self.output=(directory/f'metrics-{time.time_ns()}.jsonl').open('w',buffering=1)
        self.bridge=CvBridge()
        self.tracker=QualityTracker()
        self.arrivals={}
        self.publisher=self.create_publisher(String,'/evaluation/metrics',100)
        self.subs=[]
        for name,cfg in config['backends'].items():
            if cfg['kind']=='segmentation':
                self.subs.append(self.create_subscription(TrackingResult,f'/models/{name}/result',self.on_result,qos_profile_sensor_data))
        self.event_sub=self.create_subscription(String,'/perception/events',self.on_event,100)

    def write(self,value):
        line=json.dumps(value,allow_nan=False)
        self.output.write(line+'\n')
        self.publisher.publish(String(data=line))

    def on_event(self,msg):
        try:
            self.write({'record_type':'event',**json.loads(msg.data)})
        except ValueError:
            pass

    def on_result(self,msg):
        key=(msg.session_id,msg.generation,msg.backend,msg.camera,msg.target)
        stamp=msg.header.stamp.sec*10**9+msg.header.stamp.nanosec
        mask=self.bridge.imgmsg_to_cv2(msg.mask,'mono8')>0
        quality=self.tracker.update(key,stamp,mask,msg.detected,msg.depth_z_m if msg.depth_valid else None)
        now=time.monotonic()
        prior=self.arrivals.get(key)
        self.arrivals[key]=now
        self.write({'record_type':'tracking','session_id':msg.session_id,'generation':msg.generation,
            'backend':msg.backend,'camera':msg.camera,'target':msg.target,'request_id':msg.request_id,
            'stamp_ns':stamp,'frame_id':msg.header.frame_id,'active':msg.active,
            'detected':msg.detected,'detections':msg.detections,'confidence':float(msg.confidence),
            'processing_rate_hz':1/(now-prior) if prior and now>prior else None,
            'inference_ms':msg.inference_ms,'request_ms':msg.request_ms,
            'frame_age_ms':msg.frame_age_ms if msg.frame_age_valid else None,
            'clock':'simulation' if self.get_parameter('use_sim_time').value else 'ROS system time',
            'depth_z_m':msg.depth_z_m if msg.depth_valid else None,
            'depth_mad_m':msg.depth_mad_m if msg.depth_valid else None,
            'depth_offset_ms':msg.depth_offset_ms if msg.depth_valid else None,
            'depth_valid_fraction':msg.depth_valid_fraction if msg.depth_valid else None,
            'quality_is_accuracy':False,**quality})
        # Bound memory for long optimization runs with many generations.
        if len(self.arrivals)>128:
            oldest=next(iter(self.arrivals))
            self.arrivals.pop(oldest,None)
            self.tracker.previous.pop(oldest,None)

    def destroy_node(self):
        self.output.close()
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node=Evaluator()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok(): rclpy.shutdown()
