import pytest
from perception_core.backends import OllamaVLM,OpenAICompatibleVLM
from perception_core.contracts import load_config
from test_contracts_and_quality import request,ROOT


def test_ollama_requires_actual_vision_capability(monkeypatch):
    config=load_config(ROOT/'config/platform.yaml')['backends']['qwen4']
    monkeypatch.setattr('perception_core.backends.post_json',lambda *a,**k:{'capabilities':['completion']})
    with pytest.raises(ValueError,match='vision'): OllamaVLM(config).infer(request())


def test_ollama_multiimage_prompt_schema_and_settings(monkeypatch):
    config=load_config(ROOT/'config/platform.yaml')['backends']['qwen4']
    calls=[]
    def post(url,payload,**kwargs):
        calls.append((url,payload))
        if url.endswith('/show'): return {'capabilities':['completion','vision']}
        return {'message':{'content':'{"action":"track","target":"red object","camera":"rear","reply":"OK"}'}}
    monkeypatch.setattr('perception_core.backends.post_json',post)
    req=request(); req['images'].insert(0,{**req['images'][0],'camera':'front'})
    result=OllamaVLM(config).infer(req)
    payload=calls[-1][1]
    assert len(payload['messages'][-1]['images'])==2
    assert 'Image 2: REAR' in payload['messages'][-1]['content']
    assert payload['format']['required']==['action','target','camera','reply']
    assert payload['options']['num_ctx']==4096 and payload['model']==config['model']
    assert result['selection']['camera']=='rear'


def test_external_vision_and_unload_are_explicit():
    backend=OpenAICompatibleVLM({'model':'unknown','vision_verified':False,'resource_group':'gpu'})
    with pytest.raises(ValueError): backend.ready()
    with pytest.raises(RuntimeError): backend.unload()
