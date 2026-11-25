"""공통 실행 계약 검사. 실제 모델 학습·가중치 다운로드·승인 원장 변경은 하지 않는다."""
import json
import os
from pathlib import Path
import subprocess
import sys

import psutil
import pytest

from test_team_data_release import release_data
from test_team_data_release_v2 import v2_data
from mv_analysis.experiments.contracts import atomic_json, digest, file_sha256
from mv_analysis.training import runner
from mv_analysis.training.settings import model_settings, select_models, read_json, python_path, verify_sources
from mv_analysis.training.preflight import validate_data_release, probe_environment, check_model
from mv_analysis.training.state import (CONTRACT_VERSION, RunStore, register_checkpoint,
    validate_checkpoint, latest_checkpoint, code_fingerprint)
from mv_analysis.training.worker import validate_request


def request_for(tmp_path, mode='smoke'):
    cfg=model_settings('retinanet')
    return dict(contract_version=CONTRACT_VERSION,model_key='retinanet',mode=mode,settings=cfg,
        settings_sha256=digest(cfg),data_sha256=digest('test data'),environment_sha256=digest('test env'),
        data_kind='SYNTHETIC' if mode=='smoke' else 'REAL',code_sha256=code_fingerprint(),
        attempt_id='fixture',job_dir=str(tmp_path),resume_checkpoint=None,device='cpu')


def test_profiles_and_task_contract():
    assert select_models('owner')==['efficientad_s','retinanet','yolo11']
    assert select_models('teammate')==['rtdetrv2','uniad','hvq_trans']
    for key in select_models('owner')+select_models('teammate'):
        c=model_settings(key)
        assert c['annotation_policy']=='defect_only'
        assert c['image_policy']==('approved_crop' if c['model_family']=='anomaly' else 'original_full')


@pytest.mark.parametrize('profile,models',[(None,None),('owner',['yolo11']),('unknown',None),(None,['yolo11','yolo11']),(None,['bad'])])
def test_invalid_selection(profile,models):
    with pytest.raises(ValueError):select_models(profile,models)


@pytest.mark.parametrize('override',[{'batch_size':True},{'epochs':0},{'learning_rate':float('nan')},
    {'workers':-1},{'gradient_accumulation':1.5},{'mixed_precision':'false'},
    {'weights_sha256':'bad'},{'source_config':'../outside'},{'unknown':1},{'categories':['toy','toy']},
    {'step_size':[22,16]},{'benchmark_repetitions':1}])
def test_invalid_settings(override):
    with pytest.raises(ValueError):model_settings('retinanet',override)


def test_anomaly_rejects_d2_and_configs_are_independent():
    with pytest.raises(ValueError):model_settings('uniad',{'annotation_policy':'product_and_defect'})
    a=model_settings('retinanet',{'batch_size':4});b=model_settings('retinanet')
    assert a['batch_size']==4 and b['batch_size']==1


@pytest.mark.parametrize('text',['{"x":1,"x":2}','{"x":NaN}','{"x":Infinity}'])
def test_strict_json(tmp_path,text):
    p=tmp_path/'bad.json';p.write_text(text)
    with pytest.raises(ValueError):read_json(p)


def test_python_symlink_not_resolved(tmp_path,monkeypatch):
    p=tmp_path/'venv/bin/python';p.parent.mkdir(parents=True);p.symlink_to(sys.executable)
    monkeypatch.setenv('MV_PYTHON_RETINANET',str(p))
    assert python_path('retinanet')==p
    assert runner.worker_command(p,'request with space.json','response.json')[0]==str(p)


def test_v2_archive_and_directory_validation(v2_data):
    root,raw,_,_,build=v2_data
    before=file_sha256(root/'manifests/canonical.csv')
    d=validate_data_release(root,raw)
    z=validate_data_release(build['archive']['path'],raw,build['archive']['sha256'])
    assert d['bindings_sha256']==z['bindings_sha256']
    assert d['images']==35 and d['source_access']['decoding']=='NOT_CHECKED'
    assert d['source_access']['sample_count']==1
    assert file_sha256(root/'manifests/canonical.csv')==before


def test_release_hash_wrong_version_missing_data(v2_data):
    root,raw,_,old,build=v2_data
    with pytest.raises(ValueError):validate_data_release(old,raw)
    with pytest.raises(ValueError):validate_data_release(build['archive']['path'],raw,'0'*64)
    with pytest.raises(FileNotFoundError):validate_data_release(root,raw/'missing')


def test_release_tampering_rejected(v2_data):
    root,raw,*_=v2_data
    (root/'README_DATA.md').write_text('changed synthetic fixture')
    with pytest.raises(ValueError):validate_data_release(root,raw)


def test_source_snapshot_hashes(tmp_path):
    c=model_settings('uniad',{'source_dir':str(tmp_path/'source')});(tmp_path/'source').mkdir()
    f=tmp_path/'source/model.py';f.write_text('# synthetic source integrity test')
    atomic_json(tmp_path/'manifest.json',dict(repo='zhiyuanyou/UniAD',commit=c['official_commit'],
        files=[{'path':'model.py','sha256':file_sha256(f)}]))
    assert verify_sources(c)['files']==1
    f.write_text('tampered')
    with pytest.raises(ValueError):verify_sources(c)


def test_probe_current_python_and_missing_executable(tmp_path):
    env=probe_environment(sys.executable,'cpu')
    assert env['cpu_tensor_ok'] and env['resolved_device']=='cpu'
    with pytest.raises(FileNotFoundError):probe_environment(tmp_path/'missing')


def test_cuda_unavailable_is_not_cpu_success(monkeypatch):
    def fake(*a,**kw):
        return subprocess.CompletedProcess(a,0,json.dumps({'errors':[],'cuda_available':False,'gpu_names':[]}),'')
    monkeypatch.setattr('mv_analysis.training.preflight.subprocess.run',fake)
    with pytest.raises(ValueError,match='CUDA'):probe_environment(sys.executable,'cuda')


def test_owner_cpu_policy_and_teammate_backend_block(tmp_path,monkeypatch):
    monkeypatch.setattr('mv_analysis.training.preflight.probe_environment',lambda *a:{'resolved_device':'cpu','packages':{'torchvision':'0.29.2'}})
    c=check_model(model_settings('retinanet'),sys.executable,'cpu',tmp_path,mode='train')
    assert 'TRAIN_BACKEND_NOT_IMPLEMENTED' not in c['blockers']
    assert 'CPU_FULL_TRAINING_DISABLED' not in c['blockers']
    other=check_model(model_settings('uniad'),sys.executable,'cpu',tmp_path,mode='train')
    assert 'TRAIN_BACKEND_NOT_IMPLEMENTED' in other['blockers']
    assert 'CPU_FULL_TRAINING_DISABLED' in other['blockers']


def test_run_collision_immutable_plan_and_lock(tmp_path):
    a=RunStore.create(tmp_path,{'models':['retinanet']});b=RunStore.create(tmp_path,{'models':['retinanet']})
    assert a.path!=b.path
    with a.lock():
        with pytest.raises(RuntimeError,match='already executing'):
            with RunStore(a.path).lock():pass
    p=read_json(a.path/'plan.json');p['models']=['yolo11'];atomic_json(a.path/'plan.json',p)
    with pytest.raises(ValueError,match='modified'):RunStore(a.path)


def test_checkpoint_resume_and_corruption(tmp_path):
    req=request_for(tmp_path);p=tmp_path/'checkpoint.json';p.write_text('{"SYNTHETIC":true}')
    ref=register_checkpoint(tmp_path,p,req,epoch=0,global_step=0,state_fields=['synthetic'])
    assert latest_checkpoint(tmp_path)==str(ref)
    assert validate_checkpoint(tmp_path,ref,req)['completed_epochs']==0
    for key in ('settings_sha256','data_sha256','environment_sha256','data_kind','model_key'):
        with pytest.raises(ValueError):validate_checkpoint(tmp_path,ref,req|{key:'changed'})
    p.write_text('corrupt')
    with pytest.raises(ValueError,match='integrity'):validate_checkpoint(tmp_path,ref,req)


def test_checkpoint_real_state_requirements_and_escape(tmp_path):
    job=tmp_path/'job';job.mkdir();p=job/'state.bin';p.write_bytes(b'not actual weights')
    req=request_for(job,'train')
    with pytest.raises(ValueError,match='requires'):register_checkpoint(job,p,req,epoch=1,global_step=5,state_fields=['model'])
    fields=['model','optimizer','scheduler','rng','sampler','scaler','best_validation','progress']
    ref=register_checkpoint(job,p,req,epoch=1,global_step=5,state_fields=fields)
    assert validate_checkpoint(job,ref,req)['global_step']==5
    outer=tmp_path/'outside';outer.write_bytes(b'x');link=job/'link';link.symlink_to(outer)
    with pytest.raises(ValueError):register_checkpoint(job,link,req,epoch=0,global_step=0,state_fields=fields)


def test_request_and_response_contract(tmp_path):
    req=request_for(tmp_path);validate_request(req)
    with pytest.raises(ValueError):validate_request(req|{'data_kind':'REAL'})
    with pytest.raises(ValueError):validate_request(req|{'settings_sha256':'changed'})
    p=tmp_path/'request.json';atomic_json(p,req)
    result=dict(model_key='retinanet',request_sha256=file_sha256(p),status='COMPLETED',training_executed=True)
    with pytest.raises(ValueError):runner.check_response(result,req,p,0)
    with pytest.raises(ValueError):runner.check_response(result|{'request_sha256':'stale'},req,p,0)


def test_subprocess_logs_failure_and_timeout(tmp_path):
    code=runner.execute_worker([sys.executable,'-c','print("synthetic error");raise SystemExit(7)'],tmp_path/'failed.log')
    assert code==7 and 'synthetic error' in (tmp_path/'failed.log').read_text()
    other=tmp_path/'second';other.mkdir()
    with pytest.raises(subprocess.TimeoutExpired):
        runner.execute_worker([sys.executable,'-c','import time;time.sleep(5)'],other/'timeout.log',timeout=.05)
    assert not read_json(other/'worker_lease.json')['active']


def test_live_orphan_worker_prevents_resume(tmp_path):
    store=RunStore.create(tmp_path,{'models':['retinanet']});attempt=store.path/'retinanet/attempt_test';attempt.mkdir(parents=True)
    process=psutil.Process()
    atomic_json(attempt/'worker_lease.json',dict(active=True,pid=process.pid,create_time=process.create_time()))
    with pytest.raises(RuntimeError,match='still alive'):runner.assert_no_live_worker(store)


def stub_preflight(*a,**kw):
    return {'blockers':[], 'status':'VERIFIED','environment':{'identity_sha256':digest('synthetic env'),'resolved_device':'cpu'}}


def test_order_continue_error_resume_skip_and_new_attempts(tmp_path,monkeypatch):
    calls=[]
    monkeypatch.setattr(runner,'check_model',stub_preflight)
    def worker(command,log,**kw):
        req=read_json(command[-3]);calls.append(req['model_key'])
        status='FAILED' if req['model_key']=='retinanet' and calls.count('retinanet')==1 else 'SMOKE_PASSED'
        atomic_json(command[-1],dict(status=status,model_key=req['model_key'],training_executed=False,
                                   request_sha256=file_sha256(command[-3])))
        return 1 if status=='FAILED' else 0
    monkeypatch.setattr(runner,'execute_worker',worker)
    args=runner.parser().parse_args(['--profile','owner','--smoke','--continue-on-error','--output-root',str(tmp_path)])
    store=runner.run(args)
    assert calls==['efficientad_s','retinanet','yolo11'] and store.state['status']=='FAILED'
    resumed=runner.run(runner.parser().parse_args(['--resume',str(store.path)]))
    assert calls==['efficientad_s','retinanet','yolo11','retinanet']
    assert resumed.state['status']=='SMOKE_PASSED'
    assert len(resumed.state['jobs']['retinanet']['attempts'])==2
    with pytest.raises(ValueError):runner.run(runner.parser().parse_args(['--resume',str(store.path),'--device','cuda']))


def test_stop_on_error_and_stale_running_recovery(tmp_path,monkeypatch):
    monkeypatch.setattr(runner,'check_model',lambda *a,**kw:{'blockers':['synthetic unavailable']})
    args=runner.parser().parse_args(['--profile','owner','--smoke','--output-root',str(tmp_path)])
    store=runner.run(args)
    assert store.state['jobs']['retinanet']['status']=='PENDING'
    store.state['status']='RUNNING';store.state['jobs']['efficientad_s']['status']='RUNNING';store.save()
    resumed=runner.run(runner.parser().parse_args(['--resume',str(store.path)]))
    assert resumed.state['jobs']['efficientad_s']['attempts'][0]['status']=='INTERRUPTED'
    assert resumed.state['status']=='BLOCKED'


def test_missing_release_is_recorded_not_success(tmp_path):
    args=runner.parser().parse_args(['--profile','owner','--dry-run','--output-root',str(tmp_path)])
    store=runner.run(args)
    assert store.state['status']=='BLOCKED' and 'release' in store.state['last_error']
    assert 'PREPARATION_ERROR' in (store.path/'events.jsonl').read_text()


def test_cpu_smoke_rejects_gpu_claim(tmp_path):
    args=runner.parser().parse_args(['--models','retinanet','--smoke','--device','cuda','--output-root',str(tmp_path)])
    with pytest.raises(ValueError,match='CPU-only'):runner.run(args)


def test_changed_runner_code_rejects_resume(tmp_path,monkeypatch):
    store=RunStore.create(tmp_path,{'models':['retinanet']})
    monkeypatch.setattr('mv_analysis.training.state.code_fingerprint',lambda:'changed')
    with pytest.raises(ValueError,match='code changed'):RunStore(store.path)


@pytest.mark.parametrize('budget',['0','-1','nan','inf'])
def test_invalid_budget(tmp_path,budget):
    args=runner.parser().parse_args(['--models','retinanet','--smoke','--max-hours',budget,'--output-root',str(tmp_path)])
    with pytest.raises(ValueError,match='finite and positive'):runner.run(args)


def test_budget_preserves_pending_jobs(tmp_path):
    args=runner.parser().parse_args(['--profile','owner','--smoke','--max-hours','0.0000000001','--output-root',str(tmp_path)])
    store=runner.run(args)
    assert store.state['status']=='PARTIAL'
    assert all(j['status']=='PENDING' for j in store.state['jobs'].values())


def test_full_worker_smoke_and_checkpoint_resume(tmp_path):
    request=request_for(tmp_path);p=tmp_path/'request.json';atomic_json(p,request)
    out=tmp_path/'response.json'
    code=runner.execute_worker(runner.worker_command(sys.executable,p,out),tmp_path/'worker.log',timeout=60)
    result=runner.check_response(read_json(out),request,p,code)
    assert result['status']=='SMOKE_PASSED' and not result['official_model_executed']
    assert Path(result['report']).exists()
    assert validate_checkpoint(tmp_path,result['checkpoint_reference'],request)['global_step']==0
    # 모델 파라미터가 아닌 합성 상태만 재개해 참조 계약을 실제 별도 프로세스에서 검사한다.
    req2=request|{'attempt_id':'resumed','resume_checkpoint':result['checkpoint_reference']}
    p2=tmp_path/'request2.json';atomic_json(p2,req2);out2=tmp_path/'response2.json'
    sub=tmp_path/'second';sub.mkdir()
    code=runner.execute_worker(runner.worker_command(sys.executable,p2,out2),sub/'worker.log',timeout=60)
    assert runner.check_response(read_json(out2),req2,p2,code)['status']=='SMOKE_PASSED'
