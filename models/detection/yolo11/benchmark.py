"""YOLO의 LetterBox/float 변환·network·NMS를 분리해 CPU에서도 측정한다."""
import numpy as np
import torch
from mv_analysis.experiments.benchmark import benchmark


def measure(backend, sample, checkpoint):
    from ultralytics.data.augment import LetterBox
    from ultralytics.utils.nms import non_max_suppression
    cfg=backend.config
    letterbox=LetterBox(new_shape=(cfg['input_resolution'],)*2,auto=False)
    image=sample['image'].permute(1,2,0).numpy()
    image=(image*255).round().astype(np.uint8)
    def preprocess(batch):
        # 이미 디코딩된 RGB에서 측정한다. 실제 디스크 I/O 시간은 포함하지 않는다.
        padded=letterbox(image=batch[0])
        return torch.from_numpy(padded.transpose(2,0,1).copy()).unsqueeze(0).to(backend.device).float()/255
    model=backend.yolo.model.to(backend.device).float().eval()
    result=benchmark(model,[[image]],input_ids=[sample['image_id']],device=backend.device,
        preprocess=preprocess,postprocess=lambda p:non_max_suppression(p,conf_thres=.001,iou_thres=.7,
            max_det=100,nc=len(backend.classes)),checkpoint=checkpoint,batch_size=1,
        warmup=cfg['benchmark_warmup'],repetitions=cfg['benchmark_repetitions'])
    result['scope_note']='Decoded RGB -> official LetterBox -> float01 -> network -> NMS. Disk decoding excluded.'
    return result
