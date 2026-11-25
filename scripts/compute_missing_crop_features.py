"""미계산 이미지의 기존 GrabCut Quality Gate 특징만 체크포인트로 생성한다.

원본·마스크·기존 CSV·승인 원장은 수정하지 않는다. YOLO 추론/학습/다운로드를 하지 않는다.
기본은 CPU 1 worker. --max-new-images로 소량 검증하고 같은 출력에 --resume으로 이어간다.
출력은 자동 Crop 후보의 근거이며 사람 승인이나 독립 제품 보존 검증이 아니다.
"""
import os
os.environ.setdefault('OPENBLAS_NUM_THREADS','1')
os.environ.setdefault('OMP_NUM_THREADS','1')
from pathlib import Path
import argparse
import csv
import hashlib
import json
import sys
import time
from concurrent.futures import ProcessPoolExecutor
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
ROOT=Path(__file__).resolve().parents[1]


def sha(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def worker(item):
    """이미지 경로와 크기만 전달한다. 라벨/마스크는 작업자 입력에도 포함하지 않는다."""
    import cv2
    import numpy as np
    from mv_analysis.adaptive_crop_gate import extract_features
    path,relative,width,height=item;start=time.monotonic()
    try:
        stat=Path(path).stat()
        raw=Path(path).read_bytes();image=cv2.imdecode(np.frombuffer(raw,np.uint8),cv2.IMREAD_COLOR)
        if image is None or image.shape[:2]!=(height,width):raise ValueError('Image decode/size mismatch')
        if width!=1024 or height!=1024:raise ValueError('Existing feature extractor requires 1024x1024')
        features=extract_features(image)
        after=Path(path).stat()
        if (stat.st_size,stat.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):raise ValueError('Source changed during feature extraction')
        return dict(image_path=relative,features=features,source_hash=hashlib.sha256(raw).hexdigest(),
                    source_fingerprint=f'stat-v1:{stat.st_size}:{stat.st_mtime_ns}',
                    elapsed_ms=(time.monotonic()-start)*1000,error=None)
    except Exception as exc:
        return dict(image_path=relative,features=None,source_hash=None,
                    elapsed_ms=(time.monotonic()-start)*1000,error=repr(exc))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--data-root',type=Path,default=ROOT/'dataset')
    parser.add_argument('--workers',type=int,choices=[1,2,3],default=1)
    parser.add_argument('--max-new-images',type=int)
    parser.add_argument('--resume',action='store_true')
    args=parser.parse_args()
    if args.max_new_images is not None and args.max_new_images<1:parser.error('max-new-images must be positive')
    canonical=ROOT/'outputs/team_data_release_v2/MV_TEAM_DATA_RELEASE_v2/manifests/canonical.csv'
    cache=ROOT/'outputs/adaptive_crop_gate_v1/checkpoints/features.jsonl'
    out=args.output.resolve()
    config=dict(source_manifest_sha256=sha(canonical),existing_cache_sha256=sha(cache),
                feature_extractor_sha256=sha(ROOT/'mv_analysis/adaptive_crop_gate.py'),
                object_helper_sha256=sha(ROOT/'mv_analysis/object_aware_crop.py'),
                segmentation_sha256=sha(ROOT/'mv_analysis/background_brightness.py'),
                data_root=str(args.data_root.resolve()),coordinate_system='1024_ORIGINAL_XYXY_EXCLUSIVE')
    def write_json(name,data):
        temp=out/(name+'.tmp');temp.write_text(json.dumps(data,indent=2,allow_nan=False));os.replace(temp,out/name)
    if args.resume:
        if json.loads((out/'config.json').read_text())!=config:raise ValueError('Resume bindings changed')
    else:
        out.mkdir(parents=True,exist_ok=False);write_json('config.json',config)
    done=set()
    for p in [cache,out/'features.jsonl']:
        if not p.exists():continue
        with p.open() as stream:
            for line in stream:
                r=json.loads(line)
                if r['image_path'] in done:raise ValueError('Duplicate checkpoint image')
                done.add(r['image_path'])
    todo=[]
    with canonical.open() as stream:
        for row in csv.DictReader(stream):
            if row['source_relative_path'] not in done:
                todo.append((str(args.data_root/row['source_relative_path']),row['source_relative_path'],
                             int(row['original_width']),int(row['original_height'])))
    remaining=len(todo)
    if args.max_new_images:todo=todo[:args.max_new_images]
    start=time.monotonic();success=errors=0
    import fcntl
    with (out/'run.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        with ProcessPoolExecutor(max_workers=args.workers) as pool,(out/'features.jsonl').open('a') as stream:
            # 각 묶음의 최대 대기 작업을 제한한다. 이미지 전체를 메모리에 올리지 않는다.
            for offset in range(0,len(todo),32):
                for record in pool.map(worker,todo[offset:offset+32]):
                    stream.write(json.dumps(record,allow_nan=False)+'\n')
                    success+=record['error'] is None;errors+=record['error'] is not None
                stream.flush();os.fsync(stream.fileno())
                progress=dict(success=success,errors=errors,new_processed=success+errors,
                    session_planned=len(todo),remaining_before_session=remaining,
                    remaining_after_session=remaining-success-errors,elapsed_seconds=time.monotonic()-start,
                    workers=args.workers,full_processing_complete=success+errors==remaining,
                    actual_crop_image_files=0)
                write_json('progress.json',progress);print(json.dumps(progress),flush=True)
    print('Checkpoint saved; existing metadata/approvals unchanged',flush=True)


if __name__=='__main__':main()
