"""RT-DETRv2 추론 파이프라인 (공통 유틸 + CLI).

루트의 Ultralytics RT-DETR 학습 체크포인트(.pt)를 자동 탐색해 이미지 폴드 추론을 수행한다.
PyTorch(.pt)와 ONNX 두 엔진을 지원하며, tune_inference.py / benchmark.py가 이 파일의
공통 유틸을 재사용한다.

실행:
  python inference.py --input <이미지폴드> [--output <출력폴드>] [--engine {pt,onnx}]

체크포인트 형식 주의:
  이 저장소의 루트 체크포인트(epoch_*.pt)는 lyuwenyu/RT-DETR(고정 커밋 df2a96c) 커스텀
  학습 체크포인트다. Ultralytics RTDETR 인터페이스로는 로드할 수 없으므로(오류 확인됨),
  저장소에 동봉된 공식 소스 스냅샷(outputs/training_sources_v1/...)으로 모델을 재구성한다.
  클래스 계약: 141-프로토콜 중 결함 클래스 111종(dec_score_head 출력 수)이다.

이 파일의 파일명(inference.py)이 저장소의 기존 inference/ 패키지 디렉터리와 이름이 같다.
기존 스크립트의 `from inference.xxx import ...`가 계속 동작하도록, 임포트 시에는 이 모듈에
`__path__`를 부여해 기존 패키지 디렉터리로 서브모듈 탐색을 위임한다(실행 시에는 영향 없음).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from importlib.util import find_spec
from pathlib import Path

# ---------------------------------------------------------------------------
# 기존 inference/ 패키지 호환용: 이 파일이 `import inference`로 로드될 때만 동작.
# 루트의 inference.py가 네임스페이스 패키지 inference/ 보다 먼저 매칭되므로,
# 서브모듈 탐색 경로를 기존 패키지 디렉터리로 돌려준다.
# ---------------------------------------------------------------------------
_HERE = Path(__file__).resolve().parent
if __name__ not in ("__main__", "__mp_main__") and (_HERE / "inference").is_dir():
    __path__ = [str(_HERE / "inference")]

MV_ROOT = _HERE
IMG_EXTS = {".jpg", ".jpeg", ".png"}
DEFAULT_SOURCE_CANDIDATES = (
    "outputs/training_sources_v1/rtdetrv2/source/rtdetrv2_pytorch",
    "outputs/model_sources_20261112_v1/rtdetrv2/source/rtdetrv2_pytorch",
)
RTDETR_CONFIG = "configs/rtdetrv2/rtdetrv2_r18vd_120e_coco.yml"
_CLASSES_JSON_CANDIDATES = (
    "inference/classes_141.json",
    "inference/classes_141_server.json",
)

_STUBS_DONE = False
_SOURCE_READY = False


# ---------------------------------------------------------------------------
# 기본 유틸
# ---------------------------------------------------------------------------
def log(msg: str) -> None:
    print(msg, flush=True)


def find_checkpoint(root: Path | str = MV_ROOT, pattern: str = "*.pt") -> Path:
    """root 폴드의 .pt 파일을 수정 시각 기준 최신 것 하나를 선택한다."""
    files = sorted(Path(root).glob(pattern), key=lambda p: p.stat().st_mtime)
    if not files:
        raise FileNotFoundError(f"{root}에서 {pattern} 체크포인트를 찾지 못했습니다")
    chosen = files[-1]
    if len(files) > 1:
        log(f"[checkpoint] 후보 {len(files)}개, 최신 선택: {chosen.name}")
    return chosen


def discover_model_source(root: Path | str = MV_ROOT, explicit: str | None = None) -> Path:
    """공식 RT-DETRv2 소스 스냅샷 위치를 찾는다(저장소 상대 경로)."""
    root = Path(root)
    if explicit:
        p = Path(explicit)
        if not p.is_absolute():
            p = root / p
        if (p / "src" / "core").is_dir():
            return p
        raise FileNotFoundError(f"--src 지정 경로에 src/core가 없습니다: {p}")
    for cand in DEFAULT_SOURCE_CANDIDATES:
        p = root / cand
        if (p / "src" / "core").is_dir() and (p / "src" / "zoo" / "rtdetr").is_dir():
            return p
    raise FileNotFoundError(
        "RT-DETRv2 소스 스냅샷을 찾지 못했습니다. --src 로 rtdetrv2_pytorch 경로를 지정하세요."
    )


def ensure_third_party_stubs() -> None:
    """추론 경로에서 미사용이며 미설치된 학습 전용 의존성을 스텁 처리한다.

    공식 소스의 src 패키지 초기화가 tensorboard / faster_coco_eval 을 임포트하므로
    런타임 스텁으로만 대체한다(패키지 설치 없음, 모델 추론·ONNX 변환에는 미사용).
    """
    global _STUBS_DONE
    if _STUBS_DONE:
        return
    import types

    if find_spec("tensorboard") is None:
        tb_stub = types.ModuleType("torch.utils.tensorboard")

        class _SummaryWriter:
            def __init__(self, *a, **k):
                pass

            def __getattr__(self, name):
                return lambda *a, **k: None

        tb_stub.SummaryWriter = _SummaryWriter
        sys.modules["torch.utils.tensorboard"] = tb_stub

    if find_spec("faster_coco_eval") is None:
        fce = types.ModuleType("faster_coco_eval")

        class _Unavailable:
            def __init__(self, *a, **k):
                raise NotImplementedError("faster_coco_eval은 학습/평가 전용 의존성입니다")

        fce.COCO = _Unavailable
        submods = {
            "faster_coco_eval.core": "core",
            "faster_coco_eval.core.mask": "core.mask",
            "faster_coco_eval.utils": "utils",
            "faster_coco_eval.utils.pytorch": "utils.pytorch",
        }
        created = {}
        for modname, attr in submods.items():
            m = types.ModuleType(modname)
            sys.modules[modname] = m
            created[modname] = (m, attr)
        sys.modules["faster_coco_eval.utils.pytorch"].FasterCocoDetection = _Unavailable
        sys.modules["faster_coco_eval.utils.pytorch"].FasterCocoEvaluator = _Unavailable
        fce.core = sys.modules["faster_coco_eval.core"]
        fce.utils = sys.modules["faster_coco_eval.utils"]
        sys.modules["faster_coco_eval"] = fce

    _STUBS_DONE = True


def load_yaml_config(src_root: Path, imgsz: int, num_classes: int):
    """공식 소스의 YAMLConfig로 eval 모델을 구성한다(앵커는 imgsz 기준 생성)."""
    ensure_third_party_stubs()
    src_root = Path(src_root)
    if str(src_root) not in sys.path:
        sys.path.insert(0, str(src_root))
    from src.core import YAMLConfig  # noqa: PLC0415

    cfg = YAMLConfig(
        str(src_root / RTDETR_CONFIG),
        num_classes=num_classes,
        remap_mscoco_category=False,
        eval_spatial_size=[imgsz, imgsz],
    )
    return cfg


def count_classes(state_dict: dict) -> int:
    """dec_score_head 바이어스 길이로 클래스 수를 판정한다."""
    for key in ("decoder.dec_score_head.0.bias", "decoder.dec_score_head.bias"):
        if key in state_dict:
            return int(state_dict[key].shape[0])
    raise KeyError("state_dict에서 dec_score_head를 찾지 못했습니다")


def load_class_names(num_classes: int) -> list[str]:
    """141-프로토콜 classes json에서 결함 클래스 0..n-1 이름을 가져온다."""
    for cand in _CLASSES_JSON_CANDIDATES:
        p = MV_ROOT / cand
        if p.is_file():
            id_to_name = json.loads(p.read_text())["id_to_name"]
            return [id_to_name[str(i)] for i in range(num_classes)]
    return [f"class_{i}" for i in range(num_classes)]


def resolve_device(requested: str):
    """요청 device를 해석한다. auto 시 CUDA 우선, 없으면 CPU 폴드백."""
    import torch  # noqa: PLC0415

    if requested == "auto":
        return "cuda:0" if torch.cuda.is_available() else "cpu"
    if requested.startswith("cuda") and not torch.cuda.is_available():
        log(f"[device] {requested} 요청했으나 CUDA 미사용 가능 → CPU 폴드백")
        return "cpu"
    return requested


def extract_state_dict(checkpoint_path: Path | str, use_ema: bool = True):
    """체크포인트에서 모델 state_dict를 꺼낸다. EMA를 우선 사용한다."""
    import torch  # noqa: PLC0415

    ckpt = torch.load(str(checkpoint_path), map_location="cpu", weights_only=False)
    if isinstance(ckpt, dict) and "model" in ckpt and isinstance(ckpt["model"], dict):
        if use_ema and isinstance(ckpt.get("ema"), dict) and ckpt["ema"].get("module"):
            ema = {k.replace("module.", "", 1): v for k, v in ckpt["ema"]["module"].items()}
            log(f"[checkpoint] EMA 가중치 사용 (epoch={ckpt.get('epoch', '?')})")
            return ema
        log(f"[checkpoint] 마지막 step 가중치 사용 (epoch={ckpt.get('epoch', '?')})")
        return ckpt["model"]
    # 순수 state_dict 형태
    return ckpt


def build_torch_model(checkpoint_path: Path | str, imgsz: int, device: str,
                      src_root: Path | None = None, use_ema: bool = True,
                      half: bool = False):
    """체크포인트로부터 eval용 torch 모델을 구성한다. (model, num_classes, class_names) 반환."""
    import torch  # noqa: PLC0415

    sd = extract_state_dict(checkpoint_path, use_ema=use_ema)
    num_classes = count_classes(sd)
    src_root = Path(src_root) if src_root else discover_model_source()
    cfg = load_yaml_config(src_root, imgsz, num_classes)
    model = cfg.model
    # anchors/valid_mask는 eval_spatial_size(=imgsz) 기준으로 __init__에서 재생성되는
    # 기하 버퍼이므로 체크포인트에 저장된(학습 당시 imgsz) 값은 로드하지 않는다.
    geo_buffers = {"decoder.anchors", "decoder.valid_mask"}
    sd = {k: v for k, v in sd.items() if k not in geo_buffers}
    missing, unexpected = model.load_state_dict(sd, strict=False)
    bad_missing = [k for k in missing if k not in geo_buffers]
    if bad_missing or unexpected:
        raise RuntimeError(
            f"state_dict 로드 불일치: missing(비기하)={bad_missing[:5]} unexpected={unexpected[:5]}"
        )
    model.eval()

    if half:
        if not device.startswith("cuda"):
            log("[half] FP16은 CUDA에서만 지원 → FP32 유지")
        else:
            model = model.half()
            log("[half] FP16 적용")
    model.to(device)
    names = load_class_names(num_classes)
    return model, num_classes, names


# ---------------------------------------------------------------------------
# 전처리 / 후처리
# ---------------------------------------------------------------------------
def collect_images(folder: Path | str) -> list[Path]:
    folder = Path(folder)
    return sorted(p for p in folder.rglob("*") if p.suffix.lower() in IMG_EXTS)


def preprocess(pil_images: list, imgsz: int):
    """공식 val 변환과 동일: Resize([imgsz, imgsz]) → float32 0..1 → (B,3,H,W)."""
    import torch  # noqa: PLC0415
    import torchvision.transforms.v2 as T  # noqa: PLC0415

    resize = T.Resize(size=[imgsz, imgsz])
    tensors = []
    for img in pil_images:
        x = resize(img)
        x = T.functional.pil_to_tensor(x).float() / 255.0
        tensors.append(x)
    return torch.stack(tensors, dim=0)


def postprocess(logits, boxes, orig_sizes, conf: float, iou: float,
                num_top_queries: int = 300):
    """RT-DETRv2 디코딩: sigmoid top-k → conf 필터 → (옵션) 클래스 인식 NMS → 원본 크기 좌표.

    logits: (B, Q, C), boxes: (B, Q, 4) normalized cxcywh, orig_sizes: (B, 2) (w, h).
    반환: 이미지별 dict 리스트 {boxes(xyxy 절대좌표), scores, labels}.
    """
    import torch  # noqa: PLC0415
    import torchvision  # noqa: PLC0415

    scores = torch.sigmoid(logits.float())
    b, q, c = scores.shape
    k = min(num_top_queries, q * c)
    topv, topi = scores.flatten(1).topk(k, dim=-1)
    query_idx = topi // c
    labels = topi % c
    sel = boxes.gather(1, query_idx.unsqueeze(-1).expand(-1, -1, 4))
    sel = torchvision.ops.box_convert(sel, in_fmt="cxcywh", out_fmt="xyxy")
    sel = sel * orig_sizes.repeat(1, 2).view(-1, 1, 4).to(sel.dtype)

    results = []
    for bi in range(b):
        m = topv[bi] >= conf
        bxs, scs, lbs = sel[bi][m], topv[bi][m], labels[bi][m]
        if scs.numel() == 0:
            results.append({"boxes": bxs.reshape(0, 4), "scores": scs, "labels": lbs})
            continue
        if iou is not None and iou < 1.0:
            keep = torchvision.ops.batched_nms(bxs.float(), scs.float(), lbs, iou)
            bxs, scs, lbs = bxs[keep], scs[keep], lbs[keep]
        order = torch.argsort(scs, descending=True)
        results.append({"boxes": bxs[order], "scores": scs[order], "labels": lbs[order]})
    return results


# ---------------------------------------------------------------------------
# 추론 엔진
# ---------------------------------------------------------------------------
class PTEngine:
    """PyTorch 체크포인트 엔진."""

    name = "pt"

    def __init__(self, checkpoint: Path, imgsz: int, device: str, src_root: Path | None,
                 half: bool = False, use_ema: bool = True):
        import torch  # noqa: PLC0415

        self.torch = torch
        self.imgsz = imgsz
        self.device = device
        self.model, self.num_classes, self.class_names = build_torch_model(
            checkpoint, imgsz, device, src_root=src_root, use_ema=use_ema, half=half
        )
        self.half = half and device.startswith("cuda")

    def infer(self, batch):
        batch = batch.to(self.device)
        if self.half:
            batch = batch.half()
        with self.torch.no_grad():
            out = self.model(batch)
        return out["pred_logits"], out["pred_boxes"]

    def release(self) -> None:
        import gc  # noqa: PLC0415

        del self.model
        gc.collect()


class ONNXEngine:
    """ONNX Runtime 엔진."""

    name = "onnx"

    def __init__(self, onnx_path: Path, num_classes: int):
        import onnxruntime  # noqa: PLC0415

        providers = ["CPUExecutionProvider"]
        if onnxruntime.get_device() == "GPU" and "CUDAExecutionProvider" in onnxruntime.get_available_providers():
            providers.insert(0, "CUDAExecutionProvider")
        self.session = onnxruntime.InferenceSession(str(onnx_path), providers=providers)
        self.imgsz = None  # export 시 고정이지만 동적 배치 허용
        self.num_classes = num_classes
        self.class_names = load_class_names(num_classes)
        self._input_name = self.session.get_inputs()[0].name

    def infer(self, batch):
        out = self.session.run(None, {self._input_name: batch.numpy()})
        import torch  # noqa: PLC0415

        return torch.from_numpy(out[0]), torch.from_numpy(out[1])

    def release(self) -> None:
        del self.session


def export_onnx(checkpoint: Path, imgsz: int, out_path: Path, src_root: Path | None = None,
                use_ema: bool = True) -> Path:
    """체크포인트를 ONNX로 변환한다(배치 동적, 후처리는 엔진 공통 코드에서 수행)."""
    import torch  # noqa: PLC0415

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    model, num_classes, _ = build_torch_model(
        checkpoint, imgsz, "cpu", src_root=src_root, use_ema=use_ema, half=False
    )
    model.eval()
    dummy = torch.rand(1, 3, imgsz, imgsz)
    torch.onnx.export(
        model,
        dummy,
        str(out_path),
        input_names=["images"],
        output_names=["pred_logits", "pred_boxes"],
        dynamic_axes={"images": {0: "batch"}, "pred_logits": {0: "batch"}, "pred_boxes": {0: "batch"}},
        opset_version=17,
        do_constant_folding=True,
        dynamo=False,  # 신형 exporter는 onnxscript를 필요로 함 — 레거시 추적기 사용
    )
    # 변환 정합성 검증
    import onnx  # noqa: PLC0415
    import onnxruntime  # noqa: PLC0415

    onnx.checker.check_model(onnx.load(str(out_path)))
    with torch.no_grad():
        ref = model(dummy)
    ref_logits, ref_boxes = ref["pred_logits"], ref["pred_boxes"]
    sess = onnxruntime.InferenceSession(str(out_path), providers=["CPUExecutionProvider"])
    o_logits, o_boxes = sess.run(None, {"images": dummy.numpy()})
    d_logits = abs(float((ref_logits.numpy() - o_logits).max()))
    d_boxes = abs(float((ref_boxes.numpy() - o_boxes).max()))
    log(f"[onnx] 변환 완료: {out_path.name} (max|Δlogits|={d_logits:.2e}, max|Δboxes|={d_boxes:.2e})")
    return out_path


# ---------------------------------------------------------------------------
# 시각화 / 저장
# ---------------------------------------------------------------------------
_PALETTE = [
    (255, 56, 56), (255, 157, 151), (255, 112, 31), (255, 178, 29), (207, 210, 49),
    (72, 249, 10), (146, 204, 23), (61, 219, 134), (26, 147, 52), (0, 212, 187),
    (44, 153, 168), (0, 194, 255), (52, 69, 147), (100, 115, 255), (0, 24, 236),
    (132, 56, 255), (82, 0, 133), (203, 56, 255), (255, 149, 200), (255, 55, 199),
]


def visualize(image, boxes, scores, labels, class_names, conf: float):
    """PIL 이미지에 바울딩박스/라벨/신뢰도를 그린다."""
    from PIL import ImageDraw  # noqa: PLC0415

    img = image.copy()
    draw = ImageDraw.Draw(img)
    for box, score, label in zip(boxes, scores, labels):
        if float(score) < conf:
            continue
        x1, y1, x2, y2 = [float(v) for v in box]
        color = _PALETTE[int(label) % len(_PALETTE)]
        draw.rectangle([x1, y1, x2, y2], outline=color, width=3)
        name = class_names[int(label)] if int(label) < len(class_names) else str(int(label))
        text = f"{name} {float(score):.2f}"
        tw = draw.textlength(text)
        th = 14
        ty = max(0, y1 - th - 2)
        draw.rectangle([x1, ty, x1 + tw + 4, ty + th + 2], fill=color)
        draw.text((x1 + 2, ty + 1), text, fill=(0, 0, 0))
    return img


def save_json(path: Path, payload: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2))


# ---------------------------------------------------------------------------
# 배치 추론 루프 (tune/benchmark도 재사용)
# ---------------------------------------------------------------------------
def run_inference(images: list[Path], engine, conf: float, iou: float, imgsz: int,
                  batch_size: int, show_progress: bool = True):
    """이미지 경로 리스트를 배치 추론한다.

    반환: (results, stats)
      results: [{file, width, height, detections:[{bbox, class_id, class_name, score}]}]
      stats: {forward_ms, wall_s, n_images, per_image_forward_ms}
    """
    import torch  # noqa: PLC0415
    from PIL import Image  # noqa: PLC0415

    try:
        from tqdm import tqdm  # noqa: PLC0415
    except ImportError:  # pragma: no cover
        tqdm = None

    results: list[dict] = []
    forward_ms = 0.0
    wall_start = time.perf_counter()
    per_image_ms: list[float] = []

    iterator = range(0, len(images), batch_size)
    if show_progress and tqdm is not None:
        iterator = tqdm(iterator, total=(len(images) + batch_size - 1) // batch_size,
                        desc="추론", unit="batch")

    for start in iterator:
        batch_paths = images[start:start + batch_size]
        pil_images = [Image.open(p).convert("RGB") for p in batch_paths]
        orig_sizes = torch.tensor([[img.width, img.height] for img in pil_images])
        batch = preprocess(pil_images, imgsz)

        t0 = time.perf_counter()
        logits, boxes = engine.infer(batch)
        forward_ms += (time.perf_counter() - t0) * 1000.0
        per_image_ms.extend([(time.perf_counter() - t0) * 1000.0 / len(batch_paths)] * len(batch_paths))

        decoded = postprocess(logits, boxes, orig_sizes, conf=conf, iou=iou)
        for path, img, det in zip(batch_paths, pil_images, decoded):
            detections = [
                {
                    "bbox": [round(float(v), 2) for v in box],
                    "class_id": int(lb),
                    "class_name": engine.class_names[int(lb)] if int(lb) < len(engine.class_names) else str(int(lb)),
                    "score": round(float(sc), 4),
                }
                for box, sc, lb in zip(det["boxes"], det["scores"], det["labels"])
            ]
            results.append({
                "file": str(path),
                "width": img.width,
                "height": img.height,
                "detections": detections,
            })
        for img in pil_images:
            img.close()

    wall_s = time.perf_counter() - wall_start
    stats = {
        "forward_ms": forward_ms,
        "wall_s": wall_s,
        "n_images": len(images),
        "per_image_forward_ms": per_image_ms,
    }
    return results, stats


def detect_summary(results: list[dict]) -> dict:
    counts = [len(r["detections"]) for r in results]
    total = sum(counts)
    scores = [d["score"] for r in results for d in r["detections"]]
    return {
        "total_detections": total,
        "mean_dets_per_img": total / len(results) if results else 0.0,
        "zero_det_images": sum(1 for c in counts if c == 0),
        "max_dets_in_img": max(counts) if counts else 0,
        "mean_score": sum(scores) / len(scores) if scores else 0.0,
        "high_conf_ratio": sum(1 for s in scores if s >= 0.5) / len(scores) if scores else 0.0,
    }


def print_summary(results: list[dict], stats: dict, engine_name: str, imgsz: int) -> None:
    s = detect_summary(results)
    n = max(stats["n_images"], 1)
    fps_model = n / (stats["forward_ms"] / 1000.0) if stats["forward_ms"] > 0 else 0.0
    fps_wall = n / stats["wall_s"] if stats["wall_s"] > 0 else 0.0
    log("")
    log("=" * 62)
    log(f"[요약] 엔진={engine_name}  imgsz={imgsz}")
    log(f"  총 이미지 수        : {stats['n_images']}")
    log(f"  평균 추론 시간      : {stats['forward_ms'] / n:.1f} ms/img (모델 forward)")
    log(f"  FPS                 : {fps_model:.2f} (모델) / {fps_wall:.2f} (전체 파이프라인)")
    log(f"  총 검출 수          : {s['total_detections']}")
    log(f"  이미지당 평균 검출  : {s['mean_dets_per_img']:.2f}")
    log(f"  검출 0개 이미지     : {s['zero_det_images']}")
    log(f"  이미지당 최대 검출  : {s['max_dets_in_img']}")
    log(f"  평균 신뢰도         : {s['mean_score']:.3f}")
    log(f"  고신뢰(>=0.5) 비율  : {s['high_conf_ratio']:.3f}")
    log("=" * 62)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def parse_args(argv=None):
    p = argparse.ArgumentParser(description="RT-DETRv2 추론 (pt/onnx)")
    p.add_argument("--input", required=True, help="이미지 폴드 경로")
    p.add_argument("--output", default="rtdetr_outputs", help="결과 출력 폴드 (기본: rtdetr_outputs)")
    p.add_argument("--engine", choices=["pt", "onnx"], default="pt")
    p.add_argument("--checkpoint", default=None, help="체크포인트 경로 (미지정 시 루트 .pt 자동 탐색)")
    p.add_argument("--src", default=None, help="rtdetrv2_pytorch 소스 경로 (미지정 시 자동 탐색)")
    p.add_argument("--conf", type=float, default=0.25)
    p.add_argument("--iou", type=float, default=0.5, help="NMS IoU 임계값")
    p.add_argument("--imgsz", type=int, default=640)
    p.add_argument("--batch", type=int, default=4)
    p.add_argument("--device", default="auto", help="auto|cpu|cuda:0 ...")
    p.add_argument("--half", action="store_true", help="FP16 (CUDA에서만 자동 적용, CPU에선 FP32)")
    p.add_argument("--no-ema", action="store_true", help="EMA 대신 마지막 step 가중치 사용")
    p.add_argument("--max-images", type=int, default=None, help="처리할 최대 이미지 수 (디버그용)")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    input_dir = Path(args.input)
    if not input_dir.is_dir():
        log(f"[오류] 입력 폴드가 없습니다: {input_dir}")
        return 2

    checkpoint = Path(args.checkpoint) if args.checkpoint else find_checkpoint()
    src_root = discover_model_source(explicit=args.src)
    device = resolve_device(args.device)
    half = bool(args.half and device.startswith("cuda"))
    use_ema = not args.no_ema

    images = collect_images(input_dir)
    if args.max_images:
        images = images[: args.max_images]
    if not images:
        log(f"[오류] 이미지가 없습니다: {input_dir}")
        return 2
    log(f"[준비] 이미지 {len(images)}장, checkpoint={checkpoint.name}, device={device}, "
        f"engine={args.engine}, conf={args.conf}, iou={args.iou}, imgsz={args.imgsz}, batch={args.batch}")

    out_dir = Path(args.output)
    vis_dir = out_dir / "visualized"
    vis_dir.mkdir(parents=True, exist_ok=True)

    if args.engine == "pt":
        engine = PTEngine(checkpoint, args.imgsz, device, src_root, half=half, use_ema=use_ema)
    else:
        onnx_path = out_dir / f"{checkpoint.stem}_{args.imgsz}.onnx"
        if not onnx_path.exists():
            log(f"[onnx] 변환 모델이 없어 변환을 수행합니다: {onnx_path.name}")
            export_onnx(checkpoint, args.imgsz, onnx_path, src_root=src_root, use_ema=use_ema)
        engine = ONNXEngine(onnx_path, num_classes=count_classes(extract_state_dict(checkpoint, use_ema)))

    results, stats = run_inference(images, engine, conf=args.conf, iou=args.iou,
                                   imgsz=args.imgsz, batch_size=args.batch)
    print_summary(results, stats, args.engine, args.imgsz)

    # 시각화 이미지 저장
    from PIL import Image  # noqa: PLC0415

    vis_count = 0
    for r in results:
        img = Image.open(r["file"]).convert("RGB")
        if r["detections"]:
            det = r["detections"]
            vis = visualize(
                img,
                [d["bbox"] for d in det], [d["score"] for d in det], [d["class_id"] for d in det],
                engine.class_names, conf=args.conf,
            )
        else:
            vis = img
        vis.save(vis_dir / (Path(r["file"]).stem + ".jpg"), quality=92)
        vis_count += 1
        img.close()
    log(f"[저장] 시각화 이미지 {vis_count}장 → {vis_dir}")

    payload = {
        "checkpoint": str(checkpoint),
        "engine": args.engine,
        "imgsz": args.imgsz,
        "conf": args.conf,
        "iou": args.iou,
        "device": device,
        "images": results,
        "summary": detect_summary(results),
    }
    json_path = out_dir / "detections.json"
    save_json(json_path, payload)
    log(f"[저장] JSON → {json_path}")
    engine.release()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
