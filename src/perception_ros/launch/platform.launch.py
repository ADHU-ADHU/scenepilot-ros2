from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument('config',default_value='/config/platform.yaml'),
        DeclareLaunchArgument('use_sim_time',default_value='false'),
        Node(package='perception_ros',executable='coordinator',output='screen',
             parameters=[{'config':LaunchConfiguration('config'),
                          'use_sim_time':LaunchConfiguration('use_sim_time')}]),
    ])
