from setuptools import setup, find_packages
from glob import glob
setup(name='perception_ros',version='0.1.0',packages=find_packages(),
 data_files=[('share/ament_index/resource_index/packages',['resource/perception_ros']),
 ('share/perception_ros',['package.xml']),('share/perception_ros/launch',glob('launch/*.launch.py'))],
 install_requires=['setuptools'],zip_safe=True,entry_points={'console_scripts':['coordinator = perception_ros.coordinator:main', 'evaluator = perception_ros.evaluator:main', 'synthetic_camera = perception_ros.synthetic_camera:main']})
