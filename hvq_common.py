"""hvq_best.pt (HVQ-Trans, Real-IAD 30분기) 공통 로더/엔진/스코어링.

체크포인트는 RuiyingLu/HVQ-Trans(고정 커밋 12fbfa9) 기반 커스텀 학습본이다.
스냅샷의 models/HVQ_TR_switch.py는 (a) 분기 15개 고정, (b) einops/lmdb 미설치 의존,
(c) 4블록 concat(272ch) 미반영 등으로 그대로 쓸 수 없어, 체크포인트 state_dict 키와
정확히 일치하는 별 구현을 제공한다(einops 없음, 벡터화된 eval 경로 포함).

아키텍처(체크포인트 shape에서 확정):
  efficientnet_b4(동결, outblocks [1,5,9,21], strides [2,4,8,16])
  → 4블록 14x14 업샘플 concat(272ch) → quantize_conv_t(272→256)
  → pos embed(learned) + TransformerEncoder 4x(d256) → VQ 코드북 5단계 x 30분기
  → TransformerDecoder_hierachy 4x(d512) → 분기별 output_proj(512→272)
  → 재구성 특징과의 L2 거리맵(14x14) → x16 업샘플 히트맵(224x224)
출력: 픽셀 히트맵 + 이미지 레벨 이상 점수(EvalImageMean = 히트맵 평균).
"""

from __future__ import annotations

import json
import sys
from importlib.util import find_spec
from pathlib import Path

MV_ROOT = Path(__file__).resolve().parent
IMG_EXTS = {".jpg", ".jpeg", ".png"}
SOURCE_CANDIDATES = (
    "outputs/training_sources_v1/hvqtrans/source",
    "outputs/model_sources_20261112_v1/hvqtrans/source",
)
MEAN = (0.485, 0.456, 0.406)
STD = (0.229, 0.224, 0.225)

_STUBBED = False


def log(msg: str) -> None:
    print(msg, flush=True)


def stub_missing_third_party() -> None:
    """einops/lmdb/distributed 미설치 의존성 스텁(transformer.py의 einops는 미사용 임포트)."""
    global _STUBBED
    if _STUBBED:
        return
    import types

    if find_spec("einops") is None:
        m = types.ModuleType("einops")

        def _rearrange(*a, **k):
            raise NotImplementedError("einops 스텁 — 벡터화 경로를 사용하세요")

        m.rearrange = _rearrange
        sys.modules["einops"] = m
    if find_spec("lmdb") is None:
        sys.modules["lmdb"] = types.ModuleType("lmdb")
    if find_spec("distributed") is None:
        d = types.ModuleType("distributed")
        d.all_reduce = lambda t, *a, **k: t
        sys.modules["distributed"] = d
    _STUBBED = True


def discover_source(root: Path = MV_ROOT, explicit: str | None = None) -> Path:
    root = Path(root)
    if explicit:
        p = Path(explicit)
        if not p.is_absolute():
            p = root / p
        if (p / "models" / "transformer.py").is_file():
            return p
        raise FileNotFoundError(f"--src 지정 경로에 models/transformer.py가 없습니다: {p}")
    for cand in SOURCE_CANDIDATES:
        p = root / cand
        if (p / "models" / "transformer.py").is_file() and (p / "models" / "backbones").is_dir():
            return p
    raise FileNotFoundError("HVQ-Trans 소스 스냅샷을 찾지 못했습니다. --src 로 source 경로를 지정하세요.")


def load_snapshot_modules(src_root: Path):
    """스냅샷에서 백본/트랜스포머 모듈을 로드한다.

    스냅샷 models/는 __init__.py가 없는 네임스페이스라, sys.path 방식으로는
    저장소 루트의 models/ 패키지에 선점된다. 'models'를 스냅샷 경로로 고정한다.
    """
    import types  # noqa: PLC0415

    import torch  # noqa: F401, PLC0415

    stub_missing_third_party()
    src_root = Path(src_root)
    pkg = types.ModuleType("models")
    pkg.__path__ = [str(src_root / "models")]
    sys.modules["models"] = pkg
    from models.backbones import efficientnet_b4  # noqa: PLC0415
    from models import transformer as T  # noqa: PLC0415
    return efficientnet_b4, T


def load_checkpoint_meta(checkpoint: Path) -> dict:
    import torch  # noqa: PLC0415

    ck = torch.load(str(checkpoint), map_location="cpu", weights_only=False)
    if "state_dict" not in ck:
        raise KeyError("state_dict가 없는 체크포인트입니다")
    return ck


def load_branch_mapping(checkpoint: Path) -> dict[str, int]:
    ck = load_checkpoint_meta(checkpoint)
    bm = ck.get("branch_mapping")
    if not isinstance(bm, dict):
        raise KeyError("branch_mapping이 없습니다 — 카테고리 분기 정보를 알 수 없습니다")
    return dict(bm)


def resolve_category(path, branch_mapping: dict[str, int], default: str | None = None) -> str | None:
    """파일명 접두어(<cat>_ / <cat>__) 또는 경로 부분에서 카테고리를 찾는다."""
    name = Path(path).name
    for cat in sorted(branch_mapping, key=len, reverse=True):
        if name.startswith(cat + "_"):
            return cat
    for part in Path(path).parts:
        if part in branch_mapping:
            return part
    return default


# ---------------------------------------------------------------------------
# 모델 구현 (체크포인트 키와 정확히 일치)
# ---------------------------------------------------------------------------
import torch  # noqa: E402
import torch.nn.functional as F  # noqa: E402
from torch import nn  # noqa: E402


class Quantize(nn.Module):
    def __init__(self, dim: int, n_embed: int):
        super().__init__()
        self.dim = dim
        self.n_embed = n_embed
        embed = torch.randn(dim, n_embed)
        self.register_buffer("embed", embed)
        self.register_buffer("cluster_size", torch.zeros(n_embed))
        self.register_buffer("embed_avg", embed.clone())

    def embed_code(self, embed_ind):
        return F.embedding(embed_ind, self.embed.transpose(0, 1))

    def forward(self, input):
        flatten = input.reshape(-1, self.dim)
        dist = (
            flatten.pow(2).sum(1, keepdim=True)
            - 2 * flatten @ self.embed
            + self.embed.pow(2).sum(0, keepdim=True)
        )
        _, embed_ind = (-dist).max(1)
        quantize = self.embed_code(embed_ind)
        embed_ind = embed_ind.view(*input.shape[:-1])
        diff = (quantize.detach() - input).pow(2).mean()
        quantize = input + (quantize - input).detach()  # straight-through (eval에선 동일)
        return quantize, diff, embed_ind


def _init_model(efficientnet_b4, T, num_branches=30, embed_dim=256, n_embed=512,
                feat_ch=272, feature_size=(14, 14)):
    class _M(nn.Module):
        pass
    m = _M()
    nn.Module.__init__(m)
    m.num_branches = num_branches
    m.embed_dim = embed_dim
    m.n_embed = n_embed
    m.channel = feat_ch
    m.feature_size = feature_size

    m.enc = efficientnet_b4(pretrained=False, outblocks=[1, 5, 9, 21], outstrides=[2, 4, 8, 16])
    m.quantize_conv_t = nn.Conv2d(feat_ch, embed_dim, 1)
    m.quantize_list_1 = nn.ModuleList([Quantize(embed_dim * 2, n_embed) for _ in range(num_branches)])
    m.quantize_list_2 = nn.ModuleList([Quantize(embed_dim * 2, n_embed) for _ in range(num_branches)])
    m.quantize_list_3 = nn.ModuleList([Quantize(embed_dim * 2, n_embed) for _ in range(num_branches)])
    m.quantize_list_4 = nn.ModuleList([Quantize(embed_dim * 2, n_embed) for _ in range(num_branches)])
    m.quantize_list_5 = nn.ModuleList([Quantize(embed_dim, n_embed) for _ in range(num_branches)])
    enc_layer = T.TransformerEncoderLayer(embed_dim, 8, dim_feedforward=1024, dropout=0.1,
                                          activation="relu", normalize_before=False)
    m.encoder = T.TransformerEncoder(enc_layer, 4, None, return_intermediate=True, return_src=True)
    m.pos_embed = T.build_position_embedding("learned", feature_size, embed_dim)
    dec_layer = T.Org_TransformerDecoderLayer(embed_dim * 2, feature_size, nhead=8,
                                              dim_feedforward=1024, dropout=0.1,
                                              activation="relu", normalize_before=False)
    m.decoder = T.TransformerDecoder_hierachy(dec_layer, 4, nn.LayerNorm(embed_dim * 2),
                                              return_intermediate=False)
    m.input_proj = nn.Linear(feat_ch, embed_dim)
    m.output_proj_list = nn.ModuleList([nn.Linear(embed_dim * 2, feat_ch) for _ in range(num_branches)])
    m.upsample = nn.UpsamplingBilinear2d(scale_factor=16)
    m.scale_factors = [0.125, 0.25, 0.5, 1.0]
    m.upsample_list = [nn.UpsamplingBilinear2d(scale_factor=s) for s in m.scale_factors]

    # 벡터화 eval용 스택 (non-persistent → state_dict에는 영향 없음)
    m.register_buffer("embed_stack_1", torch.zeros(1), persistent=False)
    m.register_buffer("embed_stack_2", torch.zeros(1), persistent=False)
    m.register_buffer("embed_stack_3", torch.zeros(1), persistent=False)
    m.register_buffer("embed_stack_4", torch.zeros(1), persistent=False)
    m.register_buffer("embed_stack_5", torch.zeros(1), persistent=False)
    m.register_buffer("proj_stack_w", torch.zeros(1), persistent=False)
    m.register_buffer("proj_stack_b", torch.zeros(1), persistent=False)

    m.prepare_eval = _make_prepare_eval(m)
    m.forward = _make_forward(m)
    m.forward_reference = _make_forward_reference(m)
    return m


def _make_prepare_eval(m):
    def prepare_eval():
        with torch.no_grad():
            lists = (m.quantize_list_1, m.quantize_list_2, m.quantize_list_3,
                     m.quantize_list_4, m.quantize_list_5)
            for i, lst in enumerate(lists, start=1):
                setattr(m, f"embed_stack_{i}", torch.stack([q.embed for q in lst]).contiguous())
            m.proj_stack_w = torch.stack([p.weight for p in m.output_proj_list]).contiguous()
            m.proj_stack_b = torch.stack([p.bias for p in m.output_proj_list]).contiguous()
        return m
    return prepare_eval


def _vq(x, E, n_embed):
    """x: (B,L,dim), E: (B,dim,n_embed) → quantize (B,L,dim), idx (B,L)."""
    dist = (
        x.pow(2).sum(-1, keepdim=True)
        - 2.0 * torch.matmul(x, E)
        + E.pow(2).sum(1).unsqueeze(1)
    )
    idx = (-dist).max(-1).indices
    onehot = F.one_hot(idx, n_embed).type(x.dtype)
    return torch.matmul(onehot, E.transpose(1, 2)), idx


def _make_forward(m):
    def forward(image, label):
        feats = m.enc({"image": image})["features"]
        org = torch.cat([m.upsample_list[i](f) for i, f in enumerate(feats)], dim=1)
        tok = m.quantize_conv_t(org).flatten(2).permute(2, 0, 1)  # (196,B,256)
        B = tok.shape[1]
        pos = m.pos_embed(tok).unsqueeze(1).expand(-1, B, -1)
        enc_out = m.encoder(tok, mask=None, pos=pos)  # (5,196,B,256)
        enc_out = enc_out.permute(0, 2, 1, 3)  # (5,B,196,256)

        stacks = (m.embed_stack_5, m.embed_stack_4, m.embed_stack_3,
                  m.embed_stack_2, m.embed_stack_1)
        nq4, _ = _vq(enc_out[-1], stacks[0][label], m.n_embed)  # (B,196,256)
        outs = []
        for idx, stack in zip((-2, -3, -4, -5), stacks[1:]):
            x = torch.cat([enc_out[idx], nq4], dim=2)  # (B,196,512)
            outs.append(_vq(x, stack[label], m.n_embed)[0])
        quant_list = torch.stack(outs).permute(0, 2, 1, 3)  # (4,196,B,512)

        decode_pos = torch.cat([pos, pos], dim=2)
        dec = m.decoder(quant_list, tgt_mask=None, memory_mask=None, pos=decode_pos)  # (196,B,512)

        W = m.proj_stack_w[label]  # (B,272,512)
        Bb = m.proj_stack_b[label]  # (B,272)
        rec = torch.einsum("lbc,bdc->lbd", dec, W) + Bb.unsqueeze(0)  # (196,B,272)
        rec = rec.permute(1, 2, 0).reshape(B, m.channel, *m.feature_size)

        pred = torch.sqrt(((rec - org) ** 2).sum(dim=1, keepdim=True))
        return m.upsample(pred)  # (B,1,224,224)
    return forward


def _make_forward_reference(m):
    """원본 루프 구현과 수치 동등성 확인용 참조 경로 (느림, 검증 전용)."""
    def encode_ref(input_list, label):
        quant_list = []
        q4 = input_list[-1]
        n = q4.size(0)
        new_q4 = torch.zeros_like(q4)
        for b in range(n):
            lb = int(label[b].item())
            new_q4[b] = m.quantize_list_5[lb](q4[b])[0]
        for idx, lst in zip((-2, -3, -4, -5), (m.quantize_list_4, m.quantize_list_3,
                                               m.quantize_list_2, m.quantize_list_1)):
            x = torch.cat([input_list[idx], new_q4], dim=2)
            nq = torch.zeros_like(x)
            for b in range(n):
                lb = int(label[b].item())
                nq[b] = lst[lb](x[b])[0]
            quant_list.append(nq)
        return torch.stack(quant_list)

    def forward_reference(image, label):
        feats = m.enc({"image": image})["features"]
        org = torch.cat([m.upsample_list[i](f) for i, f in enumerate(feats)], dim=1)
        tok = m.quantize_conv_t(org).flatten(2).permute(2, 0, 1)
        B = tok.shape[1]
        pos = m.pos_embed(tok).unsqueeze(1).expand(-1, B, -1)
        enc_out = m.encoder(tok, mask=None, pos=pos).permute(0, 2, 1, 3)
        ql = encode_ref(enc_out, label).permute(0, 2, 1, 3)
        decode_pos = torch.cat([pos, pos], dim=2)
        dec = m.decoder(ql, tgt_mask=None, memory_mask=None, pos=decode_pos)
        L = dec.shape[0]
        rec_tok = torch.zeros(L, B, m.channel)
        for b in range(B):
            lb = int(label[b].item())
            rec_tok[:, b, :] = m.output_proj_list[lb](dec[:, b, :])
        rec = rec_tok.permute(1, 2, 0).reshape(B, m.channel, *m.feature_size)
        pred = torch.sqrt(((rec - org) ** 2).sum(dim=1, keepdim=True))
        return m.upsample(pred)
    return forward_reference


def build_model(checkpoint, device: str = "cpu", src_root: Path | None = None):
    """체크포인트로부터 모델을 재구성한다. (model, branch_mapping) 반환."""
    ck = load_checkpoint_meta(checkpoint)
    bm = dict(ck["branch_mapping"])
    src_root = Path(src_root) if src_root else discover_source()
    efficientnet_b4, T = load_snapshot_modules(src_root)
    model = _init_model(efficientnet_b4, T, num_branches=len(bm))
    sd = ck["state_dict"]
    sd = {k.replace("module.", "", 1): v for k, v in sd.items()}
    missing, unexpected = model.load_state_dict(sd, strict=False)
    if missing or unexpected:
        raise RuntimeError(f"HVQ state_dict 불일치: missing={missing[:5]} unexpected={unexpected[:5]}")
    model.eval()
    model.prepare_eval()
    model.to(device)
    log(f"[hvq] 모델 로드 완료: 분기 {len(bm)}개, epoch={ck.get('epoch')}, "
        f"best_metric={ck.get('best_metric')}, device={device}")
    return model, bm


# ---------------------------------------------------------------------------
# 전처리 / 스코어링
# ---------------------------------------------------------------------------
def preprocess(pil_images, imgsz: int = 224):
    import torchvision.transforms.v2 as T  # noqa: PLC0415

    resize = T.Resize(size=[imgsz, imgsz])
    mean = torch.tensor(MEAN).view(3, 1, 1)
    std = torch.tensor(STD).view(3, 1, 1)
    tensors = []
    for img in pil_images:
        x = resize(img)
        x = T.functional.pil_to_tensor(x).float() / 255.0
        tensors.append((x - mean) / std)
    return torch.stack(tensors, dim=0)


def scores_from_pred(pred):
    """pred (B,1,H,W) → 이미지 레벨 점수 (B,) [EvalImageMean: 히트맵 평균]."""
    return pred.flatten(1).mean(dim=1)


# ---------------------------------------------------------------------------
# 엔진
# ---------------------------------------------------------------------------
class HVQPTEngine:
    name = "pt"

    def __init__(self, checkpoint, device="cpu", src_root=None, half=False):
        self.device = device
        self.model, self.branch_mapping = build_model(checkpoint, device, src_root)
        self.num_classes = len(self.branch_mapping)
        self.half = False
        if half:
            if device.startswith("cuda"):
                self.model = self.model.half()
                self.model.prepare_eval()
                self.half = True
            else:
                log("[hvq][half] FP16은 CUDA에서만 지원 → FP32 유지")

    def infer(self, batch, labels):
        batch = batch.to(self.device)
        labels = labels.to(self.device)
        if self.half:
            batch = batch.half()
        with torch.no_grad():
            pred = self.model(batch, labels)
        return pred

    def release(self):
        import gc

        del self.model
        gc.collect()


class HVQAutoCastEngine(HVQPTEngine):
    """J(BF16 autocast) / K(FP16 model.half) 실험용."""

    def __init__(self, checkpoint, device="cpu", src_root=None, dtype="bf16"):
        self.dtype = dtype
        super().__init__(checkpoint, device, src_root, half=False)
        if dtype == "fp16":
            self.model = self.model.half()
            self.model.prepare_eval()

    def infer(self, batch, labels):
        batch = batch.to(self.device)
        labels = labels.to(self.device)
        if self.dtype == "bf16":
            with torch.no_grad(), torch.autocast(device_type="cpu", dtype=torch.bfloat16):
                pred = self.model(batch, labels)
        else:
            with torch.no_grad():
                pred = self.model(batch.half(), labels)
        return pred.float()


class HVQONNXEngine:
    name = "onnx"

    def __init__(self, onnx_path, num_branches, session_options=None):
        import onnxruntime  # noqa: PLC0415

        self.session = onnxruntime.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"],
                                                    sess_options=session_options)
        self.num_classes = num_branches
        self._ins = {i.name: i.name for i in self.session.get_inputs()}

    def infer(self, batch, labels):
        import numpy as np  # noqa: PLC0415
        import torch  # noqa: PLC0415

        names = [i.name for i in self.session.get_inputs()]
        feed = {names[0]: batch.numpy().astype(np.float32),
                names[1]: labels.numpy().astype(np.int64)}
        out = self.session.run(None, feed)[0]
        return torch.from_numpy(out)

    def release(self):
        del self.session


def export_onnx(checkpoint, out_path, src_root=None, opset: int = 17, half: bool = False) -> Path:
    """벡터화 경로를 ONNX로 익스포트 (image/label 배치 동적). half=True 시 FP16 I/O."""
    model, bm = build_model(checkpoint, "cpu", src_root)
    if half:
        model = model.half()
        model.prepare_eval()
    dummy_img = torch.rand(1, 3, 224, 224).half() if half else torch.rand(1, 3, 224, 224)
    dummy_lbl = torch.zeros(1, dtype=torch.long)
    torch.onnx.export(
        model, (dummy_img, dummy_lbl), str(out_path),
        input_names=["image", "label"], output_names=["pred"],
        dynamic_axes={"image": {0: "batch"}, "label": {0: "batch"}, "pred": {0: "batch"}},
        opset_version=opset, do_constant_folding=True, dynamo=False,
    )
    import onnx  # noqa: PLC0415
    import onnxruntime  # noqa: PLC0415

    onnx.checker.check_model(onnx.load(str(out_path)))
    with torch.no_grad():
        ref = model(dummy_img, dummy_lbl)
    s = onnxruntime.InferenceSession(str(out_path), providers=["CPUExecutionProvider"])
    o = s.run(None, {"image": dummy_img.numpy(), "label": dummy_lbl.numpy()})[0]
    log(f"[hvq][onnx] 변환 완료: {Path(out_path).name} (half={half}, "
        f"max|Δpred|={float((ref.float().numpy()-o).max()):.2e})")
    return Path(out_path)


class HVQONNXFP16IOEngine(HVQONNXEngine):
    """FP16 I/O ONNX 엔진 — 이미지를 fp16으로 공급하고 출력을 fp32로 환산."""

    def infer(self, batch, labels):
        import numpy as np  # noqa: PLC0415
        import torch  # noqa: PLC0415

        names = [i.name for i in self.session.get_inputs()]
        feed = {names[0]: batch.numpy().astype(np.float16),
                names[1]: labels.numpy().astype(np.int64)}
        out = self.session.run(None, feed)[0]
        return torch.from_numpy(out).float()


# ---------------------------------------------------------------------------
# 라벨/카테고리 유틸
# ---------------------------------------------------------------------------
def labels_for_images(paths, branch_mapping, default: str | None = None):
    import torch  # noqa: PLC0415

    labels, unknown = [], []
    for p in paths:
        cat = resolve_category(p, branch_mapping, default)
        if cat is None:
            unknown.append(str(p))
            labels.append(0)
        else:
            labels.append(branch_mapping[cat])
    if unknown:
        log(f"[hvq][경고] 카테고리 미확인 이미지 {len(unknown)}개 (분기 0으로 처리): {unknown[:3]}")
    return torch.tensor(labels, dtype=torch.long)


def collect_images(folder) -> list[Path]:
    folder = Path(folder)
    return sorted(p for p in folder.rglob("*") if p.suffix.lower() in IMG_EXTS)


def load_gt_masks(images: list[Path], dataset_root: Path = MV_ROOT / "dataset"):
    """Real-IAD GT 마스크 조회: dataset/**/<stem>.png. 없으면 None (OK 이미지)."""
    from PIL import Image  # noqa: PLC0415
    import numpy as np  # noqa: PLC0415

    index = None
    masks = {}
    for p in images:
        stem = p.stem
        if stem in masks:
            continue
        if index is None:
            index = {q.stem: q for q in Path(dataset_root).rglob("*.png")}
        q = index.get(stem)
        if q is None:
            masks[stem] = None
            continue
        with Image.open(q) as im:
            masks[stem] = (np.asarray(im.convert("L").resize((224, 224))) > 127).astype("uint8")
    return masks
