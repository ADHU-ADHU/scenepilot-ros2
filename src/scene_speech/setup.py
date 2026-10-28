from setuptools import find_packages, setup

package_name = 'scene_speech'

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
    description='CPU speech transcription for ScenePilot perception commands',
    license='TODO: License declaration',
    extras_require={
        'test': [
            'pytest',
        ],
    },
   entry_points={
    'console_scripts': [
        'stt_node = scene_speech.stt_node:main',
    ],
 },
)
