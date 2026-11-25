"""품목별 정상 기준을 각각 학습한다. C1~C5는 공통 품목 모델에 보존한다."""
from models._shared.data import open_release
from models._shared.runtime import train_torch, seed_all
from .backend import Backend
from .dataloader import build_datasets


def run(request):
    config=request['settings'];results=[]
    with open_release(request) as release:
        categories=config['categories'] or sorted(release.canonical.category.unique())
        for category in categories:
            seed_all(config['seed'])
            data=build_datasets(release,config,category)
            backend=Backend(config,release.classes['yolo'],request['device'])
            result=train_torch(request,release,data,backend,suffix=category)
            results.append(result)
            if result['status']!='COMPLETED': return result
        return dict(status='COMPLETED',training_executed=True,categories=categories,results=results,
                    steps=sum(r['steps'] for r in results),report=results[-1]['report'],report_sha256=results[-1]['report_sha256'])
