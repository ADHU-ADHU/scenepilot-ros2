"""Pluggable inference adapters. No ROS or torch import in the VLM bridge."""
import gc
import importlib
import json
import os
import time
from pathlib import Path

import cv2
import numpy as np

from .contracts import (SELECTION_SCHEMA, decode_image, encode_image, post_json,
                        validate_selection)


class OllamaVLM:
    def __init__(self, config):
        self.config = config
        self.url = config['engine_url'].rstrip('/')
        self.model = config['model']
        self.verified = False

    def ready(self):
        info = post_json(self.url+'/api/show', {'model': self.model}, timeout=10)
        if 'vision' not in info.get('capabilities', []):
            raise ValueError(f'{self.model} does not advertise vision support; refusing text-only fallback')
        self.verified = True
        return {'model': self.model, 'capabilities': info['capabilities'],
                'details': info.get('details', {})}

    def infer(self, request):
        if not self.verified:
            self.ready()
        images = request['images']
        prompt = Path(self.config['prompt_file']).read_text()
        context = '\n'.join(f'Image {i+1}: {x["camera"].upper()} camera.' for i,x in enumerate(images))
        messages = [{'role':'system', 'content':prompt}]
        messages.extend(request.get('history', []))
        messages.append({'role':'user', 'content':context+'\n'+request['query'],
                         'images':[x['data'] for x in images]})
        payload = {'model':self.model, 'messages':messages, 'stream':False,
                   'format':SELECTION_SCHEMA, 'keep_alive': self.config.get('keep_alive', '5m'),
                   'options':self.config.get('options', {'temperature':.1})}
        if 'think' in self.config:
            payload['think'] = self.config['think']
        output = post_json(self.url+'/api/chat', payload, timeout=self.config.get('engine_timeout_s',150))
        return {'selection':validate_selection(output['message']['content'], [x['camera'] for x in images]),
                'model':self.model, 'runtime_metrics':{k:v for k,v in output.items()
                if k in ('load_duration','prompt_eval_duration','eval_duration','eval_count')}}

    def unload(self):
        # An empty generation with keep_alive=0 is Ollama's unload operation.
        # An unpulled model has no residency to release.
        import urllib.error
        try:
            post_json(self.url+'/api/generate', {'model':self.model, 'keep_alive':0}, timeout=160)
        except urllib.error.HTTPError as exc:
            if exc.code != 404:
                raise
        self.verified = False


class OpenAICompatibleVLM:
    """Adapter for a separately deployed image-capable /v1/chat/completions server.

    OpenAI-compatible discovery does not standardize modalities: operator must
    explicitly declare vision_verified after testing that exact served model.
    """
    def __init__(self, config):
        self.config = config

    def ready(self):
        if not self.config.get('vision_verified', False):
            raise ValueError('Verify this exact model/server supports images; set vision_verified only after a probe')
        return {'model': self.config['model'], 'vision_verified_by_operator': True}

    def infer(self, request):
        self.ready()
        content = [{'type':'text','text': request['query']}]
        for frame in request['images']:
            content.extend([{'type':'text','text':f'{frame["camera"].upper()} CAMERA'},
                            {'type':'image_url','image_url':{'url':'data:image/jpeg;base64,'+frame['data']}}])
        messages = [{'role':'system','content':Path(self.config['prompt_file']).read_text()},
                    *request.get('history', []), {'role':'user','content':content}]
        payload = {'model':self.config['model'], 'messages':messages, **self.config.get('options', {})}
        if self.config.get('json_schema', True):
            payload['response_format'] = {'type':'json_schema','json_schema':{
                'name':'selection','strict':True,'schema':SELECTION_SCHEMA}}
        key = os.getenv(self.config.get('api_key_env', 'VLM_API_KEY'), '')
        headers = {'Authorization':'Bearer '+key} if key else {}
        output = post_json(self.config['engine_url'].rstrip('/')+'/chat/completions', payload,
                           timeout=self.config.get('engine_timeout_s',150), headers=headers)
        return {'selection':validate_selection(output['choices'][0]['message']['content'],
                                               [x['camera'] for x in request['images']]),
                'model':self.config['model']}

    def unload(self):
        endpoint = self.config.get('unload_url')
        if endpoint:
            post_json(endpoint, {'model':self.config['model']}, timeout=160)
        elif self.config.get('resource_group'):
            raise RuntimeError('This server has no standard unload API; supply unload_url or a dedicated resource group')


class SAM3:
    def __init__(self, config):
        self.config = config
        self.model = self.processor = None

    def ready(self):
        checkpoint = self.config['checkpoint']
        if not Path(checkpoint).is_file():
            raise FileNotFoundError(f'Mount the licensed SAM checkpoint at {checkpoint}')
        import torch
        if not torch.cuda.is_available():
            raise RuntimeError('CUDA unavailable to SAM container')
        return {'checkpoint':Path(checkpoint).name, 'cuda':torch.version.cuda,
                'torch':torch.__version__, 'device':torch.cuda.get_device_name(0)}

    def load(self):
        if self.model is not None:
            return
        self.ready()
        from sam3.model_builder import build_sam3_image_model
        from sam3.model.sam3_image_processor import Sam3Processor
        self.model = build_sam3_image_model(checkpoint_path=self.config['checkpoint'],
                                            load_from_HF=False, device='cuda', eval_mode=True)
        self.processor = Sam3Processor(self.model, device='cuda',
                                      resolution=self.config.get('resolution',1008),
                                      confidence_threshold=self.config.get('confidence_threshold',.5))

    def infer(self, request):
        import torch
        from PIL import Image
        self.load()
        frame = decode_image(request['image'])
        dtype = {'bfloat16':torch.bfloat16, 'float16':torch.float16}[self.config.get('precision','bfloat16')]
        with torch.inference_mode(), torch.autocast('cuda', dtype=dtype):
            state = self.processor.set_image(Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)))
            result = self.processor.set_text_prompt(state=state, prompt=request['target'])
        torch.cuda.synchronize()
        detections = []
        for mask, box, score in zip(result['masks'], result['boxes'], result['scores']):
            mask = np.squeeze(mask.detach().cpu().numpy()).astype(np.uint8)*255
            if mask.shape != frame.shape[:2]:
                mask = cv2.resize(mask, (frame.shape[1],frame.shape[0]), interpolation=cv2.INTER_NEAREST)
            detections.append({'mask':encode_image(mask), 'box':box.detach().float().cpu().tolist(),
                               'score':float(score.detach().cpu())})
        return {'detections':detections, 'camera':request['camera'], 'header':request['header'],
                'model':'sam3-image', 'identity_tracking':False}

    def unload(self):
        self.processor = self.model = None
        gc.collect()
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()


class MockVLM:
    """Deterministic integration fixture, never a substitute for model validation."""
    def __init__(self, config):
        self.config = config

    def ready(self):
        return {'mock':True}

    def unload(self):
        pass

    def infer(self, request):
        time.sleep(self.config.get('delay_s',0))
        query = request['query'].lower()
        cameras = [x['camera'] for x in request['images']]
        camera = 'rear' if 'rear' in query and 'rear' in cameras else cameras[0]
        action = 'stop_tracking' if 'stop' in query else 'track' if 'track' in query else 'describe'
        return {'selection':{'action':action, 'target':'red object' if action=='track' else '',
                             'camera':camera if action=='track' else 'none', 'reply':'Mock response'}, 'mock':True}


class MockSegmenter(MockVLM):
    def infer(self, request):
        time.sleep(self.config.get('delay_s',0))
        frame = decode_image(request['image'])
        mask = ((frame[:,:,2] > 150) & (frame[:,:,1] < 100) & (frame[:,:,0] < 100)).astype(np.uint8)*255
        detections = []
        y,x = np.nonzero(mask)
        if len(x):
            detections.append({'mask':encode_image(mask),'score':.99,
                               'box':[int(x.min()),int(y.min()),int(x.max()),int(y.max())]})
        return {'detections':detections,'camera':request['camera'],'header':request['header'],'mock':True}


def create_backend(config):
    builtins = {'ollama':OllamaVLM, 'openai_compatible':OpenAICompatibleVLM, 'sam3':SAM3,
                'mock_vlm':MockVLM, 'mock_segmentation':MockSegmenter}
    adapter = config['adapter']
    if adapter in builtins:
        return builtins[adapter](config)
    module, name = adapter.split(':',1)
    return getattr(importlib.import_module(module),name)(config)
