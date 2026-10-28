#!/usr/bin/env python3
"""Real Jazzy pub/sub + services with synthetic cameras and CPU model fixtures.

Default includes HTTP transport; --in-process-backends replaces only HTTP with
the same service dispatch method when local sockets are unavailable. Neither
mode validates learned models, GPU execution or physical camera drivers.
"""
import argparse
import json
import os
import sys
import threading
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src/perception_core'),str(ROOT/'src/perception_ros')]

import rclpy
from rclpy.executors import SingleThreadedExecutor
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import Image
from std_msgs.msg import String
from perception_core.contracts import load_config
from perception_core.server import BackendService,make_server
from perception_interfaces.msg import TrackingResult
from perception_interfaces.srv import SwitchBackend,SelectTarget
from perception_ros.coordinator import Coordinator,stamp_ns
from perception_ros.synthetic_camera import SyntheticCamera
from perception_ros.evaluator import Evaluator


def run(args):
    config_path=Path(args.config).resolve()
    config=load_config(config_path)
    services={n:BackendService(n,c) for n,c in config['backends'].items()}
    servers=[]
    nodes=[]
    executor=None
    report={'ros_distro':os.getenv('ROS_DISTRO'),'learned_models':False,
            'http_transport':not args.in_process_backends,'checks':[]}
    try:
        if not args.in_process_backends:
            from urllib.parse import urlparse
            for name,cfg in config['backends'].items():
                endpoint=urlparse(cfg['endpoint'])
                server=make_server(services[name],endpoint.hostname,endpoint.port)
                servers.append(server)
                threading.Thread(target=server.serve_forever,daemon=True).start()
        rclpy.init(args=['--ros-args','-p',f'config:={config_path}'])
        coordinator=Coordinator(); nodes.append(coordinator)
        if args.in_process_backends:
            def direct(url,payload,**kwargs):
                for name,cfg in config['backends'].items():
                    if url.startswith(cfg['endpoint']+'/'):
                        return services[name].dispatch(url[len(cfg['endpoint']):],payload)
                raise ValueError(url)
            coordinator.pool.transport=direct
        camera=SyntheticCamera(); nodes.append(camera)
        evaluator=Evaluator(); nodes.append(evaluator)
        observer=Node('smoke_observer'); nodes.append(observer)
        executor=SingleThreadedExecutor()
        for node in nodes: executor.add_node(node)
        outputs=[]; results=[]; events=[]; metrics=[]; selections=[]; frame_stamps=set()
        subs=[observer.create_subscription(Image,'/tracking/image',outputs.append,qos_profile_sensor_data),
              observer.create_subscription(String,'/perception/events',lambda m:events.append(json.loads(m.data)),100),
              observer.create_subscription(String,'/evaluation/metrics',lambda m:metrics.append(json.loads(m.data)),100),
              observer.create_subscription(String,'/sam/target',lambda m:selections.append(m.data),10)]
        for c in ('front','rear'):
            subs.append(observer.create_subscription(Image,f'/camera/{c}/image_raw',
                lambda m:frame_stamps.add((stamp_ns(m.header),m.header.frame_id)),qos_profile_sensor_data))
        for name,cfg in config['backends'].items():
            if cfg['kind']=='segmentation':
                subs.append(observer.create_subscription(TrackingResult,f'/models/{name}/result',results.append,qos_profile_sensor_data))
        query=observer.create_publisher(String,'/assistant/query',10)
        switch=observer.create_client(SwitchBackend,'/perception/switch_backend')
        target=observer.create_client(SelectTarget,'/perception/select_target')

        def until(predicate,timeout=12):
            deadline=time.monotonic()+timeout
            while time.monotonic()<deadline:
                executor.spin_once(timeout_sec=.02)
                if predicate(): return
            raise AssertionError('Timed out waiting for ROS graph condition (check DDS/network permissions)')

        def spin_for(seconds):
            end=time.monotonic()+seconds
            while time.monotonic()<end: executor.spin_once(timeout_sec=.02)

        def switch_to(kind,backend):
            request=SwitchBackend.Request(kind=kind,backend=backend)
            future=switch.call_async(request)
            until(future.done)
            assert future.result().accepted,future.result().message

        until(lambda:len(coordinator.frames)==2 and query.get_subscription_count()>0)
        query.publish(String(data='track red object in front'))
        until(lambda:any(x.active and x.detected and x.depth_valid for x in results))
        first=next(x for x in results if x.active and x.detected and x.depth_valid)
        assert first.camera=='front' and abs(first.depth_z_m-2)<.001
        assert first.header==first.mask.header
        assert (stamp_ns(first.header),first.header.frame_id) in frame_stamps
        until(lambda:any(x.get('record_type')=='tracking' for x in metrics))
        until(lambda:any(not x.active and x.backend=='mock_sam2' for x in results))
        report['checks'].append('front RGB -> VLM -> selection -> segmentation -> annotated output + depth + evaluator')

        # Switching while the selected VLM is in flight must fence its late reply.
        services['mock_vlm'].config['delay_s']=.6
        query.publish(String(data='track red object in rear'))
        until(lambda:services['mock_vlm'].lock.locked())
        switch_to('vlm','mock_vlm2')
        until(lambda:any(e['event']=='stale_result_discarded' for e in events))
        assert coordinator.state.camera=='front'
        query.publish(String(data='track red object in rear'))
        until(lambda:any(x.active and x.camera=='rear' for x in results))
        report['checks'].append('in-flight VLM switch rejects stale result; new backend selects rear')

        switch_to('segmentation','mock_sam2')
        until(lambda:any(x.active and x.backend=='mock_sam2' for x in results))
        report['checks'].append('segmentation backend switch + isolated comparison outputs')

        coordinator.config['cameras']['rear']['depth_enabled']=False
        previous=len(results)
        until(lambda:any(x.active and not x.depth_valid for x in results[previous:]))
        report['checks'].append('RGB-only segmentation continues with depth disabled')
        coordinator.config['cameras']['rear']['depth_enabled']=True

        # Fail actual backend execution once, verify retry and recovery.
        adapter=services['mock_sam2'].backend
        original=adapter.infer
        failures=[1]
        def fail_once(req):
            if failures[0]:
                failures[0]=0
                raise RuntimeError('injected transient model failure')
            return original(req)
        adapter.infer=fail_once
        previous=len(results)
        until(lambda:any(e['event']=='backend_error' for e in events))
        until(lambda:len(results)>previous+3)
        report['checks'].append('backend error is reported and following frames recover')

        stop=SelectTarget.Request(camera='rear',target='',stop=True)
        future=target.call_async(stop); until(future.done)
        assert future.result().accepted and not coordinator.state.target
        spin_for(.7)
        before=len(results); spin_for(.5)
        assert len(results)==before
        report['checks'].append('atomic stop rejects in-flight segmentation and stops new masks')
        assert outputs and any(x.mask.data for x in results) and '__STOP__' in selections
        report.update(status='passed',tracking_results=len(results),output_frames=len(outputs),metrics=len(metrics))
    except Exception as exc:
        report.update(status='failed',error=type(exc).__name__+': '+str(exc))
        raise
    finally:
        if executor: executor.shutdown(timeout_sec=1)
        for node in reversed(nodes): node.destroy_node()
        if rclpy.ok(): rclpy.shutdown()
        for server in servers:
            server.shutdown(); server.server_close()
        Path(args.report).parent.mkdir(parents=True,exist_ok=True)
        Path(args.report).write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps(report,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--config',default=str(ROOT/'config/mock.yaml'))
    parser.add_argument('--in-process-backends',action='store_true')
    parser.add_argument('--report',default=str(ROOT/'artifacts/ros-smoke.json'))
    run(parser.parse_args())
