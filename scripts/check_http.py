#!/usr/bin/env python3
"""Small independent HTTP contract smoke check with deterministic segmentation."""
import json
import sys
import threading
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src/perception_core'))
import numpy as np
from perception_core.server import BackendService,make_server
from perception_core.contracts import post_json,encode_image,validate_response
server=make_server(BackendService('mock',{'kind':'segmentation','adapter':'mock_segmentation'}),'127.0.0.1',0)
thread=threading.Thread(target=server.serve_forever,daemon=True); thread.start()
try:
    image=np.zeros((30,40,3),np.uint8); image[10:20,15:25,2]=255
    req={'api_version':1,'kind':'segmentation','request_id':'http-smoke','generation':1,
         'camera':'rear','target':'red object','header':{'sec':42,'nanosec':7,'frame_id':'rear_optical_frame'},
         'image':encode_image(image)}
    result=validate_response(post_json(f'http://127.0.0.1:{server.server_port}/infer',req),req)
    assert len(result['detections'])==1
    print(json.dumps({'status':'passed','http_transport':True,'detections':len(result['detections'])}))
finally:
    server.shutdown(); server.server_close()
