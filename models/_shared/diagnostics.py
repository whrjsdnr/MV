"""학습 실패 증거를 JSON으로 보존한다. 비유한 값을 학습용 0으로 대체하지 않는다."""
import torch
import math


def tensor_stats(value):
    value = value.detach().double()
    finite = torch.isfinite(value)
    good = value[finite]
    return dict(shape=list(value.shape), count=value.numel(),
                nonfinite=int((~finite).sum()),
                minimum=float(good.min()) if good.numel() else None,
                maximum=float(good.max()) if good.numel() else None,
                mean=float(good.mean()) if good.numel() else None,
                std=float(good.std(unbiased=False)) if good.numel() else None)


def checked_losses(losses):
    """항목별 scalar/유한성 확인. 이상 항목 이름이 예외와 진단 파일에 남는다."""
    bad = [name for name, value in losses.items()
           if value.numel() != 1 or not torch.isfinite(value).all()]
    if not losses or bad:
        raise FloatingPointError('NONFINITE_OR_INVALID_LOSS: ' + ','.join(bad))
    total = sum(losses.values())
    if not torch.isfinite(total):
        raise FloatingPointError('NONFINITE_LOSS_SUM')
    return total


def sample_evidence(samples):
    def coordinates(boxes):
        return [[value if math.isfinite(value) else None for value in row]
                for row in boxes.detach().cpu().tolist()]
    return [dict(image_id=s['image_id'], image=tensor_stats(s['image']),
                 boxes=coordinates(s['boxes']),
                 labels=s['labels'].detach().cpu().tolist()) for s in samples]
