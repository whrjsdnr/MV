"""Owner 모델의 실제 CPU 연산·좌표·실패/복구 계약. 합성 표본을 실제 성능으로 보고하지 않는다."""
from pathlib import Path
import random
import numpy as np
import pytest
import torch
from test_team_data_release import release_data
from test_team_data_release_v2 import v2_data
from mv_analysis.data.team_release_v2 import TeamReleaseV2
from mv_analysis.training.settings import model_settings
from mv_analysis.training.backends import limitations, OWNER_BACKENDS
from mv_analysis.training.state import CONTRACT_VERSION, validate_checkpoint, latest_checkpoint
from models._shared.runtime import rng_state,restore_rng,save_checkpoint,optimization
from models.detection.retinanet.preprocessing import prepare_batch
from models.detection.retinanet.backend import build_model
from models.detection.yolo11.preprocessing import label_lines
from models.detection.yolo11.dataloader import export_dataset
from models.anomaly.efficientad_s.preprocessing import prepare_image


@pytest.mark.parametrize('key',list(OWNER_BACKENDS))
def test_owner_defaults_cpu_50_epochs_batch1(key):
    cfg=model_settings(key)
    assert cfg['epochs']==50 and cfg['batch_size']==1 and cfg['allow_cpu_training']
    assert cfg['max_steps'] is None
    assert not limitations(cfg)


@pytest.mark.parametrize('key',['uniad','hvq_trans','rtdetrv2'])
def test_teammate_not_implemented(key):
    assert 'TRAIN_BACKEND_NOT_IMPLEMENTED' in limitations(model_settings(key))


@pytest.mark.parametrize('override',[
    {'gradient_accumulation':2},{'workers':2},{'annotation_policy':'product_and_defect'},
    {'early_stopping_patience':3},{'ema':True}])
def test_unsupported_settings_are_not_silently_ignored(override):
    assert limitations(model_settings('retinanet',override))


def test_original_retina_targets_no_crop_no_negative_relabel(v2_data):
    root,raw,rows,*_=v2_data;r=TeamReleaseV2(root,raw)
    data=r.dataset(task='detection',split='train',eligible_only=True)
    samples=[data[0],data[-1]]
    images,targets=prepare_batch(samples,'cpu')
    assert all(i.shape[-2:]==(64,64) for i in images)
    assert targets[0]['boxes'].shape==(0,4)
    assert targets[-1]['labels'].min()==1
    assert torch.equal(targets[-1]['boxes'],samples[-1]['boxes'])
    bad=dict(samples[-1],detection_trainable=False)
    with pytest.raises(ValueError,match='NG'):prepare_batch([bad],'cpu')
    bad=dict(samples[0],image=samples[0]['image']-3)
    with pytest.raises(ValueError,match='unnormalized'):prepare_batch([bad],'cpu')


def test_real_torchvision_cpu_forward_backward_and_restore():
    """합성 영상으로 실제 RetinaNet을 한 step 실행한다. 사전학습 성능 테스트가 아니다."""
    torch.set_num_threads(1)
    cfg=model_settings('retinanet',{'input_resolution':64})
    model=build_model(cfg,1,random_init_for_test=True)
    model.train();image=torch.rand(3,64,64)
    losses=model([image],[{'boxes':torch.tensor([[12.,12.,25.,26.]]),'labels':torch.tensor([1])}])
    assert set(losses)=={'classification','bbox_regression'}
    total=sum(losses.values());assert torch.isfinite(total);total.backward()
    assert model.head.classification_head.cls_logits.weight.grad is not None
    model.eval()
    with torch.no_grad():prediction=model([image])[0]
    assert prediction['boxes'].shape[1]==4


def test_efficientad_requires_crop_and_no_teacher_substitution(v2_data):
    from models.anomaly.efficientad_s.backend import build_model as efficient
    with pytest.raises(ValueError,match='Teacher'):efficient({})
    root,raw,rows,*_=v2_data;r=TeamReleaseV2(root,raw)
    a=r.dataset(task='anomaly',split='train')[0]
    assert prepare_image(a).shape==(3,256,256)
    assert prepare_image(a,augment=True).shape==(3,256,256)
    full=r.dataset(task='detection',split='train',eligible_only=True)[0]
    with pytest.raises(ValueError,match='approved_crop'):prepare_image(full)


def test_yolo_original_labels_empty_ok_and_one_pixel():
    assert label_lines([],[],64,64)==''
    row=label_lines([[10,10,11,11]],[3],64,64).split()
    assert row[0]=='3'
    assert np.allclose(list(map(float,row[1:])),[10.5/64,10.5/64,1/64,1/64])
    with pytest.raises(ValueError):label_lines([[0,0,65,1]],[0],64,64)


def test_yolo_export_preserves_originals_and_excludes_missing(v2_data,tmp_path):
    root,raw,rows,*_=v2_data;r=TeamReleaseV2(root,raw)
    ds=r.dataset(task='detection',split='train',eligible_only=True)
    before={p:p.stat().st_mtime_ns for p in raw.rglob('*.jpg')}
    yaml=export_dataset({'train':ds},r.classes['yolo'],tmp_path/'yolo')
    assert yaml.is_file()
    images=list((yaml.parent/'images/train').iterdir());assert len(images)==len(ds)
    assert all(p.is_symlink() for p in images)
    assert any(not p.read_text() for p in (yaml.parent/'labels/train').iterdir())
    assert before=={p:p.stat().st_mtime_ns for p in before}
    with pytest.raises(FileExistsError):export_dataset({'train':ds},r.classes['yolo'],yaml.parent)


def test_rng_resume_repeats_next_random_draw():
    state=rng_state();expected=(random.random(),float(np.random.rand()),float(torch.rand(())))
    restore_rng(state)
    assert expected==(random.random(),float(np.random.rand()),float(torch.rand(())))


def test_checkpoint_roundtrip_and_tamper(tmp_path):
    request=dict(contract_version=CONTRACT_VERSION,model_key='retinanet',settings_sha256='s',data_sha256='d',
                 environment_sha256='e',data_kind='REAL',code_sha256='c')
    state=dict(model={'w':torch.ones(1)},optimizer={},scheduler={},rng=rng_state(),sampler={},scaler={},
               best_validation={},progress={'epoch':1,'batch':0,'step':2})
    ref=save_checkpoint(tmp_path,request,state)
    assert ref==latest_checkpoint(tmp_path)
    record=validate_checkpoint(tmp_path,ref,request)
    path=tmp_path/record['checkpoint_path']
    loaded=torch.load(path,weights_only=True);assert loaded['progress']['step']==2
    path.write_bytes(b'tampered')
    with pytest.raises(ValueError,match='integrity'):validate_checkpoint(tmp_path,ref,request)


def test_efficientad_scheduler_tracks_50_epochs_not_old_70000_steps():
    cfg=model_settings('efficientad_s');model=torch.nn.Linear(1,1)
    _,scheduler=optimization(model,cfg,total_steps=500)
    assert scheduler.step_size==475


def test_owner_one_command_and_resume_arguments():
    from argparse import Namespace
    from scripts.experiments.run_owner_cpu import command
    args=Namespace(resume=None,data_root='dataset',release_dir='release',output_root='out',
                   dry_run=True,smoke=False,max_hours=None)
    argv=command(args)
    assert argv[:4]==['--profile','owner','--device','cpu']
    assert '--dry-run' in argv and '--continue-on-error' in argv
    args.resume='out/run';args.dry_run=False
    assert command(args)==['--resume','out/run','--continue-on-error']


@pytest.mark.parametrize('key',['retinanet','efficientad_s'])
def test_optimizer_scheduler_resume_next_update_matches(tmp_path,key):
    """동일 입력에서 저장 전/복구 후 다음 update가 같은지 확인한다."""
    import copy
    cfg=model_settings(key);torch.manual_seed(17)
    original=torch.nn.Linear(2,1);opt,scheduler=optimization(original,cfg,100)
    def update(model,optimizer,lr_scheduler):
        optimizer.zero_grad();loss=model(torch.tensor([[1.,2.]])).square().mean()
        loss.backward();optimizer.step();lr_scheduler.step()
    update(original,opt,scheduler)
    states=copy.deepcopy((original.state_dict(),opt.state_dict(),scheduler.state_dict()))
    update(original,opt,scheduler)
    restored=torch.nn.Linear(2,1);new_opt,new_scheduler=optimization(restored,cfg,100)
    restored.load_state_dict(states[0]);new_opt.load_state_dict(states[1]);new_scheduler.load_state_dict(states[2])
    update(restored,new_opt,new_scheduler)
    assert all(torch.equal(a,b) for a,b in zip(original.parameters(),restored.parameters()))
    assert scheduler.get_last_lr()==new_scheduler.get_last_lr()
