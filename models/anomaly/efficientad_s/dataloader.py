"""품목별 OK Train / OK+NG Validation·Test. Test는 학습 통계에 사용하지 않는다."""
from models._shared.data import datasets


def build_datasets(release, config, category):
    return datasets(release, config, category=category)
