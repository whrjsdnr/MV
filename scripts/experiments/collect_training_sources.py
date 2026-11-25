"""고정 Commit의 텍스트 소스만 수집한다. 데이터/가중치/외부 코드는 수정하지 않는다."""
import concurrent.futures
import hashlib
import json
from pathlib import Path
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
KEYS = ['efficientad', 'uniad', 'hvqtrans', 'rtdetrv2', 'yolo11']


def collect(key):
    old = ROOT / 'outputs/model_sources_20261112_v1' / key
    meta = json.loads((old / 'manifest.json').read_text())
    paths = json.loads((old / 'tree_paths.json').read_text())
    out = ROOT / 'outputs/training_sources_v1' / key
    selected = []
    for p in paths:
        if '__pycache__' in p or not p.endswith(('.py', '.yaml', '.yml', '.txt', '.md')) and 'LICENSE' not in p:
            continue
        include = p in ('README.md', 'LICENSE', 'LICENSE.txt', 'requirements.txt', 'pyproject.toml', 'common.py', 'efficientad.py')
        if key in ('uniad', 'hvqtrans'):
            include |= p.startswith(('models/', 'utils/', 'tools/', 'experiments/MVTec-AD/'))
        if key == 'rtdetrv2':
            include |= p.startswith(('rtdetrv2_pytorch/src/', 'rtdetrv2_pytorch/configs/', 'rtdetrv2_pytorch/tools/')) or p == 'rtdetrv2_pytorch/requirements.txt'
        if key == 'yolo11':
            include |= p in ('ultralytics/engine/trainer.py', 'ultralytics/engine/model.py', 'ultralytics/models/yolo/detect/train.py', 'ultralytics/models/yolo/detect/val.py', 'ultralytics/__init__.py')
        if include:
            selected.append(p)
    def fetch(p):
        dst = out / 'source' / p
        if not dst.exists():
            cached = old / 'source' / p
            data = cached.read_bytes() if cached.exists() else urllib.request.urlopen(
                f'https://raw.githubusercontent.com/{meta["repo"]}/{meta["commit"]}/{p}', timeout=45).read()
            data.decode('utf-8')
            if len(data) > 2_000_000:
                raise ValueError('Unexpected non-source payload')
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(data)
        return dict(path=p, sha256=hashlib.sha256(dst.read_bytes()).hexdigest())
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        files = list(pool.map(fetch, selected))
    result = dict(repo=meta['repo'], commit=meta['commit'], files=files, weights_downloaded=False)
    (out / 'manifest.json').write_text(json.dumps(result, indent=2))
    print(key, len(files), meta['commit'], flush=True)


if __name__ == '__main__':
    for key in KEYS:
        collect(key)
