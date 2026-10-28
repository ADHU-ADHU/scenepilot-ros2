#!/usr/bin/env python3
"""Create a reproducible synthetic Jazzy bag; no camera/GPU/network required."""
import argparse
from pathlib import Path
import numpy as np
from cv_bridge import CvBridge
from rclpy.serialization import serialize_message
from sensor_msgs.msg import CameraInfo
from std_msgs.msg import String
import rosbag2_py

p=argparse.ArgumentParser()
p.add_argument('output')
args=p.parse_args()
if Path(args.output).exists(): p.error('Output must not already exist')
writer=rosbag2_py.SequentialWriter()
writer.open(rosbag2_py.StorageOptions(uri=args.output,storage_id='sqlite3'),
            rosbag2_py.ConverterOptions('',''))
topic_id=0
def topic(name,type_name):
    global topic_id
    writer.create_topic(rosbag2_py.TopicMetadata(id=topic_id,name=name,type=type_name,serialization_format='cdr'))
    topic_id+=1
for camera in ('front','rear'):
    topic(f'/camera/{camera}/image_raw','sensor_msgs/msg/Image')
    topic(f'/camera/{camera}/depth/aligned','sensor_msgs/msg/Image')
    topic(f'/camera/{camera}/camera_info','sensor_msgs/msg/CameraInfo')
topic('/assistant/query','std_msgs/msg/String')
bridge=CvBridge()
for i in range(60):
    stamp=100_000_000_000+i*100_000_000
    for camera in ('front','rear'):
        rgb=np.zeros((120,160,3),np.uint8)
        if not 20<=i<25: rgb[35:75,50:80,2]=255
        image=bridge.cv2_to_imgmsg(rgb,'bgr8')
        image.header.stamp.sec=stamp//10**9; image.header.stamp.nanosec=stamp%10**9
        image.header.frame_id=camera+'_optical_frame'
        depth=bridge.cv2_to_imgmsg(np.full((120,160),2000,np.uint16),'16UC1')
        depth.header=image.header
        info=CameraInfo(); info.header=image.header; info.width=160; info.height=120
        info.distortion_model='plumb_bob'; info.d=[0.]*5
        info.k=[150.,0.,80.,0.,150.,60.,0.,0.,1.]
        info.r=[1.,0.,0.,0.,1.,0.,0.,0.,1.]
        info.p=[150.,0.,80.,0.,0.,150.,60.,0.,0.,0.,1.,0.]
        for suffix,value in [('image_raw',image),('depth/aligned',depth),('camera_info',info)]:
            writer.write(f'/camera/{camera}/{suffix}',serialize_message(value),stamp)
    if i in (5,35,55):
        query={5:'track red object in front',35:'track red object in rear',55:'stop tracking'}[i]
        writer.write('/assistant/query',serialize_message(String(data=query)),stamp+1_000_000)
writer.close()
print(args.output)
