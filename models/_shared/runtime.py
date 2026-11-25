"""Torch 기반 Owner 학습 수명주기. 모델 연산은 각 models/<종류>/<모델>/backend.py가 소유한다."""
from pathlib import Path
import math
import os
import random
import signal
import subprocess
import time
import uuid
import traceback
import numpy as np
import torch
from torch.utils.data import DataLoader
from mv_analysis.experiments.contracts import digest, file_sha256, atomic_json, PROTOCOL
from mv_analysis.experiments.recorder import ExperimentRecorder
from mv_analysis.experiments.reports import generate_experiment_report
from mv_analysis.experiments.benchmark import benchmark
from mv_analysis.experiments.anomaly import binary_metrics
from mv_analysis.experiments.detection import prepare, coco_metrics
from mv_analysis.training.state import register_checkpoint, latest_checkpoint, validate_checkpoint
from .data import collate
from .evaluation import ground_truth, final_evaluation
from .diagnostics import checked_losses, tensor_stats, sample_evidence


def recorder_config(request, release, data, suffix):
    cfg = request['settings']
    ids = {s:digest(sorted(data[s].index.data.image_id.tolist())) for s in ('validation','test')}
    return dict(experiment_id=f'owner-{cfg["model_key"]}-{suffix}',
        model_name=cfg['model_name'], model_family=cfg['model_family'],
        official_repo=cfg['official_repo'], official_commit=cfg['official_commit'],
        project_commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        manifest_sha256=release.sha256, annotation_sha256=file_sha256(release.root/'annotations/defect_boxes.csv'),
        class_mapping_sha256=file_sha256(release.root/'schemas/class_mapping.json'),
        evaluation_set_sha256=digest(ids),evaluation_ids_sha256=ids,
        split_version='v2-preserved',crop_policy_version='v2-approved-crop-anomaly-original-full-detection',
        model_adapter_version='owner-backend-v1',seed=cfg['seed'],device=request['device'],
        batch_size=cfg['batch_size'],epochs=cfg['epochs'],optimizer=cfg['optimizer'],scheduler=cfg['scheduler'],
        learning_rate=cfg['learning_rate'],input_resolution=[cfg['input_resolution']]*2,
        normalization='model-specific: see backend settings',checkpoint_path=None,checkpoint_sha256=None,
        data_kind='REAL',comparison_track=cfg['comparison_track'],nms_policy=PROTOCOL['nms_policy'],
        reproduce_command='uv run python scripts/experiments/run_weekend.py --models '+cfg['model_key'],
        backend_settings=cfg, runner_bindings_sha256=digest(request),
        teacher_auxiliary_data='DISABLED_PINNED_DEFAULT' if cfg['model_family']=='anomaly' else 'N/A')


def seed_all(seed):
    random.seed(seed); np.random.seed(seed); torch.manual_seed(seed)
    if torch.cuda.is_available(): torch.cuda.manual_seed_all(seed)


def rng_state():
    state = np.random.get_state()
    return dict(python=random.getstate(), numpy=[state[0],state[1].tolist(),*state[2:]],
                torch=torch.get_rng_state(),cuda=torch.cuda.get_rng_state_all() if torch.cuda.is_available() else [])


def restore_rng(state):
    random.setstate(state['python'])
    n=state['numpy']; np.random.set_state((n[0],np.array(n[1],dtype=np.uint32),*n[2:]))
    torch.set_rng_state(state['torch'].cpu())
    if state['cuda']: torch.cuda.set_rng_state_all([t.cpu() for t in state['cuda']])


def save_checkpoint(folder, request, payload):
    """불변 체크포인트 + 해시 참조를 원자 저장한다. 승인 파일/기존 Run에는 쓰지 않는다."""
    destination=folder/('state_'+uuid.uuid4().hex+'.pt')
    temporary=destination.with_suffix('.tmp')
    with temporary.open('xb') as stream:
        torch.save(payload,stream); stream.flush(); os.fsync(stream.fileno())
    os.replace(temporary,destination)
    ref=register_checkpoint(folder,destination,request,epoch=payload['progress']['epoch'],
        global_step=payload['progress']['step'],state_fields=payload.keys())
    return str(ref)


def optimization(model, cfg, total_steps=None):
    params=[p for p in model.parameters() if p.requires_grad]
    if cfg['optimizer']=='SGD': opt=torch.optim.SGD(params,lr=cfg['learning_rate'],momentum=.9,weight_decay=cfg['weight_decay'])
    elif cfg['optimizer']=='Adam': opt=torch.optim.Adam(params,lr=cfg['learning_rate'],weight_decay=cfg['weight_decay'])
    else: raise ValueError('Unsupported Owner optimizer')
    if cfg['scheduler']=='MultiStepLR': scheduler=torch.optim.lr_scheduler.MultiStepLR(opt,cfg['step_size'],gamma=cfg['gamma'])
    elif cfg['scheduler']=='step_per_update': scheduler=torch.optim.lr_scheduler.StepLR(opt,max(1,int(total_steps*cfg['scheduler_fraction'])) if cfg.get('scheduler_fraction') else cfg['step_size'],gamma=cfg['gamma'])
    else: raise ValueError('Unsupported Owner scheduler')
    return opt,scheduler


def validation_score(backend, dataset):
    """Best는 Validation만으로 선택한다. Pixel 평가/AUPRO는 최종 평가 단계에서 수행한다."""
    if backend.config['model_family']=='anomaly':
        labels=[];scores=[]
        for sample in dataset:
            labels.append(int(sample['status']=='NG')); scores.append(backend.predict(sample)['score'])
        return binary_metrics(labels,scores)['auroc']
    gt=ground_truth(dataset,'detection')
    predictions=[backend.predict(sample) for sample in dataset]
    records,_,_=prepare(gt,predictions,'validation',backend.classes)
    return coco_metrics(records,backend.classes)['map50_95']


def train_torch(request, release, data, backend, *, suffix):
    """실제 gradient update·Validation·Best/Resume·최종 평가. CPU 전체 실행은 worker에서 차단한다."""
    cfg=request['settings']; folder=Path(request['job_dir'])/suffix; folder.mkdir(exist_ok=True)
    completed=folder/'completed.json'
    if completed.exists():
        import json
        receipt=json.loads(completed.read_text())
        if receipt['settings_sha256']!=request['settings_sha256']:
            raise ValueError('Completed category settings mismatch')
        if file_sha256(receipt['report'])!=receipt['report_sha256']:
            raise ValueError('Completed report changed')
        return receipt
    recorder=ExperimentRecorder.create(folder/'runs',recorder_config(request,release,data,suffix)).start()
    opt,scheduler=optimization(backend.model,cfg,math.ceil(len(data['train'])/cfg['batch_size'])*cfg['epochs'])
    scaler=torch.amp.GradScaler('cuda',enabled=cfg['mixed_precision'])
    progress={'epoch':0,'batch':0,'step':0,'phase':'training'};best=None;best_path=None;reference=None
    samples=[]; losses={}
    stop={'requested':False};previous=signal.getsignal(signal.SIGTERM)
    signal.signal(signal.SIGTERM,lambda *args:stop.update(requested=True))
    # 모델 생성 전에 train.py가 seed를 고정한다. 재시작은 checkpoint RNG로 이어간다.
    def snapshot():
        return save_checkpoint(folder,request,dict(model=backend.model.state_dict(),optimizer=opt.state_dict(),
            scheduler=scheduler.state_dict(),scaler=scaler.state_dict(),rng=rng_state(),
            sampler={'seed':cfg['seed'],'next_batch':progress['batch']},progress=dict(progress),
            best_validation={'score':best,'checkpoint':best_path}))
    def mark(status, **details):
        atomic_json(folder/'training_progress.json',dict(status=status,training_executed=progress['step']>0,
            progress=dict(progress),checkpoint_reference=reference,**details))
    try:
        mark('PREPARING')
        ref=latest_checkpoint(folder)
        if ref:
            meta=validate_checkpoint(folder,ref,request)
            payload=torch.load(folder/meta['checkpoint_path'],map_location=request['device'],weights_only=True)
            backend.model.load_state_dict(payload['model']); opt.load_state_dict(payload['optimizer'])
            scheduler.load_state_dict(payload['scheduler']);scaler.load_state_dict(payload['scaler'])
            progress=payload['progress'];best=payload['best_validation']['score'];best_path=payload['best_validation']['checkpoint']
            restore_rng(payload['rng']);recorder.artifact('resume.json',{'reference':str(ref)})
        else:
            backend.prepare(data['train'])
        while progress['epoch']<cfg['epochs'] and (cfg['max_steps'] is None or progress['step']<cfg['max_steps'] or progress.get('phase')=='calibration_pending'):
            start=time.perf_counter(); backend.model.train()
            # 순서는 epoch/seed만으로 재현한다. 중단 이전 배치는 재학습하지 않는다.
            indices=torch.randperm(len(data['train']),generator=torch.Generator().manual_seed(cfg['seed']+progress['epoch'])).tolist()
            batches=[indices[i:i+cfg['batch_size']] for i in range(0,len(indices),cfg['batch_size'])]
            for batch_idx in (range(progress['batch'],len(batches)) if progress.get('phase')!='calibration_pending' else []):
                samples=[data['train'][i] for i in batches[batch_idx]]
                losses={}
                opt.zero_grad(set_to_none=True)
                with torch.autocast(device_type=torch.device(request['device']).type,enabled=cfg['mixed_precision']):
                    losses=backend.loss(samples); total=checked_losses(losses)
                scaler.scale(total).backward();scaler.unscale_(opt)
                norm=torch.nn.utils.clip_grad_norm_([p for p in backend.model.parameters() if p.requires_grad],
                    cfg['gradient_clip'] or float('inf'),error_if_nonfinite=True)
                scaler.step(opt);scaler.update()
                if not all(torch.isfinite(p).all() for p in backend.model.parameters()):
                    raise FloatingPointError('NONFINITE_PARAMETERS_AFTER_UPDATE')
                if cfg['scheduler']=='step_per_update': scheduler.step()
                progress.update(step=progress['step']+1,batch=batch_idx+1)
                mark('TRAINING')
                recorder.log(epoch=progress['epoch'],step=progress['step'],phase='train',metrics={
                    **{k:float(v.detach()) for k,v in losses.items()},'loss_total':float(total.detach()),
                    'learning_rate':opt.param_groups[0]['lr'],'gradient_norm':float(norm)})
                if stop['requested']:
                    reference=snapshot()
                    mark('INTERRUPTED')
                    recorder.finalize('INTERRUPTED',training_executed=True)
                    return dict(status='INTERRUPTED',training_executed=True,checkpoint_reference=reference)
                if cfg['max_steps'] and progress['step']>=cfg['max_steps']: break
            # 학습 update와 검증은 별도 단계다. 검증 실패로 한 epoch의 유효한 가중치를 잃지 않는다.
            # 재개 시 calibration_pending이면 배치를 다시 학습하지 않고 검증부터 재시도한다.
            if progress.get('phase')!='calibration_pending':
                progress['phase']='calibration_pending'
                reference=snapshot()
            mark('CALIBRATING')
            backend.model.eval();backend.calibrate_maps(data['validation'])
            if hasattr(backend,'calibration_diagnostics'):
                recorder.artifact('calibration_'+str(progress['step'])+'.json',backend.calibration_diagnostics)
            score=validation_score(backend,data['validation'])
            if score is None or not math.isfinite(score): raise ValueError('Validation selection metric unavailable')
            recorder.log(epoch=progress['epoch'],step=progress['step'],phase='validation',
                metrics={'selection_metric':score,'epoch_seconds':time.perf_counter()-start})
            if cfg['scheduler']!='step_per_update': scheduler.step()
            progress.update(epoch=progress['epoch']+1,batch=0,phase='training')
            if best is None or score>best:
                best=score;best_path=str(folder/('best_'+uuid.uuid4().hex+'.pt'))
                with open(best_path,'xb') as stream: torch.save(backend.model.state_dict(),stream)
                recorder.checkpoint(best_path,epoch=progress['epoch'],role='best_validation')
            reference=snapshot()
            mark('VALIDATED')
            print(f'{suffix}: epoch={progress["epoch"]} step={progress["step"]} validation={score:.6g}',flush=True)
        if best_path is None: raise ValueError('No validated best checkpoint')
        backend.model.load_state_dict(torch.load(best_path,map_location=request['device'],weights_only=True));backend.model.eval()
        final_evaluation(backend,data,recorder)
        sample=data['test'][0]
        measured=benchmark(backend.model,[backend.benchmark_input(sample)],input_ids=[sample['image_id']],
            device=request['device'],batch_size=1,warmup=cfg['benchmark_warmup'],repetitions=cfg['benchmark_repetitions'],checkpoint=best_path)
        measured['scope_note']='Backend prepared-input timing; external image decode/transform excluded. RetinaNet includes internal transform and NMS.'
        recorder.artifact('benchmark.json',measured)
        recorder.finalize('COMPLETED',training_executed=True,evidence={'steps':progress['step'],'best_checkpoint':best_path})
        report=generate_experiment_report(recorder.path)
        result=dict(status='COMPLETED',training_executed=True,report=str(report),report_sha256=file_sha256(report),
                    steps=progress['step'],settings_sha256=request['settings_sha256'],best_checkpoint=best_path)
        atomic_json(completed,result,exclusive=True)
        mark('COMPLETED')
        return result
    except BaseException as exc:
        # OOM/오류를 숨기거나 batch를 자동으로 줄이지 않는다. 마지막 유효 checkpoint는 보존한다.
        failure=dict(error=repr(exc),traceback=traceback.format_exc(),progress=dict(progress),
            losses={k:tensor_stats(v) for k,v in losses.items()},samples=sample_evidence(samples),
            backend=getattr(backend,'last_diagnostics',None),calibration=getattr(backend,'calibration_diagnostics',None))
        recorder.artifact('failure_diagnostics.json',failure)
        status='INTERRUPTED' if isinstance(exc,KeyboardInterrupt) else 'FAILED'
        mark(status,error=failure['error'],traceback=failure['traceback'])
        if recorder.state['status']=='RUNNING': recorder.finalize(status,training_executed=progress['step']>0)
        generate_experiment_report(recorder.path)
        raise
    finally:
        signal.signal(signal.SIGTERM,previous)
