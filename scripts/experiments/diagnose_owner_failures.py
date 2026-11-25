"""기존 Run은 읽기 전용, 새 디렉터리에서만 제한된 실제 CPU 진단을 실행한다.

RetinaNet: 동일 seed/순서/800px에서 원래 설정과 clip=1만 다른 별도 진단 비교.
EfficientAD: 마지막 체크포인트를 읽어 소량 업데이트·calibration·Validation·복구 확인.
50 epoch 실행기가 아니며 Test 분할을 읽어 성능을 선택하지 않는다.
"""
from pathlib import Path
import argparse
import copy
import gc
import json
import sys
import time
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import torch
from mv_analysis.data.team_release_v2 import TeamReleaseV2
from mv_analysis.experiments.contracts import atomic_json, file_sha256
from mv_analysis.experiments.recorder import ExperimentRecorder
from mv_analysis.experiments.reports import generate_experiment_report
from models._shared.runtime import (seed_all, optimization, rng_state, restore_rng, recorder_config)
from models._shared.diagnostics import tensor_stats, checked_losses
from models._shared.data import datasets
from models._shared.evaluation import ground_truth, evaluate, save_examples


def subset(ds, indices):
    small = copy.copy(ds); small.index = copy.copy(ds.index)
    small.data = ds.data.iloc[indices].copy().reset_index(drop=True)
    small.index.data = small.data
    return small


def validation_subset(ds):
    rows = ds.data
    return subset(ds, list(rows.index[rows.status.eq('OK')][:2]) + list(rows.index[rows.status.eq('NG')][:2]))


def save_payload(path, backend, opt, sched, progress):
    with path.open('xb') as stream:
        torch.save(dict(model=backend.model.state_dict(), optimizer=opt.state_dict(),
                        scheduler=sched.state_dict(), scaler={}, rng=rng_state(),
                        sampler=dict(seed=backend.config['seed'], next_batch=progress['batch']),
                        progress=progress, best_validation={'score':None,'checkpoint':None}), stream)


def restore(path, backend, opt, sched):
    payload = torch.load(path, map_location='cpu', weights_only=True)
    backend.model.load_state_dict(payload['model']); opt.load_state_dict(payload['optimizer'])
    sched.load_state_dict(payload['scheduler']); restore_rng(payload['rng'])
    return payload


def finish_validation(backend, val, rec):
    backend.model.eval()
    gt = ground_truth(val, backend.config['model_family'])
    predictions = [backend.predict(s) for s in val]
    rec.predictions(predictions)
    result, policy = evaluate(backend.config['model_family'], gt, predictions, backend.classes, split='validation')
    rec.evaluation('validation', result)
    save_examples(backend, val, gt, policy, rec, limit=4)
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source-run', required=True); p.add_argument('--output', required=True)
    p.add_argument('--model', choices=['retinanet','efficientad_s'], required=True)
    p.add_argument('--learning-rates', default=None, help='쉼표 구분 lr 목록. 기본은 원 Run 설정.')
    p.add_argument('--clippings', default='none,1.0', help='쉼표 구분 clip 목록(none 가능).')
    args = p.parse_args()
    old = Path(args.source_run).resolve(); out = Path(args.output).resolve()
    if out.is_relative_to(old): raise ValueError('Source run is read-only')
    out.mkdir(parents=True, exist_ok=False)
    plan = json.loads((old/'plan.json').read_text()); cfg = plan['settings'][args.model]
    torch.set_num_threads(4)
    release = TeamReleaseV2(plan['release_source'], plan['data_root'])
    req = json.loads(next((old/args.model).glob('attempt_*/request.json')).read_text())
    atomic_json(out/'scope.json', dict(source_run=str(old), source_manifest=release.sha256,
        model=args.model, max_updates_per_trial=40 if args.model=='retinanet' else 3,
        device='cpu', threads=4, test_evaluation=False, settings=cfg), exclusive=True)
    if args.model=='retinanet':
        from models.detection.retinanet.backend import Backend
        data = datasets(release, cfg)
        indices = torch.randperm(len(data['train']), generator=torch.Generator().manual_seed(cfg['seed'])).tolist()[:41]
        lrs=[float(x) for x in args.learning_rates.split(',')] if args.learning_rates else [cfg['learning_rate']]
        clippings=[None if x=='none' else float(x) for x in args.clippings.split(',')]
        val_subset=validation_subset(data['validation'])
        for lr in lrs:
            for clipping in clippings:
                seed_all(cfg['seed']); trial=out/(f'lr{lr:g}_clip{clipping if clipping is not None else "none"}'); trial.mkdir()
                config=dict(cfg, gradient_clip=clipping, learning_rate=lr); request=dict(req, settings=config)
                backend=Backend(config, release.classes['yolo'], 'cpu')
                opt,sched=optimization(backend.model, config)
                rec=ExperimentRecorder.create(trial/'runs',recorder_config(request,release,dict(data,validation=val_subset),'bounded-diagnostic')).start()
                rows=[]; started=time.perf_counter(); success=True
                try:
                    for step,index in enumerate(indices[:40],1):
                        backend.model.train(); opt.zero_grad(set_to_none=True)
                        sample=data['train'][index]; losses=backend.loss([sample])
                        row=dict(step=step,image_id=sample['image_id'],status=sample['status'],
                                 losses={k:tensor_stats(v) for k,v in losses.items()}, details=backend.last_diagnostics)
                        rows.append(row)
                        total=checked_losses(losses); total.backward()
                        norm=torch.nn.utils.clip_grad_norm_(backend.model.parameters(),clipping or float('inf'),error_if_nonfinite=True)
                        row['gradient_norm_before_clip']=float(norm)
                        opt.step()
                        row['parameter_norm']=float(torch.linalg.vector_norm(torch.stack([p.detach().norm() for p in backend.model.parameters()])))
                        if not all(torch.isfinite(p).all() for p in backend.model.parameters()):
                            raise FloatingPointError('NONFINITE_PARAMETERS_AFTER_UPDATE')
                        rec.log(epoch=0,step=step,phase='train',metrics={**{k:float(v.detach()) for k,v in losses.items()},'gradient_norm':float(norm)})
                        atomic_json(trial/'steps.json',rows)
                        print(trial.name,step,float(total.detach()),float(norm),flush=True)
                    checkpoint=trial/'state_step40.pt'
                    save_payload(checkpoint,backend,opt,sched,dict(epoch=0,batch=40,step=40))
                    # 실제 모델/optimizer/scheduler/RNG를 디스크에서 다시 읽고 다음 입력 1개를 처리한다.
                    restored=restore(checkpoint,backend,opt,sched)
                    backend.model.train();opt.zero_grad(set_to_none=True)
                    loss=checked_losses(backend.loss([data['train'][indices[40]]]))
                    loss.backward();norm=torch.nn.utils.clip_grad_norm_(backend.model.parameters(),clipping or float('inf'),error_if_nonfinite=True); opt.step()
                    atomic_json(trial/'resume.json',dict(restored_progress=restored['progress'],source_sha256=file_sha256(checkpoint),
                        next_step=41,loss=float(loss.detach()),gradient_norm=float(norm),exact_replay_equivalence='UNIT_TEST_ONLY'),exclusive=True)
                    atomic_json(trial/'validation.json',finish_validation(backend,val_subset,rec),exclusive=True)
                    rec.finalize('PARTIAL',training_executed=True,evidence={'scope':'BOUNDED_REAL_DIAGNOSTIC','updates':41})
                except Exception as exc:
                    import traceback
                    success=False
                    atomic_json(trial/'failure.json',dict(error=repr(exc),traceback=traceback.format_exc(),steps=rows),exclusive=True)
                    rec.finalize('FAILED',training_executed=len(rows)>1)
                generate_experiment_report(rec.path)
                atomic_json(trial/'result.json',dict(success=success,attempted_steps=len(rows),elapsed_seconds=time.perf_counter()-started,
                    scope='NO_LONG_TERM_STABILITY_CLAIM',gradient_clip=clipping,learning_rate=lr),exclusive=True)
                del backend,opt,sched,rec;gc.collect()
    else:
        from models.anomaly.efficientad_s.backend import Backend
        seed_all(cfg['seed']);data=datasets(release,cfg,category='audiojack')
        backend=Backend(cfg,release.classes['yolo'],'cpu')
        opt,sched=optimization(backend.model,cfg,len(data['train'])*cfg['epochs'])
        pointer=json.loads((old/'efficientad_s/audiojack/checkpoint_latest.json').read_text())
        reference=old/'efficientad_s/audiojack'/pointer['reference']
        assert file_sha256(reference)==pointer['reference_sha256']
        meta=json.loads(reference.read_text()); checkpoint=reference.parent/meta['checkpoint_path']
        assert file_sha256(checkpoint)==meta['sha256']
        state=restore(checkpoint,backend,opt,sched)
        val=data['validation']; ids=[]
        for view in ['C1','C2','C3','C4','C5']:
            ids+=val.data.index[val.data.status.eq('OK')&val.data.view.eq(view)].tolist()[:3]
        calibration=subset(val,ids)
        backend.calibrate_maps(calibration)
        atomic_json(out/'calibration_before.json',backend.calibration_diagnostics,exclusive=True)
        # 진단 calibration은 버퍼를 갱신하므로 실제 학습 시작 직전 원본 상태를 다시 복원한다.
        state=restore(checkpoint,backend,opt,sched)
        val_subset=validation_subset(val)
        rec=ExperimentRecorder.create(out/'runs',recorder_config(req,release,dict(data,validation=val_subset),'bounded-checkpoint-diagnostic')).start()
        order=torch.randperm(len(data['train']),generator=torch.Generator().manual_seed(cfg['seed']+state['progress']['epoch'])).tolist()
        for batch in range(2):
            backend.model.train();opt.zero_grad(set_to_none=True)
            losses=backend.loss([data['train'][order[batch]]]);total=checked_losses(losses);total.backward()
            norm=torch.nn.utils.clip_grad_norm_(backend.model.parameters(),float('inf'),error_if_nonfinite=True)
            opt.step();sched.step()
            rec.log(epoch=2,step=3631+batch,phase='train',metrics={**{k:float(v.detach()) for k,v in losses.items()},'gradient_norm':float(norm)})
        saved=out/'state_step3632.pt'; save_payload(saved,backend,opt,sched,dict(epoch=2,batch=2,step=3632))
        restored=restore(saved,backend,opt,sched)
        backend.model.train();opt.zero_grad(set_to_none=True)
        loss=checked_losses(backend.loss([data['train'][order[2]]]))
        loss.backward();norm=torch.nn.utils.clip_grad_norm_(backend.model.parameters(),float('inf'),error_if_nonfinite=True);opt.step();sched.step()
        backend.calibrate_maps(calibration)
        atomic_json(out/'calibration_after.json',backend.calibration_diagnostics,exclusive=True)
        atomic_json(out/'resume.json',dict(source_progress=state['progress'],restored_progress=restored['progress'],
            next_step=3633,next_loss=float(loss.detach()),source_sha256=meta['sha256'],new_sha256=file_sha256(saved),
            restored_fields=list(restored),scaler='DISABLED_CPU',sampler='epoch seed + next batch',
            scope='SAMPLED_CALIBRATION_NOT_FAILED_EPOCH3_REPLAY'),exclusive=True)
        atomic_json(out/'validation.json',finish_validation(backend,val_subset,rec),exclusive=True)
        rec.finalize('PARTIAL',training_executed=True,evidence={'scope':'3_UPDATES_FROM_STEP3630','test_executed':False})
        generate_experiment_report(rec.path)
        print('EfficientAD checkpoint smoke complete',flush=True)


if __name__=='__main__': main()
