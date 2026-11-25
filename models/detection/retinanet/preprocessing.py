"""RGB 0..1 원본을 공식 RetinaNet 내부 Resize/Normalize에 한 번만 전달한다."""
import torch


def prepare_batch(samples, device):
    images, targets = [], []
    for sample in samples:
        if sample['metadata']['image_policy'] != 'original_full':
            raise ValueError('RetinaNet D1 must use original_full')
        if not sample['detection_trainable']:
            raise ValueError('NG missing/empty/invalid annotations are not negatives')
        image = sample['image']
        if (image.dtype != torch.float32 or image.ndim != 3 or image.shape[0] != 3
                or not torch.isfinite(image).all() or image.min() < 0 or image.max() > 1):
            raise ValueError('Expected unnormalized RGB float32 [0,1]')
        boxes, labels = sample['boxes'], sample['labels']
        h, w = image.shape[-2:]
        if (boxes.ndim != 2 or boxes.shape[1] != 4 or not torch.isfinite(boxes).all()
                or not (boxes[:, 2:] > boxes[:, :2]).all() or (boxes < 0).any()
                or (boxes[:, [0, 2]] > w).any() or (boxes[:, [1, 3]] > h).any()):
            raise ValueError('Invalid original XYXY boxes: ' + sample['image_id'])
        if labels.dtype != torch.int64 or labels.shape != (len(boxes),) or (labels < 0).any():
            raise ValueError('Invalid canonical labels: ' + sample['image_id'])
        images.append(image.to(device))
        # 프로젝트의 canonical 0..N-1을 TorchVision 1..N으로 옮긴다.
        # 0번 출력은 미사용 background 슬롯이며 결함 평가에서 제외한다.
        targets.append({'boxes': sample['boxes'].to(device),
                        'labels': sample['labels'].to(device) + 1})
    return images, targets
