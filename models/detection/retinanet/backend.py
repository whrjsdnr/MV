"""TorchVision RetinaNet. 생성 시 다운로드를 유발하는 weights enum은 사용하지 않는다."""
from pathlib import Path
import torch
from torchvision.models.detection import retinanet_resnet50_fpn
from .preprocessing import prepare_batch
from mv_analysis.experiments.bridge import restore_detection_prediction
from models._shared.diagnostics import tensor_stats, sample_evidence
from torchvision.ops import box_iou


def build_model(config, class_count=8, *, random_init_for_test=False):
    model = retinanet_resnet50_fpn(weights=None, weights_backbone=None,
        num_classes=class_count+1, min_size=config['input_resolution'], max_size=1333,
        score_thresh=.001, nms_thresh=.5, detections_per_img=100)
    if not random_init_for_test and config.get('initialization')!='random':
        path = Path(config['weights'] or '')
        if not path.is_file():
            raise FileNotFoundError('RetinaNet requires local TorchVision RetinaNet state_dict')
        state = torch.load(path, map_location='cpu', weights_only=True)
        state = state.get('model', state)
        # COCO 91-class 마지막 분류층만 새 클래스 수에 맞게 초기화한다.
        # Backbone/FPN/회귀층 누락을 조용히 허용하지 않는다.
        ignored = {'head.classification_head.cls_logits.weight', 'head.classification_head.cls_logits.bias'}
        state = {k:v for k,v in state.items() if k not in ignored}
        missing, unexpected = model.load_state_dict(state, strict=False)
        if set(missing) != ignored or unexpected:
            raise ValueError(f'Incompatible RetinaNet checkpoint: {missing}, {unexpected}')
    return model


class Backend:
    def __init__(self, config, classes, device):
        self.config, self.classes, self.device = config, classes, device
        self.model = build_model(config, len(classes)).to(device)

    def prepare(self, train):
        pass  # 사전 통계를 학습하지 않는 공식 검출 모델이다.

    def calibrate_maps(self, validation):
        pass

    def loss(self, samples):
        images, targets = prepare_batch(samples, self.device)
        if any((t['labels'] > len(self.classes)).any() for t in targets):
            raise ValueError('Class ID outside canonical mapping')
        self.last_diagnostics = dict(samples=sample_evidence(samples), heads={}, anchors=[])
        def head_stats(module, args, output):
            self.last_diagnostics['heads'] = {k:tensor_stats(v) for k,v in output.items()}
        handle = self.model.head.register_forward_hook(head_stats)
        original = self.model.compute_loss
        def audited_loss(targets, outputs, anchors):
            # 공식 matcher를 그대로 관찰하며 Target이나 loss 계산은 변경하지 않는다.
            for target, anchor in zip(targets, anchors):
                matched = (self.model.proposal_matcher(box_iou(target['boxes'], anchor))
                           if len(target['boxes']) else torch.full((len(anchor),), -1, device=anchor.device))
                self.last_diagnostics['anchors'].append(dict(total=len(anchor),
                    positive=int((matched>=0).sum()), negative=int((matched==-1).sum()),
                    ignored=int((matched==-2).sum()), transformed_boxes=target['boxes'].detach().cpu().tolist()))
            return original(targets, outputs, anchors)
        self.model.compute_loss = audited_loss
        try:
            return self.model(images, targets)
        finally:
            handle.remove()
            self.model.compute_loss = original

    @torch.inference_mode()
    def predict(self, sample):
        images, _ = prepare_batch([sample], self.device)
        pred = self.model(images)[0]
        keep = pred['labels'] > 0
        return restore_detection_prediction(sample, boxes=pred['boxes'][keep].cpu().numpy(),
            labels=pred['labels'][keep].cpu().numpy(), scores=pred['scores'][keep].cpu().numpy(),
            box_format='xyxy', normalized=False, class_offset=1, class_ids=self.classes.values())

    def benchmark_input(self, sample):
        return [sample['image'].to(self.device)]
