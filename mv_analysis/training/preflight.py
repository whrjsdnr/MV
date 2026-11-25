"""읽기 전용 사전 점검. 패키지 설치/다운로드/이미지 수정은 수행하지 않는다."""
import csv
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

from mv_analysis.data.team_release import extract_release, verify_release
from mv_analysis.experiments.contracts import file_sha256, digest
from .settings import ROOT, verify_sources, weight_path


def validate_data_release(source, data_root=None, expected_zip_sha256=None):
    """v2 ZIP은 임시 폴더에만 해제한다. 기존 검증기로 해시/좌표/클래스/Split을 전수 확인한다."""
    source=Path(source).expanduser().resolve()
    if source.is_file():
        with tempfile.TemporaryDirectory(prefix='mv-release-check-') as tmp:
            root=extract_release(source, Path(tmp)/'extracted', expected_zip_sha256)
            result=_validate_directory(root, data_root)
        result.update(source=str(source), zip_sha256=file_sha256(source), source_kind='zip')
        return result
    if expected_zip_sha256:
        raise ValueError('--release-sha256 applies to a ZIP file only')
    result=_validate_directory(source, data_root)
    result.update(source=str(source), source_kind='directory', zip_sha256=None)
    return result


def _validate_directory(root, data_root):
    meta=json.loads((root/'release.json').read_text())
    if meta.get('release_id')!='MV_TEAM_DATA_RELEASE_v2':
        raise ValueError('This runner requires MV_TEAM_DATA_RELEASE_v2')
    checks=verify_release(root)
    if meta.get('anomaly_image_policy')!='approved_crop' or meta.get('detection_image_policy')!='original_full':
        raise ValueError('v2 image policy mismatch')
    hashes={name:file_sha256(root/name) for name in ('release.json','manifests/canonical.csv',
        'manifests/eligibility.csv','annotations/defect_boxes.csv','annotations/product_boxes.csv','schemas/class_mapping.json')}
    sample=[]; categories=set()
    if data_root is not None:
        data_root=Path(data_root).expanduser().resolve()
        if not data_root.is_dir():
            raise FileNotFoundError('Data root does not exist: '+str(data_root))
        with (root/'manifests/canonical.csv').open(newline='') as f:
            for row in csv.DictReader(f):
                if row['category'] in categories:
                    continue
                categories.add(row['category'])
                path=(data_root/row['source_relative_path']).resolve()
                if not path.is_relative_to(data_root) or not path.is_file() or not os.access(path,os.R_OK):
                    raise FileNotFoundError('Original image missing/unreadable: '+row['source_relative_path'])
                sample.append(row['image_id'])
    return dict(status='VERIFIED', release_id=meta['release_id'], images=checks['images'],
        manifest_sha256=hashes['manifests/canonical.csv'], bindings_sha256=digest(hashes), hashes=hashes,
        validation=checks, data_root=str(data_root) if data_root else None,
        source_access=dict(status='SAMPLED_EXISTENCE_ONLY' if sample else 'NOT_CHECKED',
                           sample_count=len(sample), image_ids=sample, decoding='NOT_CHECKED'))


PROBE = r'''
import json,platform,sys,importlib.metadata as m,importlib.util,os
result=dict(python=sys.version.split()[0],executable=sys.executable,prefix=sys.prefix,base_prefix=sys.base_prefix,
            platform=platform.platform(),cpu_count=os.cpu_count(),packages={},errors=[],cuda_available=False)
for name in ['torch','torchvision','numpy','pandas','scipy','scikit-learn','matplotlib','opencv-python','pycocotools','psutil','PyYAML','ultralytics','easydict','lmdb','faster-coco-eval']:
    try: result['packages'][name]=m.version(name)
    except m.PackageNotFoundError: result['packages'][name]=None
try:
    import torch
    result.update(torch_version=torch.__version__,cuda_version=torch.version.cuda,cuda_available=torch.cuda.is_available(),
                  gpu_names=[torch.cuda.get_device_name(i) for i in range(torch.cuda.device_count())])
    result['cpu_tensor_ok']=bool(torch.tensor([1.,2.]).sum().item()==3.)
except Exception as e: result['errors'].append(type(e).__name__+': '+str(e))
try:
    import psutil
    result['ram_total_bytes']=psutil.virtual_memory().total
    result['ram_available_bytes']=psutil.virtual_memory().available
except ImportError: pass
print(json.dumps(result,allow_nan=False))
'''


def probe_environment(python, requested_device='auto', timeout=45):
    """지정 모델 환경 안에서 PyTorch를 실제 import한다. 부모 환경의 CUDA를 대신 사용하지 않는다."""
    if requested_device not in ('auto','cpu','cuda') and not requested_device.startswith('cuda:'):
        raise ValueError('Invalid device')
    python=Path(python)
    if not python.is_file() or not os.access(python,os.X_OK):
        raise FileNotFoundError('Independent Python missing: '+str(python))
    proc=subprocess.run([str(python),'-c',PROBE],cwd=ROOT,text=True,capture_output=True,timeout=timeout)
    if proc.returncode:
        raise RuntimeError('Environment probe failed: '+proc.stderr[-2000:])
    result=json.loads(proc.stdout)
    if result['errors']:
        raise RuntimeError('; '.join(result['errors']))
    device=('cuda' if result['cuda_available'] else 'cpu') if requested_device=='auto' else requested_device
    if device.startswith('cuda'):
        index=int(device.split(':')[1]) if ':' in device else 0
        if not result['cuda_available'] or not 0<=index<len(result['gpu_names']):
            raise ValueError('Requested CUDA device unavailable in selected model environment')
    result['resolved_device']=device
    # 사용 가능한 RAM은 변동값이다. Resume 비교는 환경 정체성/버전/장치만 사용한다.
    identity={k:result.get(k) for k in ('python','prefix','platform','packages','gpu_names','resolved_device')}
    result['identity_sha256']=digest(identity)
    return result


def check_model(cfg, python, device, output_root, *, mode):
    checks={}; blockers=[]
    output_root=Path(output_root)
    free=shutil.disk_usage(output_root).free
    checks['disk_free_bytes']=free
    if free < cfg['minimum_free_gb']*1024**3:
        blockers.append('INSUFFICIENT_DISK_SPACE')
    try:
        checks['environment']=probe_environment(python,device)
    except (OSError,ValueError,RuntimeError,subprocess.TimeoutExpired) as e:
        blockers.append('ENVIRONMENT: '+str(e))
    if mode!='smoke':
        try:
            checks['source']=verify_sources(cfg)
        except (OSError,ValueError,KeyError) as e:
            blockers.append('OFFICIAL_SOURCE: '+str(e))
        try:
            if cfg['model_key']=='retinanet' and cfg.get('initialization')=='random':
                checks['weights']={'initialization':'EXPLICIT_RANDOM_NO_PRETRAINING'}
            else:
                weight=weight_path(cfg)
                checks['weights']={'path':str(weight),'sha256':file_sha256(weight)}
        except (OSError,ValueError) as e:
            blockers.append('WEIGHTS: '+str(e))
        # 이번 작업 범위는 실행 계약까지다. 모델 구현이 없음을 반드시 실행을 막는 이유로 남긴다.
        from .backends import limitations
        blockers.extend(limitations(cfg))
        packages=checks.get('environment',{}).get('packages',{})
        if cfg['model_key']=='yolo11' and packages.get('ultralytics')!='8.4.211':
            blockers.append('ULTRALYTICS_8.4.211_REQUIRED')
        if cfg['model_key']=='retinanet' and not packages.get('torchvision'):
            blockers.append('TORCHVISION_REQUIRED')
        if checks.get('environment',{}).get('resolved_device')=='cpu' and not cfg['allow_cpu_training']:
            blockers.append('CPU_FULL_TRAINING_DISABLED')
    return dict(status='BLOCKED' if blockers else 'VERIFIED', blockers=blockers, **checks)
