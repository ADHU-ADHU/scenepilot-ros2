from setuptools import find_packages, setup

package_name = 'scene_camera'

setup(
    name=package_name,
    version='0.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='Adhithya Palanisamy Chandrasekaran',
    maintainer_email='130308572+ADHU-ADHU@users.noreply.github.com',
    description='Configurable front and rear camera publishers for ScenePilot',
    license='TODO: License declaration',
    extras_require={
        'test': [
            'pytest',
        ],
    },
   entry_points={
    'console_scripts': [
        'camera_node = scene_camera.camera_node:main',
    ],
 },
)
