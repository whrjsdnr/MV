"""실행기에는 경로와 지원 조건만 둔다. 모델 코드는 models/가 소유한다."""
import importlib

OWNER_BACKENDS={'efficientad_s':'models.anomaly.efficientad_s.train',
                'retinanet':'models.detection.retinanet.train',
                'yolo11':'models.detection.yolo11.train'}


def limitations(config):
    """구현하지 않은 설정을 조용히 무시하지 않는다."""
    key=config['model_key']; issues=[]
    if key not in OWNER_BACKENDS: return ['TRAIN_BACKEND_NOT_IMPLEMENTED']
    if config['annotation_policy']!='defect_only': issues.append('D2_TRAINING_NOT_IMPLEMENTED')
    if config['gradient_accumulation']!=1: issues.append('GRADIENT_ACCUMULATION_NOT_IMPLEMENTED')
    if config['workers']!=0: issues.append('RESUME_REQUIRES_WORKERS_ZERO')
    if config['ema']: issues.append('CUSTOM_EMA_NOT_IMPLEMENTED')
    if config['early_stopping_patience'] is not None and key!='yolo11': issues.append('EARLY_STOPPING_NOT_IMPLEMENTED')
    if key=='efficientad_s' and (config['batch_size']!=1 or config['input_resolution']!=256):
        issues.append('EFFICIENTAD_PINNED_SHAPE_REQUIRES_BATCH1_SIZE256')
    if key=='yolo11' and config['max_steps'] is not None: issues.append('YOLO_USES_EPOCH_BUDGET')
    if key=='yolo11' and config['mixed_precision']: issues.append('YOLO_CPU_BASELINE_AMP_DISABLED')
    return issues


def run_backend(request):
    cfg=request['settings'];issues=limitations(cfg)
    if issues: return dict(status='BLOCKED',reason='; '.join(issues),training_executed=False)
    # 사용자 허용 CPU 정책을 유지한다. CUDA를 CPU로 조용히 치환하지 않는다.
    if request['device']=='cpu' and not cfg['allow_cpu_training']:
        return dict(status='BLOCKED',reason='CPU_FULL_TRAINING_DISABLED',training_executed=False)
    import torch, os
    torch.set_num_threads(cfg.get('cpu_threads',4))
    os.environ['YOLO_OFFLINE']='true'
    os.environ['YOLO_AUTOINSTALL']='false'
    os.environ['YOLO_CONFIG_DIR']=str(__import__('pathlib').Path(request['job_dir'])/'yolo_config')
    module=importlib.import_module(OWNER_BACKENDS[request['model_key']])
    return module.run(request)
