"""고정 Ultralytics 추론 API. 모델 결과는 원본 좌표이므로 Crop 원점을 더하지 않는다."""
import numpy as np
from mv_analysis.experiments.bridge import restore_detection_prediction

PINNED_VERSION='8.4.211'


def build_model(config):
    import ultralytics
    if ultralytics.__version__!=PINNED_VERSION: raise ValueError('Ultralytics version mismatch')
    from ultralytics import YOLO
    from pathlib import Path
    if not Path(config['weights'] or '').is_file(): raise FileNotFoundError('Local YOLO11 weight required')
    return YOLO(config['weights'])


class Backend:
    def __init__(self, config, classes, device, yolo):
        self.config,self.classes,self.device,self.yolo=config,classes,device,yolo

    def predict(self, sample):
        if sample['metadata']['image_policy']!='original_full': raise ValueError('YOLO D1 requires original_full')
        # NumPy 입력은 Ultralytics의 BGR 계약이다. 내부 LetterBox/Normalize를 중복하지 않는다.
        image=(sample['image'].permute(1,2,0).numpy()*255).round().astype(np.uint8)[:,:,::-1].copy()
        result=self.yolo.predict(image,device=self.device,imgsz=self.config['input_resolution'],
            conf=.001,iou=.7,max_det=100,verbose=False,save=False)[0]
        return restore_detection_prediction(sample,boxes=result.boxes.xyxy.cpu().numpy(),
            labels=result.boxes.cls.cpu().numpy(),scores=result.boxes.conf.cpu().numpy(),
            box_format='xyxy',normalized=False,class_offset=0,class_ids=self.classes.values())
