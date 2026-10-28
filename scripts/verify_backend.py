#!/usr/bin/env python3
"""Check configured model identity/vision support; optional two-image inference probe."""
import argparse
import json
import sys
import urllib.request
import uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src/perception_core'))
import cv2
from perception_core.contracts import load_config,encode_image,post_json,validate_response

p=argparse.ArgumentParser()
p.add_argument('backend')
p.add_argument('--config',default=str(ROOT/'config/platform.yaml'))
p.add_argument('--front')
p.add_argument('--rear')
args=p.parse_args()
config=load_config(args.config)['backends'][args.backend]
with urllib.request.urlopen(config['endpoint']+'/readyz',timeout=15) as response:
    print(json.dumps(json.load(response),indent=2))
if args.front or args.rear:
    if config['kind']!='vlm': p.error('Image probe is for VLM adapters')
    images=[]
    for camera,path in [('front',args.front),('rear',args.rear)]:
        if path:
            frame=cv2.imread(path)
            if frame is None: p.error(f'Cannot decode {path}')
            images.append({'camera':camera,'header':{'sec':0,'nanosec':0,'frame_id':camera+'_optical_frame'},
                           'data':encode_image(frame,'.jpg',960)})
    req={'api_version':1,'kind':'vlm','request_id':uuid.uuid4().hex,'generation':0,
         'images':images,'query':'Describe each camera image separately.','history':[]}
    # Run with coordinator stopped: a direct probe does not acquire its GPU lease.
    print(json.dumps(validate_response(post_json(config['endpoint']+'/infer',req,timeout=180),req),indent=2))
