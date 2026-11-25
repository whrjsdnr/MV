"""D1 적격성·원본 좌표를 유지하는 v2 로더 연결."""
from models._shared.data import datasets


def build_datasets(release, config):
    return datasets(release, config)
