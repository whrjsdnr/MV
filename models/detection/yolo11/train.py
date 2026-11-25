"""Ultralytics 공식 Trainer 연결. 자동 batch 축소를 금지하고 매 epoch에 독립 복구 스냅샷을 저장한다."""
from pathlib import Path
import copy
import signal
import uuid
import torch
from mv_analysis.experiments.contracts import atomic_json, file_sha256
from mv_analysis.experiments.recorder import ExperimentRecorder
from mv_analysis.experiments.reports import generate_experiment_report
from mv_analysis.training.state import latest_checkpoint,validate_checkpoint,register_checkpoint
from models._shared.data import open_release
from models._shared.runtime import recorder_config,rng_state,restore_rng,seed_all
from .backend import Backend, build_model
from .dataloader import build_datasets,export_dataset
from .evaluate import final_evaluation


def run(request):
    # import는 모델별 Python에서만 한다. 공통 CPU 환경에 Ultralytics를 강제로 설치하지 않는다.
    from ultralytics.models.yolo.detect import DetectionTrainer
    cfg=request['settings']; folder=Path(request['job_dir']);seed_all(cfg['seed'])
    with open_release(request) as release:
        data=build_datasets(release,cfg);classes=release.classes['yolo']
        recorder=ExperimentRecorder.create(folder/'runs',recorder_config(request,release,data,'D1')).start()
        yaml=export_dataset(data,classes,folder/('dataset_'+request['attempt_id']))
        resume=latest_checkpoint(folder);extra=None;native=None
        if resume:
            meta=validate_checkpoint(folder,resume,request)
            payload=torch.load(folder/meta['checkpoint_path'],map_location='cpu',weights_only=True)
            native=Path(payload['native_checkpoint'])
            if not native.is_relative_to(folder) or file_sha256(native)!=payload['native_sha256']:
                raise ValueError('Native YOLO checkpoint mismatch')
            extra=payload
        yolo=build_model(cfg if native is None else dict(cfg,weights=str(native)))
        state={'step':extra['progress']['step'] if extra else 0,'reference':None,'stop':False}
        previous=signal.getsignal(signal.SIGTERM)
        signal.signal(signal.SIGTERM,lambda *args:state.update(stop=True))

        class Trainer(DetectionTrainer):
            def resume_training(self, checkpoint):
                super().resume_training(checkpoint)
                if extra:
                    # native checkpoint는 EMA/FP16 저장이다. 실제 모델/optimizer/RNG를 추가 스냅샷으로 복구한다.
                    self.model.load_state_dict(extra['model']);self.optimizer.load_state_dict(extra['optimizer'])
                    self.scheduler.load_state_dict(extra['scheduler']);self.scaler.load_state_dict(extra['scaler'])

        def batch_start(trainer):
            trainer._oom_retries=3  # 고정 소스의 OOM 재시도 조건을 차단한다.

        def batch_end(trainer):
            trainer._oom_retries=0
            losses={str(k):float(v) for k,v in trainer.loss_items.items()}
            if not all(torch.isfinite(torch.tensor(v)) for v in losses.values()):
                raise FloatingPointError('NONFINITE_YOLO_LOSS')
            state['step']+=1
            recorder.log(epoch=trainer.epoch,step=state['step'],phase='train',metrics=losses)

        def saved(trainer):
            # Native last.pt는 공식 루프가 갱신한다. 독립 불변 복사본을 사용해 기존 체크포인트를 보호한다.
            import shutil
            token=uuid.uuid4().hex; native_path=folder/('native_'+token+'.pt')
            shutil.copyfile(trainer.last,native_path)
            payload=dict(model=trainer.model.state_dict(),optimizer=trainer.optimizer.state_dict(),
                scheduler=trainer.scheduler.state_dict(),scaler=trainer.scaler.state_dict(),rng=rng_state(),
                sampler={'seed':cfg['seed'],'next_epoch':trainer.epoch+1},best_validation=trainer.best_fitness,
                progress={'epoch':trainer.epoch+1,'step':state['step']},native_checkpoint=str(native_path),
                native_sha256=file_sha256(native_path))
            from models._shared.runtime import save_checkpoint
            state['reference']=save_checkpoint(folder,request,payload)
            recorder.checkpoint(native_path,epoch=trainer.epoch+1,role='resume')

        def epoch_end(trainer):
            recorder.log(epoch=trainer.epoch,step=state['step'],phase='validation',metrics=trainer.metrics)
            if state['stop']: trainer.stop=True

        def started(trainer):
            if extra: restore_rng(extra['rng'])
        for event,callback in [('on_train_start',started),('on_train_batch_start',batch_start),
            ('on_train_batch_end',batch_end),('on_model_save',saved),('on_fit_epoch_end',epoch_end)]:
            yolo.add_callback(event,callback)
        try:
            # batch=1を固定。nbs=1で隠れた勾配蓄積をなくす。CPU AMPは無効。
            kwargs=dict(trainer=Trainer,data=str(yaml),epochs=cfg['epochs'],batch=cfg['batch_size'],
                device=request['device'],imgsz=cfg['input_resolution'],workers=0,seed=cfg['seed'],
                optimizer=cfg['optimizer'],lr0=cfg['learning_rate'],weight_decay=cfg['weight_decay'],
                amp=False,nbs=1,project=str(folder/'native_runs'),name=request['attempt_id'],exist_ok=False,
                save=True,save_period=cfg['checkpoint_interval'],val=True,plots=False,cache=False,
                patience=cfg['early_stopping_patience'] or 0,cos_lr=True,deterministic=True)
            if cfg['augmentation']=='none':
                kwargs.update(hsv_h=0.,hsv_s=0.,hsv_v=0.,degrees=0.,translate=0.,scale=0.,shear=0.,
                              perspective=0.,flipud=0.,fliplr=0.,mosaic=0.,mixup=0.,copy_paste=0.)
            if native: kwargs['resume']=str(native)
            yolo.train(**kwargs)
            if state['stop']:
                recorder.finalize('INTERRUPTED',training_executed=state['step']>0)
                return dict(status='INTERRUPTED',training_executed=state['step']>0,checkpoint_reference=state['reference'])
            best=Path(yolo.trainer.best)
            if not best.is_file(): raise FileNotFoundError('YOLO best checkpoint missing')
            recorder.checkpoint(best,epoch=yolo.trainer.epoch+1,role='best_validation_native_fitness')
            from ultralytics import YOLO
            backend=Backend(cfg,classes,request['device'],YOLO(best))
            final_evaluation(backend,data,recorder)
            from .benchmark import measure
            recorder.artifact('benchmark.json',measure(backend,data['test'][0],best))
            recorder.finalize('COMPLETED',training_executed=True,evidence={'steps':state['step'],'best_checkpoint':str(best)})
            report=generate_experiment_report(recorder.path)
            return dict(status='COMPLETED',training_executed=True,report=str(report),report_sha256=file_sha256(report),steps=state['step'])
        except BaseException:
            if recorder.state['status']=='RUNNING': recorder.finalize('FAILED',training_executed=state['step']>0)
            generate_experiment_report(recorder.path)
            raise
        finally: signal.signal(signal.SIGTERM,previous)
