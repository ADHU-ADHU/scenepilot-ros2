from setuptools import setup, find_packages
from glob import glob
setup(name='perception_core',version='0.1.0',packages=find_packages(),
 data_files=[('share/ament_index/resource_index/packages',['resource/perception_core']),
 ('share/perception_core',['package.xml']),('share/perception_core/launch',glob('launch/*.launch.py'))],
 install_requires=['setuptools'],zip_safe=True,entry_points={'console_scripts':['backend_server = perception_core.server:main']})
