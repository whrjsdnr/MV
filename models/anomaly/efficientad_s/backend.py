"""고정 nelson1425 소스의 PDN-S/AE 및 손실식 연결. 이 저장소는 논문 저자의 공식 구현이 아니다."""
import importlib.util
import torch
from torch import nn
from torch.nn import functional as F
from mv_analysis.training.settings import source_root, verify_sources
from mv_analysis.experiments.bridge import restore_anomaly_prediction
from .preprocessing import prepare_image
from models._shared.diagnostics import tensor_stats


class CalibrationError(ValueError):
    """실패 map/분포를 보존하고 기존 calibration buffer를 변경하지 않는다."""
    def __init__(self, diagnostics):
        self.diagnostics = diagnostics
        super().__init__('Degenerate validation map quantiles: ' +
                         ', '.join(k for k, v in diagnostics.items() if not v['valid']))


def calibration_quantiles(maps):
    """고정 소스의 float32 q90/q99.5 그대로 검증. epsilon/다른 분위수로 우회하지 않는다."""
    diagnostics, values = {}, []
    for name, value in maps.items():
        value = value.detach().flatten().cpu()
        stat = tensor_stats(value)
        valid = value.numel() > 0 and stat['nonfinite'] == 0
        q = torch.quantile(value, torch.tensor([.9, .995], dtype=value.dtype)) if valid else None
        stat.update(q90=float(q[0]) if q is not None else None,
                    q995=float(q[1]) if q is not None else None,
                    valid=bool(valid and q[1] > q[0]))
        if q is not None:
            stat['double_quantiles'] = torch.quantile(value.double(), torch.tensor([.9, .995], dtype=torch.float64)).tolist()
            values.append(q)
        diagnostics[name] = stat
    if not diagnostics or not all(v['valid'] for v in diagnostics.values()):
        raise CalibrationError(diagnostics)
    return torch.cat(values), diagnostics


def source_module(config):
    verify_sources(config)
    spec = importlib.util.spec_from_file_location('mv_pinned_efficientad_common', source_root(config)/'common.py')
    module = importlib.util.module_from_spec(spec)
    import sys
    previous=sys.dont_write_bytecode
    try:
        sys.dont_write_bytecode=True
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode=previous
    return module


def build_model(config):
    if not config.get('weights'):
        raise ValueError('Teacher weights are required; random teacher is forbidden')
    return Network(source_module(config), config['weights'])


class Network(nn.Module):
    def __init__(self, source, weights):
        super().__init__()
        self.teacher = source.get_pdn_small(384)
        # 실제 Teacher 파일 없이는 랜덤 Teacher로 대체하지 않는다.
        self.teacher.load_state_dict(torch.load(weights, map_location='cpu', weights_only=True))
        self.teacher.requires_grad_(False)
        self.student = source.get_pdn_small(768)
        self.autoencoder = source.get_autoencoder(384)
        self.register_buffer('teacher_mean', torch.zeros(1,384,1,1))
        self.register_buffer('teacher_std', torch.ones(1,384,1,1))
        self.register_buffer('quantiles', torch.tensor([0.,1.,0.,1.]))

    def train(self, mode=True):
        super().train(mode)
        self.teacher.eval()
        return self

    def raw_maps(self, x):
        teacher = (self.teacher(x)-self.teacher_mean)/self.teacher_std
        student = self.student(x)
        return ((teacher-student[:,:384]).square().mean(1,keepdim=True),
                (self.autoencoder(x)-student[:,384:]).square().mean(1,keepdim=True))

    def forward(self, x):
        st, ae = self.raw_maps(x)
        a,b,c,d = self.quantiles
        combined = .05*((st-a)/(b-a)+(ae-c)/(d-c))
        return F.interpolate(F.pad(combined,(4,4,4,4)), (256,256), mode='bilinear', align_corners=False)


class Backend:
    def __init__(self, config, classes, device):
        self.config, self.device, self.classes = config, device, classes
        self.model = Network(source_module(config), config['weights']).to(device)

    @torch.no_grad()
    def prepare(self, train):
        """정상 Train만 두 번 순회해 채널 통계를 계산한다. 원본 소스와 같은 모집단 분산이다."""
        self.model.eval()
        total = torch.zeros_like(self.model.teacher_mean)
        for sample in train:
            if sample['status'] != 'OK':
                raise ValueError('NG leaked into teacher statistics')
            total += self.model.teacher(self.input(sample)).mean((0,2,3), keepdim=True)
        self.model.teacher_mean.copy_(total/len(train))
        total.zero_()
        for sample in train:
            values = self.model.teacher(self.input(sample))
            total += (values-self.model.teacher_mean).square().mean((0,2,3),keepdim=True)
        std = (total/len(train)).sqrt()
        if not torch.isfinite(std).all() or (std<=0).any():
            raise ValueError('Degenerate Teacher statistics')
        self.model.teacher_std.copy_(std)

    def input(self, sample, augment=False):
        return prepare_image(sample, augment=augment).unsqueeze(0).to(self.device)

    def loss(self, samples):
        if len(samples) != 1:
            raise ValueError('Pinned EfficientAD baseline uses batch_size=1')
        x = self.input(samples[0]); aug = self.input(samples[0], True)
        m = self.model
        with torch.no_grad():
            teacher = (m.teacher(x)-m.teacher_mean)/m.teacher_std
            teacher_aug = (m.teacher(aug)-m.teacher_mean)/m.teacher_std
        distance = (teacher-m.student(x)[:,:384]).square()
        # 하드마이닝 분위수는 기본 0.999(공식 고정값). 균일 배경이 넓은 데이터셋에서
        # 하위 픽셀의 감독 부재로 학생이 상수로 붕괴하면 공식 calibration이 q90==q99.5를 거부한다.
        mining = float(self.config.get('hard_mining_quantile', 0.999))
        hard = distance[distance >= torch.quantile(distance, mining)].mean()
        ae = m.autoencoder(aug)
        return {'distillation_loss': hard, 'reconstruction_loss': (teacher_aug-ae).square().mean(),
                'student_ae_loss': (ae-m.student(aug)[:,384:]).square().mean()}

    @torch.no_grad()
    def calibrate_maps(self, validation):
        """공식 q90/q99.5를 Validation OK에서만 계산한다. Test에는 고정값을 쓴다."""
        st, ae, evidence = [], [], []
        self.model.eval()
        for sample in validation:
            if sample['status'] == 'OK':
                x = self.input(sample)
                a,b = self.model.raw_maps(x)
                evidence.append(dict(image_id=sample['image_id'], input=tensor_stats(x),
                                     st=tensor_stats(a), ae=tensor_stats(b)))
                st.append(a.flatten().cpu()); ae.append(b.flatten().cpu())
        self.calibration_diagnostics = dict(images=evidence, ok_images=len(evidence), status='FAILED')
        try:
            q, stats = calibration_quantiles(dict(st=torch.cat(st) if st else torch.empty(0),
                                                 ae=torch.cat(ae) if ae else torch.empty(0)))
        except CalibrationError as exc:
            self.calibration_diagnostics['maps'] = exc.diagnostics
            raise
        self.calibration_diagnostics.update(maps=stats, status='VALID')
        self.model.quantiles.copy_(q.to(self.device))

    @torch.inference_mode()
    def predict(self, sample):
        values = self.model(self.input(sample))[0,0].cpu().numpy()
        aligned = dict(sample, image=torch.empty(3,256,256))
        return restore_anomaly_prediction(aligned, score=float(values.max()), score_map=values)

    def benchmark_input(self, sample):
        return self.input(sample)
