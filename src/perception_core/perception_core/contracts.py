"""Versioned JSON contracts shared by ROS bridges and model servers (no ROS imports)."""
import base64
import json
import math
import os
import re
import urllib.request
from pathlib import Path

import cv2
import numpy as np
import yaml

API_VERSION = 1
ACTIONS = ('track', 'stop_tracking', 'describe', 'chat')
SELECTION_SCHEMA = {
    'type': 'object', 'additionalProperties': False,
    'properties': {
        'action': {'type': 'string', 'enum': list(ACTIONS)},
        'target': {'type': 'string'},
        'camera': {'type': 'string', 'enum': ['front', 'rear', 'both', 'none']},
        'reply': {'type': 'string'},
    }, 'required': ['action', 'target', 'camera', 'reply'],
}


def load_config(path):
    text = os.path.expandvars(open(path, encoding='utf8').read())
    if re.search(r'\$\{[^}]+\}', text):
        raise ValueError('Unresolved environment variable in configuration')
    config = yaml.safe_load(text)
    if set(config['active']) != {'vlm','segmentation'}:
        raise ValueError('Configure active VLM and segmentation backends')
    for group in config.get('resource_groups', {}).values():
        if group.get('mode') not in ('serial','parallel'):
            raise ValueError('Resource group mode must be serial or parallel')
    for name, backend in config['backends'].items():
        if not re.fullmatch(r'[a-z][a-z0-9_]*', name):
            raise ValueError(f'Invalid ROS backend namespace: {name}')
        if backend['kind'] not in ('vlm', 'segmentation'):
            raise ValueError(f'Invalid backend kind: {name}')
        if 'prompt_file' in backend and not Path(backend['prompt_file']).is_absolute():
            backend['prompt_file'] = str(Path(path).resolve().parent/backend['prompt_file'])
        if backend.get('resource_group') not in (None, *config.get('resource_groups', {})):
            raise ValueError(f'Unknown resource group for {name}')
    for kind, name in config['active'].items():
        if config['backends'][name]['kind'] != kind:
            raise ValueError(f'Wrong kind for active backend: {name}')
    for kind, names in config.get('comparison', {}).items():
        for name in names:
            if config['backends'][name]['kind'] != kind:
                raise ValueError(f'Wrong comparison kind: {name}')
    return config


def post_json(url, data, timeout=120, headers=None):
    request = urllib.request.Request(url, data=json.dumps(data, allow_nan=False).encode(),
                                     headers={'Content-Type': 'application/json', **(headers or {})})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


def encode_image(image, extension='.png', max_width=None, quality=85):
    if max_width and image.shape[1] > max_width:
        scale = max_width / image.shape[1]
        image = cv2.resize(image, (max_width, max(1, round(image.shape[0]*scale))))
    params = [cv2.IMWRITE_JPEG_QUALITY, quality] if extension == '.jpg' else []
    ok, data = cv2.imencode(extension, image, params)
    if not ok:
        raise ValueError('Image encoding failed')
    return base64.b64encode(data).decode('ascii')


def decode_image(data, grayscale=False):
    raw = base64.b64decode(data, validate=True)
    image = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8),
                         cv2.IMREAD_GRAYSCALE if grayscale else cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError('Invalid encoded image')
    return image


def validate_selection(value, cameras):
    if isinstance(value, str):
        value = value.strip()
        if value.startswith('```'):
            value = '\n'.join(value.splitlines()[1:-1])
        value = json.loads(value)
    if not isinstance(value, dict) or any(not isinstance(value.get(k), str)
                                         for k in SELECTION_SCHEMA['required']):
        raise ValueError('Selection must contain action, target, camera, reply strings')
    value = {k: value[k].strip() for k in SELECTION_SCHEMA['required']}
    if value['action'] not in ACTIONS or value['camera'] not in ('front','rear','both','none'):
        raise ValueError('Invalid action or camera')
    if value['action'] == 'track':
        if not value['target'] or len(value['target']) > 256 or value['camera'] not in cameras:
            raise ValueError('Tracking requires a target and an available camera')
    elif value['target']:
        raise ValueError('Only track may set a target')
    return value


def validate_request(value, kind):
    if value.get('api_version') != API_VERSION or value.get('kind') != kind:
        raise ValueError('API version or backend kind mismatch')
    if not isinstance(value.get('request_id'), str) or not value['request_id']:
        raise ValueError('Missing request identity')
    if not isinstance(value.get('generation'), int) or value['generation'] < 0:
        raise ValueError('Invalid generation')
    if kind == 'vlm':
        if not value.get('images') or not isinstance(value.get('query'), str):
            raise ValueError('VLM needs images and query')
        for frame in value['images']:
            if frame['camera'] not in ('front','rear'):
                raise ValueError('Unknown camera')
    else:
        if not value.get('target') or value.get('camera') not in ('front','rear'):
            raise ValueError('Segmentation needs camera and target')


def validate_response(response, request):
    for key in ('api_version', 'request_id', 'generation', 'kind'):
        if response.get(key) != request[key]:
            raise ValueError(f'Backend response identity mismatch: {key}')
    ms = response.get('inference_ms')
    if not isinstance(ms, (int,float)) or not math.isfinite(ms) or ms < 0:
        raise ValueError('Invalid inference duration')
    if request['kind'] == 'vlm':
        response['selection'] = validate_selection(response['selection'],
                                                   [i['camera'] for i in request['images']])
    else:
        if response.get('camera') != request['camera'] or response.get('header') != request['header']:
            raise ValueError('Segmentation changed frame identity')
        for detection in response['detections']:
            score = detection['score']
            if not isinstance(score, (float,int)) or not math.isfinite(score) or not 0 <= score <= 1:
                raise ValueError('Invalid detection score')
    return response
