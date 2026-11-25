"""담당자 프로필, 불변 실행 설정, 사전 점검. 실험 설정 변경은 새 실행으로 구분한다."""
import json
import math
import os
import re
from pathlib import Path
from mv_analysis.experiments.contracts import registry, file_sha256

ROOT = Path(__file__).resolve().parents[2]
MODELS = {'rtdetrv2':'RT-DETRv2', 'uniad':'UniAD', 'hvq_trans':'HVQ-Trans',
          'efficientad_s':'EfficientAD-S', 'retinanet':'RetinaNet', 'yolo11':'YOLO11'}
PROFILES = {'teammate':['rtdetrv2','uniad','hvq_trans'], 'owner':['efficientad_s','retinanet','yolo11']}
SOURCE_KEYS = dict(rtdetrv2='rtdetrv2', uniad='uniad', hvq_trans='hvqtrans', efficientad_s='efficientad', yolo11='yolo11')
SETTINGS_VERSION = 'mv-training-settings-v1'


def read_json(path):
    """오타를 조용히 덮는 중복 키와 비표준 NaN/Infinity를 설정에서 거부한다."""
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('Duplicate JSON key: '+key)
            result[key] = value
        return result
    def invalid(value):
        raise ValueError('Nonfinite JSON number: '+value)
    return json.loads(Path(path).read_text(), object_pairs_hook=pairs, parse_constant=invalid)


def select_models(profile=None, models=None):
    """명시한 순서를 보존한다. 프로필과 개별 모델 목록을 동시에 해석하지 않는다."""
    if bool(profile) == bool(models):
        raise ValueError('Choose exactly one of --profile or --models')
    if profile:
        if profile not in PROFILES:
            raise ValueError('Unknown profile: '+profile)
        return list(PROFILES[profile])
    selected = models.split(',') if isinstance(models, str) else list(models)
    if not selected or any(m not in MODELS for m in selected) or len(set(selected)) != len(selected):
        raise ValueError('Unknown/duplicate model key; use: '+', '.join(MODELS))
    return selected


def validate_settings(cfg):
    """bool은 정수로 취급하지 않는다. 실제 루프가 없는 현재 설정은 검증된 baseline이 아니다."""
    if cfg.get('cpu_threads') is not None and (type(cfg['cpu_threads']) is not int or cfg['cpu_threads']<1):
        raise ValueError('cpu_threads must be positive integer')
    if cfg.get('scheduler_fraction') is not None and not 0 < cfg['scheduler_fraction'] < 1:
        raise ValueError('scheduler_fraction must be between zero and one')
    if cfg.get('initialization') not in (None,'random','local_checkpoint'):
        raise ValueError('Unknown initialization policy')
    for key in ('epochs', 'batch_size', 'gradient_accumulation', 'checkpoint_interval',
                'input_resolution', 'benchmark_repetitions', 'benchmark_warmup'):
        if type(cfg[key]) is not int or cfg[key] < 1:
            raise ValueError(key+' must be a positive integer')
    for key in ('seed','workers'):
        if type(cfg[key]) is not int or cfg[key] < 0:
            raise ValueError(key+' must be a nonnegative integer')
    for key in ('max_steps','train_limit','eval_limit','early_stopping_patience'):
        if cfg[key] is not None and (type(cfg[key]) is not int or cfg[key] < 1):
            raise ValueError(key+' must be null or a positive integer')
    for key in ('learning_rate','gamma','minimum_free_gb','weight_decay','gradient_clip'):
        value = cfg[key]
        if key == 'gradient_clip' and value is None:
            continue
        if type(value) not in (int,float) or not math.isfinite(value) or value < 0 or (key != 'weight_decay' and value == 0):
            raise ValueError('Invalid finite setting: '+key)
    if cfg['benchmark_repetitions'] < 2:
        raise ValueError('benchmark_repetitions must be >= 2')
    for key in ('mixed_precision','ema','allow_cpu_training'):
        if type(cfg[key]) is not bool:
            raise ValueError(key+' must be boolean')
    for key in ('source_dir','weights','source_config'):
        if cfg[key] is not None and (not isinstance(cfg[key],str) or not cfg[key].strip()):
            raise ValueError(key+' must be null or a nonempty path string')
    if cfg['source_config'] is not None and (Path(cfg['source_config']).is_absolute() or '..' in Path(cfg['source_config']).parts):
        raise ValueError('source_config must stay inside the official source')
    if cfg['weights_sha256'] is not None and (not isinstance(cfg['weights_sha256'],str) or not re.fullmatch(r'[0-9a-f]{64}', cfg['weights_sha256'])):
        raise ValueError('weights_sha256 must be lowercase SHA256')
    if cfg['annotation_policy'] not in ('defect_only','product_and_defect'):
        raise ValueError('Unknown annotation policy')
    if cfg['model_family']=='anomaly' and cfg['annotation_policy']!='defect_only':
        raise ValueError('Anomaly task cannot use detection D2 policy')
    if cfg['comparison_track'] not in ('COMMON_INPUT','OFFICIAL_BASELINE','OPTIMIZED'):
        raise ValueError('Unknown comparison track')
    for key in ('optimizer','scheduler','augmentation'):
        if not isinstance(cfg[key],str) or not cfg[key].strip():
            raise ValueError(key+' must be a nonempty string')
    steps=cfg['step_size'] if isinstance(cfg['step_size'],list) else [cfg['step_size']]
    if not steps or any(type(v) is not int or v<1 for v in steps) or steps!=sorted(set(steps)):
        raise ValueError('step_size must be positive integer(s), strictly increasing')
    if cfg['categories'] is not None:
        cats=cfg['categories']
        if not isinstance(cats,list) or not cats or any(not isinstance(v,str) or not re.fullmatch(r'[a-zA-Z0-9_-]+',v) for v in cats) or len(set(cats))!=len(cats):
            raise ValueError('categories must be a unique nonempty string list')
    if cfg.get('hard_mining_quantile') is not None and not 0 < cfg['hard_mining_quantile'] < 1:
        raise ValueError('hard_mining_quantile must be between zero and one')
    if cfg.get('background_keep_ratio') is not None and not 0 < cfg['background_keep_ratio'] <= 1:
        raise ValueError('background_keep_ratio must be in (0, 1]')
    return cfg


def model_settings(key, overrides=None):
    if key not in MODELS:
        raise ValueError('Unknown model: '+key)
    cfg = read_json(ROOT/'configs/training'/f'{key}.json')
    if overrides is not None and not isinstance(overrides,dict):
        raise ValueError('Model override must be a JSON object')
    if overrides:
        unknown = set(overrides)-set(cfg)
        if unknown:
            raise ValueError('Unknown settings: '+str(sorted(unknown)))
        cfg.update(overrides)
    cfg.update(model_key=key, model_name=MODELS[key], **registry()[MODELS[key]])
    cfg.update(settings_version=SETTINGS_VERSION,
               image_policy='approved_crop' if cfg['model_family']=='anomaly' else 'original_full')
    return validate_settings(cfg)


def source_root(cfg):
    if cfg['source_dir']:
        return Path(cfg['source_dir']).expanduser().resolve()
    key = SOURCE_KEYS.get(cfg['model_key'])
    return ROOT/'outputs/training_sources_v1'/key/'source' if key else None


def verify_sources(cfg):
    """공식 clone은 Commit/수정 여부, 텍스트 스냅샷은 모든 파일 해시를 확인한다."""
    root = source_root(cfg)
    if root is None:
        return {'status':'UNVERIFIED_INSTALLED_VS_PINNED_SOURCE', 'source_commit':cfg['official_commit']}
    if not root.is_dir():
        raise FileNotFoundError(f'BLOCKED: source missing: {root}')
    import subprocess
    if (root/'.git').exists():
        sha = subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD'],text=True).strip()
        dirty = subprocess.check_output(['git','-C',str(root),'status','--porcelain','--untracked-files=all'],text=True).strip()
        # Python이 생성한 bytecode만 허용한다. 추적 소스/추가 Python 소스 변경은 계속 거부한다.
        dirty = '\n'.join(line for line in dirty.splitlines() if not (line.startswith('?? ') and '__pycache__' in Path(line[3:]).parts and line.endswith('.pyc')))
        if sha != cfg['official_commit'] or dirty:
            raise ValueError('Pinned source commit mismatch or modified official source')
        return {'commit':sha,'kind':'git'}
    meta_path = root.parent/'manifest.json'
    meta = json.loads(meta_path.read_text())
    if meta['commit'] != cfg['official_commit'] or not meta.get('files') or meta['repo'] != cfg['official_repo'].removeprefix('https://github.com/'):
        raise ValueError('Source snapshot commit mismatch')
    seen=set()
    for f in meta['files']:
        p=(root/f['path']).resolve()
        if f['path'] in seen or not p.is_relative_to(root.resolve()) or file_sha256(p)!=f['sha256']:
            raise ValueError('Official source checksum mismatch: '+f['path'])
        seen.add(f['path'])
    return {'commit':meta['commit'], 'snapshot_sha256':file_sha256(meta_path), 'files':len(meta['files'])}


def weight_path(cfg, *, required=True):
    value = cfg.get('weights') or os.environ.get('MV_WEIGHTS_'+cfg['model_key'].upper())
    if not value:
        if required:
            raise FileNotFoundError('BLOCKED: local pretrained weights required; set MV_WEIGHTS_'+cfg['model_key'].upper())
        return None
    path=Path(value).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError('BLOCKED: weights file missing: '+str(path))
    if cfg.get('weights_sha256') and file_sha256(path)!=cfg['weights_sha256']:
        raise ValueError('Pretrained weight SHA256 mismatch')
    return path


def python_path(key):
    # resolve()는 venv python symlink를 시스템 Python으로 바꾸므로 사용하지 않는다.
    return Path(os.path.abspath(Path(os.environ.get('MV_PYTHON_'+key.upper(), str(ROOT/'environments'/key/'.venv/bin/python'))).expanduser()))
