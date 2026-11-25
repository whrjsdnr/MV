"""모델별 구현 진입점. 빈 설정의 과거 TODO 호출 계약은 유지한다."""
from models.detection.retinanet.train import run


def build_model(config):
    if not config:
        raise NotImplementedError('빈 TODO 설정에는 모델을 생성하지 않습니다. 고정 모델 설정을 전달하세요.')
    from models.detection.retinanet.backend import build_model as create
    return create(config)
