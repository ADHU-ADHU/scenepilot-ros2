import threading
from concurrent.futures import ThreadPoolExecutor
import pytest
from perception_core.state import SelectionState,Ticket,BackendPool,StaleRequest
from perception_core.server import BackendService
from test_contracts_and_quality import request


def test_switch_and_new_command_fence_old_results():
    state=SelectionState({'vlm':'a','segmentation':'sam'})
    old=Ticket(state.generation,'a','vlm')
    assert state.valid(old)
    state.switch('vlm','b')
    assert not state.valid(old) and not state.valid(old,shadow=True)
    current=Ticket(state.generation,'b','vlm')
    assert state.valid(current)
    state.advance()
    assert not state.valid(current)


def test_busy_model_cannot_be_unloaded_or_overlapped():
    service=BackendService('sam',{'kind':'segmentation','adapter':'mock_segmentation'})
    started=threading.Event(); release=threading.Event()
    original=service.backend.infer
    def delayed(req):
        started.set(); assert release.wait(2)
        return original(req)
    service.backend.infer=delayed
    with ThreadPoolExecutor() as workers:
        future=workers.submit(service.dispatch,'/infer',request('segmentation'))
        assert started.wait(2)
        with pytest.raises(BlockingIOError): service.dispatch('/unload',{})
        with pytest.raises(BlockingIOError): service.dispatch('/infer',request('segmentation'))
        release.set(); assert future.result()['detections']
    assert service.dispatch('/unload',{})['unloaded']


def test_error_does_not_leave_backend_busy_and_next_call_recovers():
    service=BackendService('vlm',{'kind':'vlm','adapter':'mock_vlm'})
    original=service.backend.infer
    def fail(req): raise RuntimeError('simulated model crash')
    service.backend.infer=fail
    with pytest.raises(RuntimeError): service.dispatch('/infer',request())
    service.backend.infer=original
    assert service.dispatch('/infer',request())['selection']['action']=='track'


def test_timeout_cannot_admit_another_gpu_model_until_unload_acknowledged():
    config={'backends':{n:{'kind':'vlm','endpoint':n,'resource_group':'gpu'} for n in ('a','b')},
            'resource_groups':{'gpu':{'mode':'serial'}}}
    calls=[]; timeout=False; busy=False
    def transport(url,payload,timeout=1):
        calls.append(url)
        if url=='a/infer': raise TimeoutError('upstream still running')
        if url=='a/unload' and busy: raise BlockingIOError('upstream busy')
        if url.endswith('/unload'): return {'unloaded':True}
        return BackendService('b',{'kind':'vlm','adapter':'mock_vlm'}).dispatch('/infer',payload)
    pool=BackendPool(config,transport)
    with pytest.raises(TimeoutError): pool.invoke('a',request())
    busy=True
    with pytest.raises(BlockingIOError): pool.invoke('b',request())
    assert 'b/infer' not in calls
    busy=False
    assert pool.invoke('b',request())['selection']['action']=='track'
    assert calls[-2:]==['a/unload','b/infer']


def test_queued_request_is_cancelled_before_backend_call_after_switch():
    state=SelectionState({'vlm':'a','segmentation':'s'})
    config={'backends':{'a':{'kind':'vlm','endpoint':'a','resource_group':'gpu'}},
            'resource_groups':{'gpu':{'mode':'serial'}}}
    calls=[]
    pool=BackendPool(config,lambda *a,**k:calls.append(a))
    ticket=Ticket(0,'a','vlm')
    pool.locks['gpu'].acquire()
    with ThreadPoolExecutor() as workers:
        future=workers.submit(pool.invoke,'a',request(),lambda:state.valid(ticket))
        state.advance(); pool.locks['gpu'].release()
        with pytest.raises(StaleRequest): future.result()
    assert not calls


def test_independent_resource_groups_allow_concurrent_comparison():
    barrier=threading.Barrier(2)
    config={'backends':{n:{'kind':'vlm','endpoint':n,'resource_group':n} for n in ('a','b')},
            'resource_groups':{n:{'mode':'parallel'} for n in ('a','b')}}
    def transport(url,payload,**kwargs):
        barrier.wait(timeout=2)
        return BackendService(url.split('/')[0],{'kind':'vlm','adapter':'mock_vlm'}).dispatch('/infer',payload)
    pool=BackendPool(config,transport)
    with ThreadPoolExecutor() as workers:
        futures=[workers.submit(pool.invoke,n,request()) for n in ('a','b')]
        assert all(f.result()['selection']['action']=='track' for f in futures)
