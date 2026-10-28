import copy
import numpy as np
import pytest
from perception_core.contracts import (validate_selection,validate_response,load_config,
                                      encode_image,decode_image)
from perception_core.quality import QualityTracker,depth_estimate
from perception_core.server import BackendService
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def request(kind='vlm'):
    frame=np.zeros((64,80,3),np.uint8)
    frame[20:40,30:50,2]=255
    header={'sec':10,'nanosec':123,'frame_id':'rear_optical_frame'}
    value={'api_version':1,'kind':kind,'request_id':'unique','generation':3}
    if kind=='vlm':
        value.update(query='track the red object in rear',images=[{'camera':'rear','header':header,'data':encode_image(frame)}])
    else:
        value.update(camera='rear',header=header,image=encode_image(frame),target='red object')
    return value


def test_rgb_vlm_mask_contract_roundtrip():
    vlm=BackendService('vlm',{'kind':'vlm','adapter':'mock_vlm'})
    sam=BackendService('sam',{'kind':'segmentation','adapter':'mock_segmentation'})
    choice=vlm.dispatch('/infer',request())['selection']
    assert choice['action']=='track' and choice['camera']=='rear'
    req=request('segmentation'); req['target']=choice['target']
    result=sam.dispatch('/infer',req)
    assert result['header']==req['header']
    assert decode_image(result['detections'][0]['mask'],True).sum()==400*255
    for field,bad in [('request_id','wrong'),('generation',2),('header',{})]:
        changed=copy.deepcopy(result); changed[field]=bad
        with pytest.raises(ValueError): validate_response(changed,req)


@pytest.mark.parametrize('value',[
    {'action':'track','camera':'front','target':'person','reply':'OK'},
    {'action':'track','camera':'rear','target':'','reply':'OK'},
    {'action':'delete','camera':'rear','target':'person','reply':'OK'},
    {'action':'chat','camera':'none','target':'person','reply':'OK'},
    {'action':'track','camera':'rear','target':15,'reply':'OK'},
])
def test_reject_invalid_model_output(value):
    with pytest.raises(ValueError): validate_selection(value,['rear'])


def test_depth_uses_units_calibration_and_rejects_invalid_pixels():
    mask=np.ones((10,10),np.uint8)
    depth=np.full((10,10),2000,np.uint16); depth[0]=0
    k=[100.,0.,4.5,0.,100.,4.5,0.,0.,1.]
    a=depth_estimate(mask,depth,'16UC1',k)
    b=depth_estimate(mask,depth.astype(np.float32)/1000,'32FC1',k)
    assert a==b and a['z_m']==2 and a['mad_m']==0 and a['valid_fraction']==.9
    assert a['point'][0]==pytest.approx(0)
    with pytest.raises(ValueError): depth_estimate(mask,depth[:2],'16UC1',k)
    with pytest.raises(ValueError): depth_estimate(mask,depth,'8UC1',k)
    with pytest.raises(ValueError): depth_estimate(mask,depth,'16UC1',[0.]*9)
    assert depth_estimate(mask,np.zeros((10,10)),'32FC1',k) is None


def test_quality_proxies_do_not_cross_camera_generation_or_clock_reset():
    q=QualityTracker(); m=np.ones((4,4),bool)
    key=('run',1,'sam','front','person')
    assert q.update(key,10**9,m,True)['mask_iou_proxy'] is None
    assert q.update(key,2*10**9,m,True)['mask_iou_proxy']==1.
    lost=q.update(key,3*10**9,m*False,False)
    assert lost['loss_event'] and lost['mask_iou_proxy'] is None
    assert q.update(key,4*10**9,m,True)['reacquisition_event']
    assert q.update(key,10,m,True)['time_reset']
    assert q.update(('run',2,'sam','rear','person'),20,m,True)['mask_iou_proxy'] is None


def test_configuration_and_prompt_resolution():
    config=load_config(ROOT/'config/platform.yaml')
    assert Path(config['backends']['qwen4']['prompt_file']).is_file()
    assert config['resource_groups']['laptop_gpu']['mode']=='serial'
    assert len(load_config(ROOT/'config/mock.yaml')['backends'])==4
