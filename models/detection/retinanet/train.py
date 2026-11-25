"""RetinaNet 원본 D1 학습 진입점."""
from models._shared.data import open_release
from models._shared.runtime import train_torch, seed_all
from .backend import Backend
from .dataloader import build_datasets


def run(request):
    config=request['settings'];seed_all(config['seed'])
    with open_release(request) as release:
        data=build_datasets(release,config)
        backend=Backend(config,release.classes['yolo'],request['device'])
        return train_torch(request,release,data,backend,suffix='D1')
