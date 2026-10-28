"""Explicit test fixture: red object with aligned constant 2 m depth."""
import cv2
import numpy as np
import rclpy
from cv_bridge import CvBridge
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import Image, CameraInfo


class SyntheticCamera(Node):
    def __init__(self):
        super().__init__('synthetic_camera')
        self.bridge=CvBridge()
        self.pubs={}
        for c in ('front','rear'):
            self.pubs[c]=[self.create_publisher(t,f'/camera/{c}/{topic}',qos_profile_sensor_data)
                          for t,topic in ((Image,'image_raw'),(Image,'depth/aligned'),(CameraInfo,'camera_info'))]
        self.create_timer(.1,self.tick)

    def tick(self):
        for c,pubs in self.pubs.items():
            image=np.zeros((240,320,3),np.uint8)
            cv2.rectangle(image,(100,70),(160,150),(0,0,255),-1)
            msg=self.bridge.cv2_to_imgmsg(image,'bgr8')
            msg.header.stamp=self.get_clock().now().to_msg()
            msg.header.frame_id=c+'_optical_frame'
            depth=self.bridge.cv2_to_imgmsg(np.full((240,320),2000,np.uint16),'16UC1')
            depth.header=msg.header
            info=CameraInfo()
            info.header=msg.header
            info.width=320; info.height=240
            info.distortion_model='plumb_bob'
            info.d=[0.]*5
            info.k=[300.,0.,160.,0.,300.,120.,0.,0.,1.]
            info.r=[1.,0.,0.,0.,1.,0.,0.,0.,1.]
            info.p=[300.,0.,160.,0.,0.,300.,120.,0.,0.,0.,1.,0.]
            for pub,value in zip(pubs,(msg,depth,info)): pub.publish(value)


def main(args=None):
    rclpy.init(args=args)
    node=SyntheticCamera()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok(): rclpy.shutdown()
