from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    actions=[]
    for camera,device in (('front','/dev/video0'),('rear','/dev/video2')):
        actions.append(DeclareLaunchArgument(camera+'_device',default_value=device))
        actions.append(DeclareLaunchArgument(camera+'_topic',default_value=f'/camera/{camera}/image_raw'))
        actions.append(Node(package='scene_camera',executable='camera_node',name=camera+'_camera',
            parameters=[{'device':LaunchConfiguration(camera+'_device'),
                         'topic':LaunchConfiguration(camera+'_topic'),
                         'frame_id':camera+'_optical_frame','fps':10.0}],output='screen'))
    return LaunchDescription(actions)
