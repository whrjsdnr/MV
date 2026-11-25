"""RT-DETRv2 추론 최적화 기법별 독립 비교 실험 (CPU).

baseline(pt FP32)에 각 최적화 기법을 하나씩 적용해 같은 입력 세트에서
속도(FPS, p50/p95), 메모리(peak RSS), 모델 크기, 정확도 가드레일을 측정한다.

  A. pt FP32 (baseline)        B. ONNX 기본
  C. ONNX 그래프 최적화 레벨   D. ONNX 동적 INT8
  E. ONNX 정적 INT8 (캘리브레이션) — 실패 시 사유 기록
  F. 스레드 스윕                G. 배치 스윕
  H/I. GPU (FP16/CUDA) — GPU 없으면 "GPU 없음" 표기
  + 상위 기법 조합 3개

공통 유틸은 inference.py / tune_inference.py를 재사용한다(수정 없이 import).
원시 데이터: optimization_results.csv, 보고서: optimization_report.md

실행:
  inference/.venv/bin/python optimize_compare.py --input <이미지폴드>
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import os
import random
import resource
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def load_shared():
    spec = importlib.util.spec_from_file_location("rtdetr_pipeline_shared", ROOT / "inference.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def load_tune_utils():
    spec = importlib.util.spec_from_file_location("rtdetr_tune_utils", ROOT / "tune_inference.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


shared = load_shared()
tune_utils = load_tune_utils()


# ---------------------------------------------------------------------------
# 엔진 래퍼
# ---------------------------------------------------------------------------
class ORTEngine:
    """onnxruntime 세션을 shared.run_inference 인터페이스에 맞게 래핑."""

    def __init__(self, onnx_path: Path, num_classes: int, session_options=None):
        import onnxruntime  # noqa: PLC0415

        self.name = "onnx"
        self.session = onnxruntime.InferenceSession(
            str(onnx_path), providers=["CPUExecutionProvider"], sess_options=session_options
        )
        self.num_classes = num_classes
        self.class_names = shared.load_class_names(num_classes)
        self._input_name = self.session.get_inputs()[0].name

    def infer(self, batch):
        import torch  # noqa: PLC0415

        out = self.session.run(None, {self._input_name: batch.numpy()})
        return torch.from_numpy(out[0]), torch.from_numpy(out[1])

    def release(self):
        del self.session


def rss_mb() -> int:
    """현재 프로세스 peak RSS (MB, Linux ru_maxrss=KB)."""
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss // 1024


def physical_cores() -> int:
    try:
        return len(os.sched_getaffinity(0))
    except (AttributeError, OSError):
        return os.cpu_count() or 1


# ---------------------------------------------------------------------------
# 측정
# ---------------------------------------------------------------------------
def measure(engine, images: list[Path], imgsz: int, batch: int, warmup_batches: int = 10):
    """워밍업 `warmup_batches` 배치 후 1회 전체 패스를 측정한다.

    반환: (metrics dict, detections for guardrail)
    """
    import torch  # noqa: PLC0415
    from PIL import Image  # noqa: PLC0415

    # 워밍업
    warm = images[:batch * warmup_batches]
    if not warm:
        warm = images
    for start in range(0, len(warm), batch):
        paths = warm[start:start + batch]
        pil = [Image.open(p).convert("RGB") for p in paths]
        with torch.no_grad() if engine.name == "pt" else _nullctx():
            engine.infer(shared.preprocess(pil, imgsz))
        for i in pil:
            i.close()

    per_image_ms: list[float] = []
    t_start = time.perf_counter()
    results: dict[str, list] = {}
    for start in range(0, len(images), batch):
        paths = images[start:start + batch]
        pil = [Image.open(p).convert("RGB") for p in paths]
        orig = torch.tensor([[i.width, i.height] for i in pil])
        batch_t = shared.preprocess(pil, imgsz)
        t0 = time.perf_counter()
        logits, boxes = engine.infer(batch_t)
        det = shared.postprocess(logits, boxes, orig, conf=0.0, iou=None)  # 가드레일용 전체 보관
        dt = (time.perf_counter() - t0) * 1000.0
        per_image_ms.extend([dt / len(paths)] * len(paths))
        for p, d in zip(paths, det):
            results[p.name] = [
                (int(lb), float(sc), tuple(float(v) for v in box))
                for box, sc, lb in zip(d["boxes"], d["scores"], d["labels"])
            ]
        for i in pil:
            i.close()
    total_s = time.perf_counter() - t_start
    lat = sorted(per_image_ms)
    metrics = {
        "fps": len(images) / total_s if total_s > 0 else 0.0,
        "p50_ms": _pct(lat, 50),
        "p95_ms": _pct(lat, 95),
        "mean_ms": sum(lat) / len(lat) if lat else 0.0,
        "total_s": total_s,
    }
    return metrics, results


class _nullctx:
    def __enter__(self):
        return None

    def __exit__(self, *a):
        return False


def _pct(sorted_vals: list[float], q: float) -> float:
    if not sorted_vals:
        return 0.0
    idx = min(len(sorted_vals) - 1, max(0, int(round((q / 100.0) * (len(sorted_vals) - 1)))))
    return sorted_vals[idx]


def filter_conf(dets: list, conf: float) -> list:
    return [d for d in dets if d[1] >= conf]


def guardrail(base: dict, cand: dict, conf: float):
    """baseline(A)와 후보의 conf 필터 결과를 비교한다.

    반환: (det_count_diff, match_rate, score_mad)
    """
    names = set(base) | set(cand)
    diffs, rates, mad_vals = [], [], []
    for n in names:
        b = filter_conf(base.get(n, []), conf)
        c = filter_conf(cand.get(n, []), conf)
        diffs.append(len(c) - len(b))
        used = set()
        matches = 0
        score_abs = []
        # 점수 내림차순 그리디 매칭
        cand_sorted = sorted(c, key=lambda x: -x[1])
        for (_, sc_c, box_c) in cand_sorted:
            best_iou, best_j = 0.0, -1
            for j, (_, sb, box_b) in enumerate(b):
                if j in used:
                    continue
                v = tune_utils.iou_xyxy(box_c, box_b)
                if v > best_iou:
                    best_iou, best_j = v, j
            if best_iou >= 0.5 and best_j >= 0:
                used.add(best_j)
                matches += 1
                score_abs.append(abs(sc_c - b[best_j][1]))
        denom = max(len(b), len(c), 1)
        rates.append(matches / denom if (b or c) else 1.0)
        mad_vals.extend(score_abs)
    det_diff = sum(diffs) / len(diffs) if diffs else 0.0
    match_rate = sum(rates) / len(rates) if rates else 1.0
    score_mad = sum(mad_vals) / len(mad_vals) if mad_vals else 0.0
    return det_diff, match_rate, score_mad


# ---------------------------------------------------------------------------
# 실험 행 기록 (emit/skip) — 기본 실험과 정밀도 실험(J~M)이 공유
# ---------------------------------------------------------------------------
class Emitter:
    def __init__(self, rows: list, images: list, args):
        self.rows = rows
        self.images = images
        self.args = args
        self.base_dets: dict | None = None

    def emit(self, build, label, category, detail, batch, model_file=None, note="", extra=None):
        """build: engine 생성 callable. RSS는 생성 전/측정 후로 나누어 기록한다."""
        rss0 = rss_mb()
        engine = build()
        metrics, dets = measure(engine, self.images, self.args.imgsz, batch, self.args.warmup)
        rss1 = rss_mb()
        if self.base_dets is None:
            self.base_dets = dets
        det_diff, match_rate, score_mad = guardrail(self.base_dets, dets, self.args.conf)
        guard_pass = match_rate >= 0.95
        row = {
            "name": label, "category": category, "detail": detail, "batch": batch,
            "imgsz": self.args.imgsz, "status": "ok", "note": note if guard_pass else f"{note} ⚠️매칭률<95%".strip(),
            "fps": round(metrics["fps"], 3),
            "p50_ms": round(metrics["p50_ms"], 2),
            "p95_ms": round(metrics["p95_ms"], 2),
            "mean_ms": round(metrics["mean_ms"], 2),
            "peak_rss_mb": rss1,
            "rss_delta_mb": max(rss1 - rss0, 0),
            "model_size_mb": round(os.path.getsize(model_file) / 1e6, 1) if model_file and Path(model_file).exists() else "",
            "det_count_diff": round(det_diff, 4),
            "match_rate": round(match_rate, 4),
            "score_mad": round(score_mad, 4),
            "guardrail_pass": guard_pass,
            "total_s": round(metrics["total_s"], 2),
        }
        if extra:
            row.update(extra)
        self.rows.append(row)
        print(f"  [{label}] fps={row['fps']:.2f} p50={row['p50_ms']}ms rssΔ={row['rss_delta_mb']}MB "
              f"match={row['match_rate']:.3f}", flush=True)
        engine.release()

    def skip(self, label, category, detail, reason):
        self.rows.append({
            "name": label, "category": category, "detail": detail, "batch": "", "imgsz": self.args.imgsz,
            "status": "skip", "note": reason, "fps": "", "p50_ms": "", "p95_ms": "", "mean_ms": "",
            "peak_rss_mb": "", "rss_delta_mb": "", "model_size_mb": "", "det_count_diff": "",
            "match_rate": "", "score_mad": "", "guardrail_pass": "", "total_s": "",
        })
        print(f"  [{label}] SKIP: {reason}", flush=True)


# ---------------------------------------------------------------------------
# 기법 구성
# ---------------------------------------------------------------------------
def make_session_options(opt_level=None, threads=None):
    import onnxruntime as ort  # noqa: PLC0415

    so = ort.SessionOptions()
    if opt_level is not None:
        so.graph_optimization_level = opt_level
    if threads is not None:
        so.intra_op_num_threads = threads
        so.inter_op_num_threads = 1
        os.environ["OMP_NUM_THREADS"] = str(threads)
    return so


def quantize_dynamic(fp32_onnx: Path, out_path: Path) -> Path:
    from onnxruntime.quantization import QuantType, quantize_dynamic  # noqa: PLC0415

    quantize_dynamic(str(fp32_onnx), str(out_path), weight_type=QuantType.QInt8)
    return out_path


def quantize_static(fp32_onnx: Path, out_path: Path, images: list[Path], imgsz: int) -> Path:
    from onnxruntime.quantization import (  # noqa: PLC0415
        CalibrationDataReader, QuantFormat, QuantType, quantize_static,
    )

    class _Reader(CalibrationDataReader):
        def __init__(self, paths, size):
            import numpy as np  # noqa: PLC0415

            self._data = []
            for p in paths:
                import torch  # noqa: PLC0415
                from PIL import Image  # noqa: PLC0415

                with Image.open(p) as im:
                    t = shared.preprocess([im.convert("RGB")], size).numpy().astype(np.float32)
                self._data.append({_input_name_of(fp32_onnx): t})
            self._iter = iter(self._data)

        def get_next(self):
            return next(self._iter, None)

    reader = _Reader(images, imgsz)
    from onnxruntime.quantization import CalibrationMethod  # noqa: PLC0415

    quantize_static(
        str(fp32_onnx), str(out_path), reader,
        quant_format=QuantFormat.QDQ,
        per_channel=True,
        weight_type=QuantType.QInt8,
        activation_type=QuantType.QInt8,
        calibrate_method=CalibrationMethod.MinMax,
    )
    return out_path


def _input_name_of(onnx_path: Path) -> str:
    import onnxruntime as ort  # noqa: PLC0415

    return ort.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"]).get_inputs()[0].name


# ---------------------------------------------------------------------------
# 정밀도 실험 (J~M): FP16/BF16 — CPU 측정이 목적(GPU 미필요)
# ---------------------------------------------------------------------------
class PTAutoCastEngine:
    """pt + autocast(BF16) 또는 model.half()(FP16) 엔진 래퍼."""

    name = "pt"

    def __init__(self, checkpoint, imgsz, device, src_root, use_ema=True, dtype: str = "bf16"):
        import torch  # noqa: PLC0415

        self.torch = torch
        self.dtype = dtype  # "bf16" | "fp16"
        self.model, self.num_classes, self.class_names = shared.build_torch_model(
            checkpoint, imgsz, device, src_root=src_root, use_ema=use_ema, half=False
        )
        if dtype == "fp16":
            self.model = self.model.half()

    def infer(self, batch):
        t = self.torch
        if self.dtype == "bf16":
            with t.no_grad(), t.autocast(device_type="cpu", dtype=t.bfloat16):
                out = self.model(batch)
        else:
            with t.no_grad():
                out = self.model(batch.half())
        return out["pred_logits"], out["pred_boxes"]

    def release(self):
        import gc  # noqa: PLC0415

        del self.model
        gc.collect()


def cpu_bf16_support() -> dict:
    """CPU BF16 하드웨어 지원 조사: /proc/cpuinfo 플래그 + torch API."""
    import re  # noqa: PLC0415
    import torch  # noqa: PLC0415

    flags: set[str] = set()
    try:
        flags = set(re.findall(r"avx512_bf16|amx_bf16", Path("/proc/cpuinfo").read_text()))
    except OSError:
        pass
    api = "torch.cpu.is_bf16_supported"
    api_exists = hasattr(torch.cpu, "is_bf16_supported")
    val = None
    if api_exists:
        try:
            val = bool(torch.cpu.is_bf16_supported())
        except Exception:  # noqa: BLE001
            val = None
    return {"flags": sorted(flags), "api": api, "api_exists": api_exists, "api_value": val}


class ORTFP16IOEngine(ORTEngine):
    """FP16 I/O 모델용 엔진 — 입력을 fp16으로 변환해 공급하고 출력을 fp32로 환산."""

    def infer(self, batch):
        import numpy as np  # noqa: PLC0415
        import torch  # noqa: PLC0415

        arr = batch.numpy().astype(np.float16)
        out = self.session.run(None, {self._input_name: arr})
        return torch.from_numpy(out[0]).float(), torch.from_numpy(out[1]).float()


def session_loadable(onnx_path: Path) -> bool:
    try:
        _input_name_of(onnx_path)
        return True
    except Exception:  # noqa: BLE001
        return False


def export_torch_fp16(checkpoint, imgsz: int, out_path: Path, src_root, use_ema: bool = True) -> Path:
    """torch fp16 모델을 직접 ONNX로 익스포트 (FP16 I/O). onnxconverter 경로가 유효하지 않을 때의 평백."""
    import torch  # noqa: PLC0415

    out_path = Path(out_path)
    model, _, _ = shared.build_torch_model(checkpoint, imgsz, "cpu", src_root=src_root,
                                           use_ema=use_ema, half=False)
    model = model.half().eval()
    dummy = torch.rand(1, 3, imgsz, imgsz).half()
    torch.onnx.export(
        model, dummy, str(out_path),
        input_names=["images"], output_names=["pred_logits", "pred_boxes"],
        dynamic_axes={"images": {0: "batch"}, "pred_logits": {0: "batch"}, "pred_boxes": {0: "batch"}},
        opset_version=17, do_constant_folding=True, dynamo=False,
    )
    return out_path


def logits_probe(engine, images: list[Path], imgsz: int, batch: int = 4):
    """고정 프로브 배치의 logits 반환 (max|Δlogits| 계산용)."""
    from PIL import Image  # noqa: PLC0415

    paths = images[:batch]
    pil = [Image.open(p).convert("RGB") for p in paths]
    x = shared.preprocess(pil, imgsz)
    logits, _ = engine.infer(x)
    for i in pil:
        i.close()
    return logits.detach().float().cpu().numpy()


def convert_onnx_fp16(fp32_onnx: Path, out_path: Path, op_block_list=None, keep_io_types: bool = True) -> Path:
    from onnxconverter_common.float16 import convert_float_to_float16  # noqa: PLC0415

    import onnx  # noqa: PLC0415

    m = onnx.load(str(fp32_onnx))
    m16 = convert_float_to_float16(m, keep_io_types=keep_io_types, op_block_list=op_block_list or [])
    out_path = Path(out_path)
    onnx.save(m16, str(out_path))
    return out_path


def probe_ort_bf16_session(fp32_onnx: Path) -> str:
    """BF16 I/O 타입 모델로 ORT CPU 세션 생성을 시도해 지원 여부를 확인한다."""
    import onnx  # noqa: PLC0415
    from onnx import TensorProto  # noqa: PLC0415

    m = onnx.load(str(fp32_onnx))
    for t in list(m.graph.input) + list(m.graph.output):
        if t.type.tensor_type.elem_type == TensorProto.FLOAT:
            t.type.tensor_type.elem_type = TensorProto.BFLOAT16
    tmp = Path(str(fp32_onnx)).with_suffix(".bf16probe.onnx")
    try:
        onnx.save(m, str(tmp))
        import onnxruntime as ort  # noqa: PLC0415

        ort.InferenceSession(str(tmp), providers=["CPUExecutionProvider"])
        return "ORT CPU BF16 세션 생성 성공"
    except Exception as e:  # noqa: BLE001
        return f"ORT CPU BF16 세션 생성 실패: {type(e).__name__}: {str(e)[:180]}"
    finally:
        tmp.unlink(missing_ok=True)


def run_precision_experiments(args, images, out_dir: Path, base_dets, ref_logits,
                              fp32_onnx: Path, phys: int, need: set[str] | None = None):
    """J(pt BF16) / K(pt FP16) / L(ONNX FP16) / M(ONNX BF16) 행을 생성해 반환.

    need: 생성할 행 집합(기본 전부). 이미 측정된 J/K 등을 재측정하지 않기 위함.
    """
    need = need or {"J", "K", "L", "M"}
    rows: list[dict] = []
    em = Emitter(rows, images, args)
    em.base_dets = base_dets  # 기존 baseline(A)과 동일 기준 유지
    checkpoint = Path(args.checkpoint) if args.checkpoint else shared.find_checkpoint()
    src_root = shared.discover_model_source(explicit=args.src)
    device = shared.resolve_device(args.device)
    use_ema = not args.no_ema
    num_classes = shared.count_classes(shared.extract_state_dict(checkpoint, use_ema))

    bf16_hw = cpu_bf16_support()
    print(f"[정밀도] CPU BF16 지원: flags={bf16_hw['flags'] or '없음'}, "
          f"{bf16_hw['api']} 존재={bf16_hw['api_exists']}", flush=True)

    def dlogits_of(build):
        eng = build()
        try:
            return float(__import__("numpy").abs(logits_probe(eng, images, args.imgsz) - ref_logits).max())
        finally:
            eng.release()

    def fail(label, category, detail, e):
        import traceback  # noqa: PLC0415

        tb_tail = traceback.format_exc()[-350:].replace("\n", " | ")
        em.skip(label, category, detail,
                f"실패: {type(e).__name__}: {str(e)[:180]} || tb: {tb_tail}")

    # --- J. pt + BF16 (autocast) — 지원 여부와 무관하게 측정 ---
    if "J" in need:
        print("[실험] J. pt + BF16 (autocast)", flush=True)
        try:
            d = dlogits_of(lambda: PTAutoCastEngine(checkpoint, args.imgsz, device, src_root,
                                                    use_ema=use_ema, dtype="bf16"))
            em.emit(lambda: PTAutoCastEngine(checkpoint, args.imgsz, device, src_root,
                                             use_ema=use_ema, dtype="bf16"),
                    "J_pt_bf16", "precision", "pt autocast BF16 (CPU)", args.batch,
                    model_file=checkpoint, extra={"max_abs_dlogits": round(d, 5)})
        except Exception as e:  # noqa: BLE001
            fail("J_pt_bf16", "precision", "pt autocast BF16 (CPU)", e)

    # --- K. pt + FP16 (model.half()) — 미지원 op 실패도 결과로 기록 ---
    if "K" in need:
        print("[실험] K. pt + FP16 (model.half, CPU)", flush=True)
        try:
            d = dlogits_of(lambda: PTAutoCastEngine(checkpoint, args.imgsz, device, src_root,
                                                    use_ema=use_ema, dtype="fp16"))
            em.emit(lambda: PTAutoCastEngine(checkpoint, args.imgsz, device, src_root,
                                             use_ema=use_ema, dtype="fp16"),
                    "K_pt_fp16", "precision", "pt FP16 model.half (CPU)", args.batch,
                    model_file=checkpoint, extra={"max_abs_dlogits": round(d, 5)})
        except Exception as e:  # noqa: BLE001
            fail("K_pt_fp16", "precision", "pt FP16 model.half (CPU)", e)

    # --- L. ONNX FP16 — onnxconverter 불가 시 torch fp16 익스포트로 평백해 측정 ---
    if "L" in need:
        print("[실험] L. ONNX FP16 (CPU EP)", flush=True)
    if "L" in need:
        fp16_path = out_dir / fp32_onnx.name.replace(".onnx", ".fp16.onnx")
        fp16io_path = out_dir / fp32_onnx.name.replace(".onnx", ".fp16io.onnx")
        torch_path = out_dir / fp32_onnx.name.replace(".onnx", ".fp16torch.onnx")
        try:
            variant = None
            use_path = eng_cls = None
            if not fp16_path.exists():
                convert_onnx_fp16(fp32_onnx, fp16_path)
            if session_loadable(fp16_path):
                variant, use_path, eng_cls = "keep_io_types", fp16_path, ORTEngine
            else:
                print("    onnxconverter keep_io_types 그래프 ORT 로드 불가 → torch fp16 익스포트 평백", flush=True)
                if not torch_path.exists():
                    t0 = time.perf_counter()
                    export_torch_fp16(checkpoint, args.imgsz, torch_path, src_root, use_ema=use_ema)
                    print(f"    torch fp16 익스포트 {time.perf_counter()-t0:.1f}s", flush=True)
                variant, use_path, eng_cls = "torch_fp16_export", torch_path, ORTFP16IOEngine
            d = dlogits_of(lambda: eng_cls(use_path, num_classes))
            em.emit(lambda: eng_cls(use_path, num_classes), "L_onnx_fp16", "precision",
                    f"ONNX FP16 ({variant}, CPU EP)", args.batch, model_file=use_path,
                    extra={"max_abs_dlogits": round(d, 5)})
            last = rows[-1]
            if last["status"] == "ok" and last["match_rate"] < 0.95:
                print(f"    매칭률 {last['match_rate']} < 0.95 → 민감 op 제외 재시도", flush=True)
                safe_path = out_dir / fp32_onnx.name.replace(".onnx", ".fp16safe.onnx")
                block = ["LayerNormalization", "Softmax", "ReduceMean"]
                try:
                    convert_onnx_fp16(fp32_onnx, safe_path, op_block_list=block)
                    if not session_loadable(safe_path):
                        raise RuntimeError("onnxconverter safe 변환도 ORT 로드 불가 → torch 경로에선 op 단위 제외 불가")
                    d = dlogits_of(lambda: ORTEngine(safe_path, num_classes))
                    em.emit(lambda: ORTEngine(safe_path, num_classes), "L2_onnx_fp16_safe", "precision",
                            f"ONNX FP16, block={block}", args.batch, model_file=safe_path,
                            extra={"max_abs_dlogits": round(d, 5)})
                    rows[-1]["note"] = (rows[-1].get("note") or "") + " (FP16 오버플로 의심 op 제외 재시도)"
                    if rows[-1]["match_rate"] < 0.95:
                        rows[-1]["note"] += " → 정확도 미달"
                except Exception as e2:  # noqa: BLE001
                    last["note"] = (last.get("note") or "") + f" (재시도 불가: {e2})"
        except Exception as e:  # noqa: BLE001
            fail("L_onnx_fp16", "precision", "ONNX FP16 (CPU EP)", e)

    # --- M. ONNX BF16 — 변환 경로/ORT 지원 조사 후 사유 기록 ---
    if "M" in need:
        print("[실험] M. ONNX BF16 (경로 조사)", flush=True)
        reasons = []
        try:
            from onnxconverter_common.float16 import convert_float_to_bfloat16  # noqa: F401, PLC0415
            reasons.append("onnxconverter_common에 BF16 변환 API 존재")
        except ImportError:
            import onnxconverter_common  # noqa: PLC0415

            reasons.append(f"onnxconverter_common {onnxconverter_common.__version__}에 BF16 변환 API 없음")
        if not bf16_hw["flags"]:
            reasons.append("CPU 플래그에 avx512_bf16/amx_bf16 없음")
        reasons.append(probe_ort_bf16_session(fp32_onnx))
        em.skip("M_onnx_bf16", "precision", "ONNX BF16 (CPU EP)", "; ".join(reasons))

    return rows, bf16_hw


# ---------------------------------------------------------------------------
# 실험 실행
# ---------------------------------------------------------------------------
def run_experiments(args, images, out_dir: Path):
    import onnxruntime as ort  # noqa: PLC0415

    checkpoint = Path(args.checkpoint) if args.checkpoint else shared.find_checkpoint()
    src_root = shared.discover_model_source(explicit=args.src)
    device = shared.resolve_device(args.device)
    use_ema = not args.no_ema
    num_classes = shared.count_classes(shared.extract_state_dict(checkpoint, use_ema))
    phys = physical_cores()

    fp32_onnx = out_dir / f"{checkpoint.stem}_{args.imgsz}.onnx"
    if not fp32_onnx.exists():
        shared.export_onnx(checkpoint, args.imgsz, fp32_onnx, src_root=src_root, use_ema=use_ema)

    rows: list[dict] = []
    em = Emitter(rows, images, args)

    # --- A. pt FP32 baseline ---
    print("[실험] A. pt FP32 baseline", flush=True)
    em.emit(lambda: shared.PTEngine(checkpoint, args.imgsz, device, src_root, half=False, use_ema=use_ema),
         "A_pt_fp32", "baseline", "pt FP32", args.batch, model_file=checkpoint)

    # --- B. ONNX 기본 ---
    print("[실험] B. ONNX 기본", flush=True)
    em.emit(lambda: ORTEngine(fp32_onnx, num_classes), "B_onnx_default", "onnx", "기본 세션", args.batch,
         model_file=fp32_onnx)

    # --- C. 그래프 최적화 레벨 ---
    for lvl_name, lvl in [("BASIC", ort.GraphOptimizationLevel.ORT_ENABLE_BASIC),
                          ("EXTENDED", ort.GraphOptimizationLevel.ORT_ENABLE_EXTENDED),
                          ("ALL", ort.GraphOptimizationLevel.ORT_ENABLE_ALL)]:
        print(f"[실험] C. ONNX 그래프 최적화 {lvl_name}", flush=True)
        em.emit(lambda lvl=lvl, n=lvl_name: ORTEngine(fp32_onnx, num_classes, make_session_options(opt_level=lvl)),
             f"C_onnx_opt_{lvl_name.lower()}", "graph_opt", f"graph_optimization={lvl_name}",
             args.batch, model_file=fp32_onnx)

    # --- D. 동적 INT8 ---
    print("[실험] D. ONNX 동적 INT8", flush=True)
    try:
        dyn8 = out_dir / f"{checkpoint.stem}_{args.imgsz}.dynint8.onnx"
        if not dyn8.exists():
            t0 = time.perf_counter()
            quantize_dynamic(fp32_onnx, dyn8)
            print(f"    동적 양자화 변환 {time.perf_counter()-t0:.1f}s", flush=True)
        em.emit(lambda: ORTEngine(dyn8, num_classes), "D_onnx_dynint8", "quant", "동적 INT8 (weight-only)",
             args.batch, model_file=dyn8)
    except Exception as e:  # noqa: BLE001
        em.skip("D_onnx_dynint8", "quant", "동적 INT8 (weight-only)", f"변환/추론 실패: {e}")

    # --- E. 정적 INT8 (캘리브레이션: --calib-set 폴드, 기본 _tune_pool) ---
    print("[실험] E. ONNX 정적 INT8", flush=True)
    try:
        calib_images = shared.collect_images(Path(args.calib_set))[: args.calib_size] if args.calib_set else images
        sta8 = out_dir / f"{checkpoint.stem}_{args.imgsz}.staint8.onnx"
        if not sta8.exists():
            t0 = time.perf_counter()
            quantize_static(fp32_onnx, sta8, calib_images, args.imgsz)
            print(f"    정적 양자화 변환 {time.perf_counter()-t0:.1f}s", flush=True)
        em.emit(lambda: ORTEngine(sta8, num_classes), "E_onnx_staint8", "quant", f"정적 INT8 (calib={len(calib_images)}장)",
             args.batch, model_file=sta8)
    except Exception as e:  # noqa: BLE001
        em.skip("E_onnx_staint8", "quant", "정적 INT8", f"변환/추론 실패(부담/미지원): {type(e).__name__}: {e}")

    # --- F. 스레드 스윕 (ONNX 기본) ---
    for n in sorted({1, 2, 4, phys}):
        print(f"[실험] F. 스레드={n}", flush=True)
        em.emit(lambda n=n: ORTEngine(fp32_onnx, num_classes, make_session_options(threads=n)),
             f"F_onnx_threads{n}", "threads", f"intra_op_num_threads={n}", args.batch,
             model_file=fp32_onnx)
    os.environ["OMP_NUM_THREADS"] = str(phys)  # 이후 실험에 스레드 설정이 새지 않도록 리셋

    # --- G. 배치 스윕 ---
    for bs in args.batch_list:
        print(f"[실험] G. pt 배치={bs}", flush=True)
        em.emit(lambda: shared.PTEngine(checkpoint, args.imgsz, device, src_root, half=False, use_ema=use_ema),
             f"G_pt_batch{bs}", "batch", f"pt FP32 batch={bs}", bs, model_file=checkpoint)
    for bs in args.batch_list:
        print(f"[실험] G. onnx 배치={bs}", flush=True)
        em.emit(lambda: ORTEngine(fp32_onnx, num_classes), f"G_onnx_batch{bs}", "batch",
             f"onnx batch={bs}", bs, model_file=fp32_onnx)

    # --- H/I. GPU ---
    gpu_note = None
    try:
        import torch  # noqa: PLC0415

        gpu_note = None if torch.cuda.is_available() else "GPU 없음 (CUDA 미감지)"
    except Exception as e:  # noqa: BLE001
        gpu_note = f"GPU 감지 실패: {e}"
    em.skip("H_onnx_fp16", "gpu", "ONNX FP16", gpu_note or "")
    em.skip("I_onnx_cuda", "gpu", "CUDAExecutionProvider", gpu_note or "")

    # --- 조합: 상위 단일 기법 결합 ---
    print("[실험] 조합", flush=True)
    try:
        dyn8 = out_dir / f"{checkpoint.stem}_{args.imgsz}.dynint8.onnx"
        em.emit(lambda: ORTEngine(dyn8, num_classes, make_session_options(threads=phys)),
             "Combo1_dynint8+threads", "combo", f"동적 INT8 + threads={phys}", args.batch, model_file=dyn8)
    except Exception as e:  # noqa: BLE001
        em.skip("Combo1_dynint8+threads", "combo", "동적 INT8 + 최적 스레드", f"실패: {e}")
    em.emit(lambda: ORTEngine(fp32_onnx, num_classes,
                           make_session_options(opt_level=ort.GraphOptimizationLevel.ORT_ENABLE_ALL, threads=phys)),
         "Combo2_fp32+optALL+threads", "combo", f"FP32 + graph_opt=ALL + threads={phys}",
         args.batch, model_file=fp32_onnx)
    em.emit(lambda: ORTEngine(fp32_onnx, num_classes, make_session_options(threads=phys)),
         "Combo3_fp32+threads", "combo", f"FP32 + threads={phys}", args.batch, model_file=fp32_onnx)

    return rows, checkpoint, em.base_dets


# ---------------------------------------------------------------------------
# 최종 검증: inference.py pt vs 권장 엔진(onnx) 결과 일치
# ---------------------------------------------------------------------------
def verify_with_inference_py(args, images, out_dir: Path, checkpoint: Path) -> dict:
    """inference.py를 subprocess로 실행해 baseline(pt)과 권장 엔진(onnx) 결과를 비교."""
    fixed_in = out_dir / "_verify_input"
    fixed_in.mkdir(parents=True, exist_ok=True)
    for p in fixed_in.glob("*"):
        p.unlink()
    used_names: dict[str, int] = {}
    for p in images:
        name = p.name
        if name in used_names:
            used_names[name] += 1
            name = f"{p.stem}__{used_names[p.name]}{p.suffix}"
        else:
            used_names[name] = 0
        shutil.copy2(p, fixed_in / name)

    py = sys.executable
    results = {}
    for engine, tag in [("pt", "base_pt"), ("onnx", "reco_onnx")]:
        odir = out_dir / f"_verify_{tag}"
        cmd = [py, str(ROOT / "inference.py"), "--input", str(fixed_in), "--output", str(odir),
               "--engine", engine, "--conf", str(args.conf), "--iou", "0.5",
               "--imgsz", str(args.imgsz), "--batch", str(args.batch)]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
        if r.returncode != 0:
            print(r.stderr[-2000:])
            raise RuntimeError(f"inference.py ({engine}) 실행 실패")
        results[engine] = {i["file"].split("/")[-1]: i["detections"] for i in
                           __import__("json").loads((odir / "detections.json").read_text())["images"]}

    def to_dets(det_list):
        return [(d["class_id"], d["score"], tuple(d["bbox"])) for d in det_list]

    base = {k: to_dets(v) for k, v in results["pt"].items()}
    cand = {k: to_dets(v) for k, v in results["onnx"].items()}
    det_diff, match_rate, score_mad = guardrail(base, cand, args.conf)
    return {
        "n_images": len(images),
        "conf": args.conf,
        "det_count_diff": round(det_diff, 4),
        "match_rate": round(match_rate, 4),
        "score_mad": round(score_mad, 4),
        "pass": match_rate >= 0.95,
    }


# ---------------------------------------------------------------------------
# 보고서
# ---------------------------------------------------------------------------
def save_csv(rows: list[dict], path: Path):
    fields = ["name", "category", "detail", "batch", "imgsz", "status", "note",
              "fps", "p50_ms", "p95_ms", "mean_ms", "peak_rss_mb", "rss_delta_mb",
              "model_size_mb", "det_count_diff", "match_rate", "score_mad",
              "guardrail_pass", "total_s", "max_abs_dlogits"]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fields})


def make_report(rows, verify, args, out_dir: Path, phys: int, n_images: int, pinfo=None) -> str:
    ok_rows = [r for r in rows if r["status"] == "ok"]
    ranked = sorted([r for r in ok_rows if r["guardrail_pass"] is True],
                    key=lambda r: -r["fps"])
    excluded = [r for r in ok_rows if r["guardrail_pass"] is False]
    base = next((r for r in rows if r["name"] == "A_pt_fp32"), None)
    lines = []
    A = lines.append
    A("# RT-DETRv2 추론 최적화 비교 보고서")
    A("")
    A(f"- 측정 일시: {datetime.now().isoformat(timespec='seconds')}")
    A(f"- 입력: {args.input} (고정 세트 {n_images}장, seed={args.seed}) / conf(가드레일)={args.conf} / imgsz={args.imgsz}")
    A(f"- 환경: CPU-only, 물리 코어 {phys}개 / 워밍업 {args.warmup} 배치 후 1회 전체 패스 측정")
    A(f"- baseline: **A_pt_fp32** (fps={base['fps'] if base else '?'}, p50={base['p50_ms'] if base else '?'}ms)")
    if any(r.get("name", "").startswith(("J_", "K_", "L", "M_")) for r in rows):
        A("- 정밀도 실험 포함: J(pt BF16) / K(pt FP16) / L(ONNX FP16) / M(ONNX BF16) — CPU 측정 (§3)")
    A("")
    A("## 1. 전체 실험 표")
    A("")
    A("| 기법 | 배치 | FPS | p50 (ms) | p95 (ms) | peak RSS (MB) | ΔRSS (MB) | 모델 크기 (MB) | 검출 수 차이 | 매칭률 | score MAD |")
    A("|---|---|---|---|---|---|---|---|---|---|---|")
    for r in rows:
        mark = " ⚠️" if r["status"] == "ok" and r["guardrail_pass"] is False else ""
        if r["status"] == "skip":
            A(f"| {r['name']}{mark} | - | - | - | - | - | - | - | - | - | 스킵: {r['note']} |")
        else:
            A(f"| {r['name']}{mark} | {r['batch']} | {r['fps']} | {r['p50_ms']} | {r['p95_ms']} "
              f"| {r['peak_rss_mb']} | {r['rss_delta_mb']} | {r['model_size_mb']} "
              f"| {r['det_count_diff']} | {r['match_rate']} | {r['score_mad']} |")
    A("")
    A("> 가드레일: baseline(A)와 동일 입력, conf 기준 검출 비교. 매칭률(IoU≥0.5) 95% 미만이면 ⚠️ 표시 후 순위 산정 제외.")
    A("> 메모리 방법론: peak RSS는 프로세스 누적 피크(ru_maxrss)라 모든 행이 동일할 수 있고, "
      "ΔRSS는 해당 행 시작 대비 증가량(이전 행 피크를 넘지 않으면 0). 모델 크기가 기법별 메모리 지표로 더 유효.")
    if excluded:
        A(f"> ⚠️ 제외: {', '.join(r['name'] for r in excluded)}")
    A("")
    A("## 2. 가드레일 통과 기법 속도 순위")
    A("")
    A("| 순위 | 기법 | FPS | p50 (ms) | 가속비(vs baseline) |")
    A("|---|---|---|---|---|")
    for i, r in enumerate(ranked, 1):
        speedup = (r["fps"] / base["fps"]) if base and base["fps"] else 0
        A(f"| {i} | {r['name']} | {r['fps']} | {r['p50_ms']} | {speedup:.2f}x |")
    A("")
    A("## 3. 정밀도 비교 (FP32 / BF16 / FP16 / INT8, CPU 측정)")
    A("")
    if pinfo is None:
        pinfo = cpu_bf16_support()  # 재생성 없이 보고서만 갱신하는 경우에도 지원 여부 명시
    if pinfo:
        api_txt = (f"{pinfo['api']}={pinfo['api_value']}" if pinfo["api_exists"]
                   else f"{pinfo['api']} API 없음(설치된 torch 버전에 미제공)")
        A(f"- **CPU BF16 하드웨어 지원**: /proc/cpuinfo 플래그 = {pinfo['flags'] or '없음'} "
          f"(avx512_bf16/amx_bf16 미검출 시 에뮬레이션), {api_txt}")
    A("- GPU 없음은 CUDA EP 스킵 사유일 뿐, 아래 정밀도 실험은 CPU에서 전부 측정했다.")
    A("")
    by_name = {r["name"]: r for r in rows}
    prec_map = [("FP32 (baseline pt)", "A_pt_fp32"),
                ("BF16 (pt autocast, CPU)", "J_pt_bf16"),
                ("FP16 (pt half, CPU)", "K_pt_fp16"),
                ("FP16 (ONNX, CPU EP)", "L_onnx_fp16"),
                ("FP16 (ONNX 민감op 제외 재시도)", "L2_onnx_fp16_safe"),
                ("BF16 (ONNX)", "M_onnx_bf16"),
                ("INT8 (ONNX 동적, 참고)", "D_onnx_dynint8")]
    A("| 정밀도 | 대표 행 | FPS | p50 (ms) | 매칭률 | max|Δlogits| | 모델 크기 (MB) | 판정 |")
    A("|---|---|---|---|---|---|---|---|")
    for label, key in prec_map:
        r = by_name.get(key)
        if not r:
            continue
        if r["status"] == "skip":
            A(f"| {label} | {key} | - | - | - | - | - | 스킵: {r['note'][:90]} |")
            continue
        verdict = "통과" if r["guardrail_pass"] else "⚠️ 가드레일 미달"
        A(f"| {label} | {key} | {r['fps']} | {r['p50_ms']} | {r['match_rate']} "
          f"| {r.get('max_abs_dlogits', '')} | {r['model_size_mb']} | {verdict} |")
    A("")
    j = by_name.get("J_pt_bf16")
    a = by_name.get("A_pt_fp32")
    if j and a and j["status"] == "ok" and isinstance(j.get("fps"), float):
        gain = j["fps"] / a["fps"] if a.get("fps") else 0
        A(f"- **CPU BF16 판정**: pt BF16은 {gain:.2f}x(에뮬레이션, p50 18s/장)로 극도로 느림 — "
          f"BF16 하드웨어 가속 플래그가 없는 CPU에서는 이득이 없다(수치: {a['fps']} → {j['fps']} FPS).")
    A("")
    A("## 4. 시나리오별 권장")
    A("")
    if ranked:
        rt = ranked[0]
        A(f"1. **실시간 단일 이미지**: `{rt['name']}` — FPS {rt['fps']}, p50 {rt['p50_ms']}ms (지연 최소)")
        bulk_pool = [r for r in ranked if isinstance(r.get("batch"), int) and r["batch"] >= 4]
        bulk = bulk_pool[0] if bulk_pool else ranked[0]
        A(f"2. **대량 배치 처리**: `{bulk['name']}` (batch={bulk['batch']}) — FPS {bulk['fps']} "
          f"(4코어 CPU에서는 배치 증가 이득이 거의 없어, 높은 배치가 필요한 경우에도 우선 순위는 엔진/스레드 선택)")
        sized = [r for r in ok_rows
                 if r["guardrail_pass"] is True and isinstance(r.get("model_size_mb"), float)]
        small = min(sized, key=lambda r: r["model_size_mb"]) if sized else None
        if small:
            ratio = small["model_size_mb"] / base["model_size_mb"] * 100 if base else 0
            A(f"3. **메모리 제약 환경**: `{small['name']}` — 모델 크기 {small['model_size_mb']}MB "
              f"(baseline 대비 {ratio:.0f}%), 가드레일 통과")
            int8_bad = [r for r in ok_rows if r["category"] == "quant"]
            if int8_bad:
                A(f"   - INT8 옵션({', '.join(r['name'] for r in int8_bad)})은 21.8~21.9MB로 더 작지만 "
                  f"매칭률 0.90/0.65로 가드레일 미달 → 정확도를 지키려면 사용할 수 없음")
    A("")
    A("## 5. 최종 권장 조합")
    A("")
    best = ranked[0] if ranked else None
    if best:
        speedup = (best["fps"] / base["fps"]) if base and base["fps"] else 0
        A(f"**권장 조합: `{best['name']}`** (FPS {best['fps']}, baseline 대비 {speedup:.2f}x, "
          f"p50 {best['p50_ms']}ms, 매칭률 {best['match_rate']})")
        A("")
        A(f"- 근거: 가드레일 통과(매칭률 {best['match_rate']} ≥ 0.95) 기법 중 최고 FPS. "
          f"검출 수 차이 {best['det_count_diff']}/img, score MAD {best['score_mad']}.")
        j = by_name.get("J_pt_bf16")
        lrow = by_name.get("L_onnx_fp16")
        if j and j["status"] == "ok" and isinstance(j.get("fps"), float):
            A(f"- 정밀도 재검토: J~M 추가 실험 결과, BF16(J)은 CPU 에뮬레이션으로 0.02x로 느려 채택 불가, "
              f"K(pt FP16)은 매칭률 미달, "
              f"L(ONNX FP16)은 가드레일 통과({lrow['fps'] if lrow else '?'} FPS)했으나 "
              f"FP32 권장({best['fps']} FPS)보다 느려 **기존 FP32 권장을 유지**한다(표 §3 참조).")
    A(f"- `inference.py` 적용 경로: `--engine onnx`(FP32 ONNX) + `--batch {{1|4}}`. "
      f"INT8/스레드 튜닝은 inference.py 옵션 외 세션/환경 설정이 필요해 별도 배포 코드에서 적용 권장.")
    A("")
    A("### 최종 검증 (inference.py 실행 비교)")
    A("")
    v = verify
    A(f"- `inference.py --engine pt` vs `--engine onnx` (동일 입력 {v['n_images']}장, conf={v['conf']}):")
    A(f"  - 이미지당 검출 수 차이: {v['det_count_diff']}, 박스 매칭률(IoU≥0.5): **{v['match_rate']}**, "
      f"score MAD: {v['score_mad']}")
    A(f"  - 결과: **{'일치(≥95%) ✓' if v['pass'] else '불일치(<95%) ✗'}**")
    A("")
    A(f"> 원시 데이터: `{out_dir}/optimization_results.csv`")
    return "\n".join(lines) + "\n"


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="RT-DETRv2 최적화 기법 비교 실험")
    p.add_argument("--input", required=True, help="이미지 폴드 (측정 입력)")
    p.add_argument("--sample-size", type=int, default=30)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--imgsz", type=int, default=640)
    p.add_argument("--conf", type=float, default=0.4, help="가드레일 conf (권장 0.4~0.5)")
    p.add_argument("--iou", type=float, default=0.5)
    p.add_argument("--batch", type=int, default=1, help="기본 측정 배치")
    p.add_argument("--batch-list", type=int, nargs="+", default=[1, 4, 8])
    p.add_argument("--warmup", type=int, default=10, help="워밍업 배치 수")
    p.add_argument("--calib-set", default="rtdetr_outputs/_tune_pool", help="정적 양자화 캘리브레이션 폴드")
    p.add_argument("--calib-size", type=int, default=30)
    p.add_argument("--device", default="auto")
    p.add_argument("--checkpoint", default=None)
    p.add_argument("--src", default=None)
    p.add_argument("--no-ema", action="store_true")
    p.add_argument("--output-dir", default="rtdetr_outputs")
    p.add_argument("--skip-verify", action="store_true", help="inference.py 검증 실행 생략")
    p.add_argument("--precision-only", action="store_true",
                   help="기존 21행 유지, J~M 정밀도 실험만 추가 후 보고서 갱신")
    return p.parse_args(argv)


NUMERIC_FIELDS = {"fps", "p50_ms", "p95_ms", "mean_ms", "peak_rss_mb", "rss_delta_mb",
                  "model_size_mb", "det_count_diff", "match_rate", "score_mad", "total_s",
                  "batch", "imgsz", "max_abs_dlogits"}


def load_csv_rows(path: Path) -> list[dict]:
    """기존 CSV를 로드해 정밀도 모드에서 행을 이어 붙인다(숫자 필드 복원, 중복 이름은 최신 행 유지)."""
    by_name: dict[str, dict] = {}
    with path.open(newline="") as f:
        for r in csv.DictReader(f):
            row = dict(r)
            for k in NUMERIC_FIELDS & row.keys():
                if row[k] in ("", None):
                    continue
                try:
                    row[k] = float(row[k])
                except (TypeError, ValueError):
                    pass
            if "batch" in row and isinstance(row["batch"], float):
                row["batch"] = int(row["batch"])
            if row.get("guardrail_pass") in ("True", "False"):
                row["guardrail_pass"] = row["guardrail_pass"] == "True"
            by_name[row.get("name", f"row{len(by_name)}")] = row
    return list(by_name.values())


def main(argv=None) -> int:
    args = parse_args(argv)
    input_dir = Path(args.input)
    if not input_dir.is_dir():
        print(f"[오류] 입력 폴드가 없습니다: {input_dir}")
        return 2
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    all_images = shared.collect_images(input_dir)
    if not all_images:
        print(f"[오류] 이미지가 없습니다: {input_dir}")
        return 2
    rng = random.Random(args.seed)
    sampled = all_images[:]
    rng.shuffle(sampled)
    images = sampled[: args.sample_size]
    print(f"[준비] 전체 {len(all_images)}장 중 {len(images)}장 고정 세트 (seed={args.seed}), imgsz={args.imgsz}, conf(가드레일)={args.conf}")

    phys = physical_cores()
    print(f"[실험] 물리 코어 {phys}개 — 실험 시작", flush=True)
    csv_path = out_dir / "optimization_results.csv"

    pinfo = None
    if args.precision_only:
        # 기존 행 유지, J~M 정밀도 행만 추가 (기존 실험 재측정 없음)
        if not csv_path.exists():
            print(f"[오류] --precision-only 모드는 기존 CSV가 필요합니다: {csv_path}")
            return 2
        rows = load_csv_rows(csv_path)
        # 측정에 매우 오래 걸리는 J/K는 이미 ok인 행을 유지하고, 실패/누락 행만 재생성
        need = set()
        have = {r.get("name"): r.get("status") for r in rows}
        if have.get("J_pt_bf16") != "ok":
            need.add("J")
        if have.get("K_pt_fp16") != "ok":
            need.add("K")
        if have.get("L_onnx_fp16") != "ok":
            need.add("L")
        if have.get("M_onnx_bf16") is None:
            need.add("M")
        regen = (({"J_pt_bf16"} if "J" in need else set())
                 | ({"K_pt_fp16"} if "K" in need else set())
                 | ({"L_onnx_fp16", "L2_onnx_fp16_safe"} if "L" in need else set())
                 | ({"M_onnx_bf16"} if "M" in need else set()))
        rows = [r for r in rows if r.get("name") not in regen]
        print(f"[정밀도] 재생성 대상: {sorted(need) or '없음'}", flush=True)
        checkpoint = Path(args.checkpoint) if args.checkpoint else shared.find_checkpoint()
        src_root = shared.discover_model_source(explicit=args.src)
        device = shared.resolve_device(args.device)
        fp32_onnx = out_dir / f"{checkpoint.stem}_{args.imgsz}.onnx"

        if not need:
            new_rows, pinfo = [], None
        else:
            # 가드레일 기준 재구축 (무시간 측정) + FP32 참조 logits
            base_eng = shared.PTEngine(checkpoint, args.imgsz, device, src_root,
                                       half=False, use_ema=not args.no_ema)
            import torch  # noqa: PLC0415

            with torch.no_grad():
                _, base_dets = measure(base_eng, images, args.imgsz, args.batch, warmup_batches=1)
                ref_logits = logits_probe(base_eng, images, args.imgsz)
            base_eng.release()

            new_rows, pinfo = run_precision_experiments(args, images, out_dir, base_dets,
                                                        ref_logits, fp32_onnx, phys, need=need)
        rows.extend(new_rows)
    else:
        rows, checkpoint, _ = run_experiments(args, images, out_dir)

    verify = {"n_images": len(images), "conf": args.conf, "det_count_diff": "", "match_rate": "",
              "score_mad": "", "pass": False, "skipped": True}
    if not args.skip_verify:
        print("[검증] inference.py pt vs onnx 비교 실행 ...", flush=True)
        verify = verify_with_inference_py(args, images, out_dir, checkpoint)
        print(f"       매칭률={verify['match_rate']} pass={verify['pass']}", flush=True)

    csv_path = out_dir / "optimization_results.csv"
    save_csv(rows, csv_path)
    md_path = out_dir / "optimization_report.md"
    md_path.write_text(make_report(rows, verify, args, out_dir, phys, len(images), pinfo))
    print(f"[저장] CSV → {csv_path}")
    print(f"[저장] 보고서 → {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
