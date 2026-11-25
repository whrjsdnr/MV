"""HVQ-Trans (hvq_best.pt) CPU 추론 최적화 기법별 비교 실험 — 25행.

optimize_compare.py(RT-DETR)의 실험 설계를 그대로 복제한 HVQ 버전:
  A pt FP32 / B ONNX / C 그래프 최적화 3종 / D 동적 INT8 / E 정적 INT8 / F 스레드 /
  G 배치(pt,onnx) / H·I GPU(사유 기록) / J pt BF16 / K pt FP16 / L ONNX FP16 /
  M ONNX BF16 / Combo 3종

가드레일(RT-DETR의 박스 매칭률 대신, 출력 형태에 맞게 교체):
  - 이미지 레벨 점수: baseline 대비 Spearman ≥ 0.98 AND 점수 상대 MAE ≤ 2%
  - 히트맵 출력: 위 + Real-IAD GT 마스크 픽셀 AUROC 하락 ≤ 0.005
  미달 행은 ⚠️ 표시 후 속도 순위에서 제외.

산출물: hvq_outputs/optimization_results_hvq.csv, optimization_report_hvq.md, 변환 모델.
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import os
import random
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent


def load_oc():
    """optimize_compare.py를 읽기 전용으로 재사용(수정 없음)."""
    spec = importlib.util.spec_from_file_location("oc_shared", ROOT / "optimize_compare.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


oc = load_oc()
import hvq_common as H  # noqa: E402


def log(msg: str) -> None:
    print(msg, flush=True)


# ---------------------------------------------------------------------------
# 측정 / 가드레일
# ---------------------------------------------------------------------------
def measure_hvq(engine, images, branch_mapping, batch: int, warmup_batches: int = 10,
                default_cat=None):
    """워밍업 후 1회 전체 패스. 반환: (metrics, scores, heats)."""
    import torch  # noqa: PLC0415
    from PIL import Image  # noqa: PLC0415

    warm = images[:batch * warmup_batches] or images
    for start in range(0, len(warm), batch):
        paths = warm[start:start + batch]
        pil = [Image.open(p).convert("RGB") for p in paths]
        labels = H.labels_for_images(paths, branch_mapping, default_cat)
        with torch.no_grad():
            engine.infer(H.preprocess(pil, 224), labels)
        for i in pil:
            i.close()

    per_image_ms: list[float] = []
    scores: dict[str, float] = {}
    heats: dict[str, np.ndarray] = {}
    t_start = time.perf_counter()
    for start in range(0, len(images), batch):
        paths = images[start:start + batch]
        pil = [Image.open(p).convert("RGB") for p in paths]
        labels = H.labels_for_images(paths, branch_mapping, default_cat)
        batch_t = H.preprocess(pil, 224)
        t0 = time.perf_counter()
        with torch.no_grad():
            pred = engine.infer(batch_t, labels)
        dt = (time.perf_counter() - t0) * 1000.0
        per_image_ms.extend([dt / len(paths)] * len(paths))
        sc = H.scores_from_pred(pred.float())
        for p, s, hm in zip(paths, sc, pred):
            scores[p.name] = float(s)
            heats[p.name] = hm[0].float().cpu().numpy()
        for i in pil:
            i.close()
    total_s = time.perf_counter() - t_start
    lat = sorted(per_image_ms)
    metrics = {
        "fps": len(images) / total_s if total_s > 0 else 0.0,
        "p50_ms": oc._pct(lat, 50),
        "p95_ms": oc._pct(lat, 95),
        "mean_ms": float(np.mean(lat)) if lat else 0.0,
        "total_s": total_s,
    }
    return metrics, scores, heats


def pixel_auroc(heats: dict[str, np.ndarray], gt_masks: dict) -> float | None:
    from sklearn.metrics import roc_auc_score  # noqa: PLC0415

    hs, ms = [], []
    for name, heat in heats.items():
        mask = gt_masks.get(Path(name).stem)
        if mask is None:
            mask = np.zeros_like(heat, dtype="uint8")
        hs.append(heat.flatten())
        ms.append((mask > 0).astype("uint8").flatten())
    if not hs:
        return None
    return float(roc_auc_score(np.concatenate(ms), np.concatenate(hs)))


def guardrail_hvq(base_scores, cand_scores, base_heats, cand_heats, gt_masks):
    """Spearman ≥0.98 AND 상대 MAE ≤2% AND (히트맵 시) 픽셀 AUROC 하락 ≤0.005."""
    from scipy.stats import spearmanr  # noqa: PLC0415

    names = sorted(set(base_scores) | set(cand_scores))
    b = np.array([base_scores[n] for n in names])
    c = np.array([cand_scores[n] for n in names])
    rho = float(spearmanr(b, c).statistic)
    rel_mae = float(np.abs(c - b).mean() / (np.abs(b).mean() + 1e-9))
    auroc_b = auroc_c = drop = None
    if gt_masks:
        auroc_b = pixel_auroc(base_heats, gt_masks)
        auroc_c = pixel_auroc(cand_heats, gt_masks)
        drop = (auroc_b - auroc_c) if (auroc_b is not None and auroc_c is not None) else None
    ok = rho >= 0.98 and rel_mae <= 0.02 and (drop is None or drop <= 0.005)
    return ok, rho, rel_mae, auroc_b, auroc_c, drop


class EmitterH:
    def __init__(self, rows, images, branch_mapping, gt_masks, default_cat=None):
        self.rows = rows
        self.images = images
        self.bm = branch_mapping
        self.gt = gt_masks
        self.default_cat = default_cat
        self.base_scores = None
        self.base_heats = None

    def emit(self, build, label, category, detail, batch, model_file=None, note="", extra=None):
        rss0 = oc.rss_mb()
        engine = build()
        metrics, scores, heats = measure_hvq(engine, self.images, self.bm, batch,
                                             default_cat=self.default_cat)
        rss1 = oc.rss_mb()
        if self.base_scores is None:
            self.base_scores, self.base_heats = scores, heats
        ok, rho, rel_mae, a_b, a_c, drop = guardrail_hvq(
            self.base_scores, scores, self.base_heats, heats, self.gt)
        row = {
            "name": label, "category": category, "detail": detail, "batch": batch,
            "status": "ok", "note": note if ok else f"{note} ⚠️가드레일미달".strip(),
            "fps": round(metrics["fps"], 3), "p50_ms": round(metrics["p50_ms"], 2),
            "p95_ms": round(metrics["p95_ms"], 2), "mean_ms": round(metrics["mean_ms"], 2),
            "peak_rss_mb": rss1, "rss_delta_mb": max(rss1 - rss0, 0),
            "model_size_mb": round(os.path.getsize(model_file) / 1e6, 1)
            if model_file and Path(model_file).exists() else "",
            "spearman": round(rho, 5), "rel_mae": round(rel_mae, 5),
            "auroc_base": round(a_b, 5) if a_b is not None else "",
            "auroc_cand": round(a_c, 5) if a_c is not None else "",
            "auroc_drop": round(drop, 5) if drop is not None else "",
            "guardrail_pass": ok, "total_s": round(metrics["total_s"], 2),
        }
        if extra:
            row.update(extra)
        self.rows.append(row)
        print(f"  [{label}] fps={row['fps']:.2f} p50={row['p50_ms']}ms spearman={rho:.4f} "
              f"relMAE={rel_mae:.5f} pass={ok}", flush=True)
        engine.release()

    def skip(self, label, category, detail, reason):
        self.rows.append({
            "name": label, "category": category, "detail": detail, "batch": "",
            "status": "skip", "note": reason, "fps": "", "p50_ms": "", "p95_ms": "",
            "mean_ms": "", "peak_rss_mb": "", "rss_delta_mb": "", "model_size_mb": "",
            "spearman": "", "rel_mae": "", "auroc_base": "", "auroc_cand": "",
            "auroc_drop": "", "guardrail_pass": "", "total_s": "",
        })
        print(f"  [{label}] SKIP: {reason}", flush=True)


def scores_probe(engine, images, bm, batch: int = 4):
    import torch  # noqa: PLC0415
    from PIL import Image  # noqa: PLC0415

    paths = images[:batch]
    pil = [Image.open(p).convert("RGB") for p in paths]
    labels = H.labels_for_images(paths, bm)
    with torch.no_grad():
        pred = engine.infer(H.preprocess(pil, 224), labels)
    return H.scores_from_pred(pred.float()).numpy()


# ---------------------------------------------------------------------------
# 양자화
# ---------------------------------------------------------------------------
def quantize_static_hvq(fp32_onnx: Path, out_path: Path, images, bm, calib_n: int) -> Path:
    from onnxruntime.quantization import (  # noqa: PLC0415
        CalibrationDataReader, CalibrationMethod, QuantFormat, QuantType, quantize_static,
    )

    class _Reader(CalibrationDataReader):
        def __init__(self, paths):
            self._data = []
            for p in paths:
                from PIL import Image  # noqa: PLC0415

                with Image.open(p) as im:
                    t = H.preprocess([im.convert("RGB")], 224).numpy().astype(np.float32)
                lbl = H.labels_for_images([p], bm).numpy()
                self._data.append({"image": t, "label": lbl})
            self._iter = iter(self._data)

        def get_next(self):
            return next(self._iter, None)

    reader = _Reader(images[:calib_n])
    quantize_static(
        str(fp32_onnx), str(out_path), reader,
        quant_format=QuantFormat.QDQ, per_channel=True,
        weight_type=QuantType.QInt8, activation_type=QuantType.QInt8,
        calibrate_method=CalibrationMethod.MinMax,
    )
    return Path(out_path)


# ---------------------------------------------------------------------------
# 실험 실행
# ---------------------------------------------------------------------------
def run_experiments(args, images, out_dir: Path):
    import onnxruntime as ort  # noqa: PLC0415

    checkpoint = Path(args.checkpoint) if args.checkpoint else H.MV_ROOT / "hvq_best.pt"
    if not checkpoint.is_file():
        cands = sorted(H.MV_ROOT.glob("hvq*.pt"), key=lambda p: p.stat().st_mtime)
        checkpoint = cands[-1]
    src_root = H.discover_source(explicit=args.src)
    device = "cpu"
    if args.device != "cpu":
        import torch  # noqa: PLC0415

        if args.device == "auto":
            device = "cuda:0" if torch.cuda.is_available() else "cpu"
        elif args.device.startswith("cuda") and torch.cuda.is_available():
            device = args.device
        else:
            device = "cpu"
            log(f"[device] {args.device} 요청했으나 CUDA 미사용 가능 → CPU 폴드백")
    phys = oc.physical_cores()
    bm = H.load_branch_mapping(checkpoint)
    log(f"[실험] 분기 {len(bm)}개, 물리 코어 {phys}개")

    fp32_onnx = out_dir / f"{checkpoint.stem}.onnx"
    if not fp32_onnx.exists():
        H.export_onnx(checkpoint, fp32_onnx, src_root=src_root)

    gt_masks = H.load_gt_masks(images) if not args.no_auroc else {}
    log(f"[가드레일] GT 마스크 확보: {sum(1 for v in gt_masks.values() if v is not None)}/{len(images)}장")

    rows: list[dict] = []
    em = EmitterH(rows, images, bm, gt_masks, default_cat=args.category)
    n_br = len(bm)

    def dscores_of(build):
        eng = build()
        try:
            return float(np.abs(scores_probe(eng, images, bm) - ref_scores).max())
        finally:
            eng.release()

    def fail(label, category, detail, e):
        import traceback  # noqa: PLC0415

        tb = traceback.format_exc()[-300:].replace("\n", " | ")
        em.skip(label, category, detail, f"실패: {type(e).__name__}: {str(e)[:160]} || tb: {tb}")

    # FP32 참조 점수 (J~M max|Δscore|용)
    base_eng = H.HVQPTEngine(checkpoint, device, src_root)
    ref_scores = scores_probe(base_eng, images, bm)
    base_eng.release()

    # A
    print("[실험] A. pt FP32 baseline", flush=True)
    em.emit(lambda: H.HVQPTEngine(checkpoint, device, src_root), "A_pt_fp32", "baseline",
            "pt FP32", args.batch, model_file=checkpoint)
    # B
    print("[실험] B. ONNX 기본", flush=True)
    em.emit(lambda: H.HVQONNXEngine(fp32_onnx, n_br), "B_onnx_default", "onnx", "기본 세션",
            args.batch, model_file=fp32_onnx)
    # C
    for lvl_name, lvl in [("BASIC", ort.GraphOptimizationLevel.ORT_ENABLE_BASIC),
                          ("EXTENDED", ort.GraphOptimizationLevel.ORT_ENABLE_EXTENDED),
                          ("ALL", ort.GraphOptimizationLevel.ORT_ENABLE_ALL)]:
        print(f"[실험] C. 그래프 최적화 {lvl_name}", flush=True)
        em.emit(lambda lvl=lvl: H.HVQONNXEngine(fp32_onnx, n_br, oc.make_session_options(opt_level=lvl)),
                f"C_onnx_opt_{lvl_name.lower()}", "graph_opt", f"graph_optimization={lvl_name}",
                args.batch, model_file=fp32_onnx)
    # D
    print("[실험] D. 동적 INT8", flush=True)
    try:
        dyn8 = out_dir / f"{checkpoint.stem}.dynint8.onnx"
        if not dyn8.exists():
            oc.quantize_dynamic(fp32_onnx, dyn8)
        em.emit(lambda: H.HVQONNXEngine(dyn8, n_br), "D_onnx_dynint8", "quant",
                "동적 INT8 (weight-only)", args.batch, model_file=dyn8)
    except Exception as e:  # noqa: BLE001
        fail("D_onnx_dynint8", "quant", "동적 INT8 (weight-only)", e)
    # E
    print("[실험] E. 정적 INT8", flush=True)
    try:
        sta8 = out_dir / f"{checkpoint.stem}.staint8.onnx"
        calib = images[: args.calib_size]
        if not sta8.exists():
            t0 = time.perf_counter()
            quantize_static_hvq(fp32_onnx, sta8, calib, bm, len(calib))
            print(f"    정적 양자화 변환 {time.perf_counter()-t0:.1f}s", flush=True)
        em.emit(lambda: H.HVQONNXEngine(sta8, n_br), "E_onnx_staint8", "quant",
                f"정적 INT8 (calib={len(calib)}장)", args.batch, model_file=sta8)
    except Exception as e:  # noqa: BLE001
        fail("E_onnx_staint8", "quant", "정적 INT8", e)
    # F
    for n in sorted({1, 2, 4, phys}):
        print(f"[실험] F. 스레드={n}", flush=True)
        em.emit(lambda n=n: H.HVQONNXEngine(fp32_onnx, n_br, oc.make_session_options(threads=n)),
                f"F_onnx_threads{n}", "threads", f"intra_op_num_threads={n}",
                args.batch, model_file=fp32_onnx)
    os.environ["OMP_NUM_THREADS"] = str(phys)
    # G
    for bs in args.batch_list:
        print(f"[실험] G. pt 배치={bs}", flush=True)
        em.emit(lambda: H.HVQPTEngine(checkpoint, device, src_root), f"G_pt_batch{bs}",
                "batch", f"pt FP32 batch={bs}", bs, model_file=checkpoint)
    for bs in args.batch_list:
        print(f"[실험] G. onnx 배치={bs}", flush=True)
        em.emit(lambda: H.HVQONNXEngine(fp32_onnx, n_br), f"G_onnx_batch{bs}", "batch",
                f"onnx batch={bs}", bs, model_file=fp32_onnx)
    # H/I
    try:
        import torch  # noqa: PLC0415

        gpu_note = None if torch.cuda.is_available() else "GPU 없음 (CUDA 미감지)"
    except Exception as e:  # noqa: BLE001
        gpu_note = f"GPU 감지 실패: {e}"
    em.skip("H_onnx_fp16", "gpu", "ONNX FP16 (CUDA)", gpu_note or "")
    em.skip("I_onnx_cuda", "gpu", "CUDAExecutionProvider", gpu_note or "")
    # J/K
    for key, dtype, label, detail in [("J", "bf16", "J_pt_bf16", "pt autocast BF16 (CPU)"),
                                      ("K", "fp16", "K_pt_fp16", "pt FP16 model.half (CPU)")]:
        print(f"[실험] {key}. {detail}", flush=True)
        try:
            d = dscores_of(lambda: H.HVQAutoCastEngine(checkpoint, device, src_root, dtype=dtype))
            em.emit(lambda dtype=dtype: H.HVQAutoCastEngine(checkpoint, device, src_root, dtype=dtype),
                    label, "precision", detail, args.batch, model_file=checkpoint,
                    extra={"max_abs_dscores": round(d, 5)})
        except Exception as e:  # noqa: BLE001
            fail(label, "precision", detail, e)
    # L
    print("[실험] L. ONNX FP16 (CPU EP)", flush=True)
    try:
        fp16_path = out_dir / f"{checkpoint.stem}.fp16.onnx"
        fp16io_path = out_dir / f"{checkpoint.stem}.fp16io.onnx"
        variant, use_path, eng_cls = None, None, None
        if not fp16_path.exists():
            oc.convert_onnx_fp16(fp32_onnx, fp16_path)
        if oc.session_loadable(fp16_path):
            variant, use_path, eng_cls = "keep_io_types", fp16_path, H.HVQONNXEngine
        else:
            print("    onnxconverter 그래프 ORT 로드 불가 → torch fp16 익스포트 평백", flush=True)
            if not fp16io_path.exists():
                H.export_onnx(checkpoint, fp16io_path, src_root=src_root, half=True)
            variant, use_path, eng_cls = "torch_fp16_export", fp16io_path, H.HVQONNXFP16IOEngine
        d = dscores_of(lambda: eng_cls(use_path, n_br))
        em.emit(lambda: eng_cls(use_path, n_br), "L_onnx_fp16", "precision",
                f"ONNX FP16 ({variant}, CPU EP)", args.batch, model_file=use_path,
                extra={"max_abs_dscores": round(d, 5)})
        last = rows[-1]
        if last["status"] == "ok" and not last["guardrail_pass"]:
            print("    가드레일 미달 → onnxconverter 민감op 제외 1회 재시도", flush=True)
            safe_path = out_dir / f"{checkpoint.stem}.fp16safe.onnx"
            block = ["LayerNormalization", "Softmax", "ReduceMean"]
            try:
                oc.convert_onnx_fp16(fp32_onnx, safe_path, op_block_list=block)
                if not oc.session_loadable(safe_path):
                    raise RuntimeError("safe 변환도 ORT 로드 불가")
                d = dscores_of(lambda: H.HVQONNXEngine(safe_path, n_br))
                em.emit(lambda: H.HVQONNXEngine(safe_path, n_br), "L2_onnx_fp16_safe", "precision",
                        f"ONNX FP16, block={block}", args.batch, model_file=safe_path,
                        extra={"max_abs_dscores": round(d, 5)})
                rows[-1]["note"] += " (민감op 제외 재시도)"
            except Exception as e2:  # noqa: BLE001
                last["note"] += f" (재시도 불가: {e2})"
    except Exception as e:  # noqa: BLE001
        fail("L_onnx_fp16", "precision", "ONNX FP16 (CPU EP)", e)
    # M
    print("[실험] M. ONNX BF16 (경로 조사)", flush=True)
    reasons = []
    try:
        from onnxconverter_common.float16 import convert_float_to_bfloat16  # noqa: F401, PLC0415
        reasons.append("onnxconverter_common에 BF16 변환 API 존재")
    except ImportError:
        import onnxconverter_common  # noqa: PLC0415

        reasons.append(f"onnxconverter_common {onnxconverter_common.__version__}에 BF16 변환 API 없음")
    hw = oc.cpu_bf16_support()
    if not hw["flags"]:
        reasons.append("CPU 플래그에 avx512_bf16/amx_bf16 없음")
    reasons.append(oc.probe_ort_bf16_session(fp32_onnx))
    em.skip("M_onnx_bf16", "precision", "ONNX BF16 (CPU EP)", "; ".join(reasons))

    # Combo
    print("[실험] 조합", flush=True)
    try:
        dyn8 = out_dir / f"{checkpoint.stem}.dynint8.onnx"
        em.emit(lambda: H.HVQONNXEngine(dyn8, n_br, oc.make_session_options(threads=phys)),
                "Combo1_dynint8+threads", "combo", f"동적 INT8 + threads={phys}",
                args.batch, model_file=dyn8)
    except Exception as e:  # noqa: BLE001
        fail("Combo1_dynint8+threads", "combo", "동적 INT8 + 최적 스레드", e)
    em.emit(lambda: H.HVQONNXEngine(fp32_onnx, n_br,
                                    oc.make_session_options(
                                        opt_level=ort.GraphOptimizationLevel.ORT_ENABLE_ALL,
                                        threads=phys)),
            "Combo2_fp32+optALL+threads", "combo", f"FP32 + graph_opt=ALL + threads={phys}",
            args.batch, model_file=fp32_onnx)
    em.emit(lambda: H.HVQONNXEngine(fp32_onnx, n_br, oc.make_session_options(threads=phys)),
            "Combo3_fp32+threads", "combo", f"FP32 + threads={phys}",
            args.batch, model_file=fp32_onnx)

    return rows, checkpoint, bm, hw


# ---------------------------------------------------------------------------
# 보고서
# ---------------------------------------------------------------------------
FIELDS = ["name", "category", "detail", "batch", "status", "note", "fps", "p50_ms", "p95_ms",
          "mean_ms", "peak_rss_mb", "rss_delta_mb", "model_size_mb", "spearman", "rel_mae",
          "auroc_base", "auroc_cand", "auroc_drop", "guardrail_pass", "total_s", "max_abs_dscores"]


def save_csv(rows, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in FIELDS})


def make_report(rows, ident, args, out_dir: Path, phys: int, n_images: int, hw: dict) -> str:
    ok_rows = [r for r in rows if r["status"] == "ok"]
    ranked = sorted([r for r in ok_rows if r.get("guardrail_pass") is True],
                    key=lambda r: -float(r["fps"]))
    excluded = [r for r in ok_rows if r.get("guardrail_pass") is False]
    base = next((r for r in rows if r["name"] == "A_pt_fp32"), None)
    L = []
    A = L.append
    A("# HVQ-Trans (hvq_best.pt) 추론 최적화 비교 보고서")
    A("")
    A(f"- 측정 일시: {datetime.now().isoformat(timespec='seconds')}")
    A(f"- 입력: {args.input} (고정 세트 {n_images}장, seed={args.seed})")
    A(f"- 환경: CPU-only, 물리 코어 {phys}개 / 워밍업 10 배치 후 1회 전체 패스")
    A(f"- baseline: **A_pt_fp32** (fps={base['fps'] if base else '?'}, p50={base['p50_ms'] if base else '?'}ms)")
    A("")
    A("## 0. 모델 식별 결과 (1단계)")
    A("")
    for k, v in ident.items():
        A(f"- **{k}**: {v}")
    A("")
    A("## 1. 전체 실험 표")
    A("")
    A("| 기법 | 배치 | FPS | p50 (ms) | p95 (ms) | peak RSS (MB) | 크기 (MB) | Spearman | 상대MAE | AUROC(base) | AUROC(cand) | 하락 | 판정 |")
    A("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for r in rows:
        mark = " ⚠️" if r["status"] == "ok" and r.get("guardrail_pass") is False else ""
        if r["status"] == "skip":
            A(f"| {r['name']}{mark} | — | — | — | — | — | — | — | — | — | — | — | 스킵: {r['note'][:60]} |")
        else:
            A(f"| {r['name']}{mark} | {r['batch']} | {r['fps']} | {r['p50_ms']} | {r['p95_ms']} "
              f"| {r['peak_rss_mb']} | {r['model_size_mb']} | {r['spearman']} | {r['rel_mae']} "
              f"| {r['auroc_base']} | {r['auroc_cand']} | {r['auroc_drop']} | "
              f"{'통과' if r['guardrail_pass'] else '⚠️'} |")
    A("")
    A("> 가드레일: Spearman ≥ 0.98 AND 상대 MAE ≤ 2% AND 픽셀 AUROC 하락 ≤ 0.005. 미달 시 ⚠️ 후 순위 제외.")
    if excluded:
        A(f"> ⚠️ 제외: {', '.join(r['name'] for r in excluded)}")
    A("")
    A("## 2. 가드레일 통과 기법 속도 순위")
    A("")
    A("| 순위 | 기법 | FPS | p50 (ms) | 가속비 |")
    A("|---|---|---|---|---|")
    for i, r in enumerate(ranked, 1):
        sp = float(r["fps"]) / float(base["fps"]) if base and float(base["fps"]) else 0
        A(f"| {i} | {r['name']} | {r['fps']} | {r['p50_ms']} | {sp:.2f}x |")
    A("")
    A("## 3. 정밀도 비교 (FP32 / BF16 / FP16 / INT8, CPU 측정)")
    A("")
    A(f"- **CPU BF16 하드웨어 지원**: flags={hw.get('flags') or '없음'}, "
      f"{hw.get('api')} 존재={hw.get('api_exists')}")
    A("- GPU 없음은 CUDA EP 스킵 사유일 뿐, 아래 정밀도 실험은 CPU에서 전부 측정했다.")
    A("")
    by = {r["name"]: r for r in rows}
    for label, key in [("FP32 (baseline pt)", "A_pt_fp32"), ("BF16 (pt autocast)", "J_pt_bf16"),
                       ("FP16 (pt half)", "K_pt_fp16"), ("FP16 (ONNX)", "L_onnx_fp16"),
                       ("BF16 (ONNX)", "M_onnx_bf16"), ("INT8 (동적, 참고)", "D_onnx_dynint8")]:
        r = by.get(key)
        if not r:
            continue
        if r["status"] == "skip":
            A(f"- {label}: 스킵 ({r['note'][:80]})")
        else:
            A(f"- {label}: FPS {r['fps']}, Spearman {r['spearman']}, 상대MAE {r['rel_mae']}, "
              f"max|Δscores| {r.get('max_abs_dscores', '')}, 크기 {r['model_size_mb']}MB, "
              f"{'통과' if r['guardrail_pass'] else '⚠️ 미달'}")
    A("")
    A("## 4. 시나리오별 권장")
    A("")
    if ranked:
        A(f"1. **실시간 단일 이미지**: `{ranked[0]['name']}` — FPS {ranked[0]['fps']}, p50 {ranked[0]['p50_ms']}ms")
        bulk = [r for r in ranked if isinstance(r.get("batch"), int) and int(r["batch"]) >= 4]
        b = bulk[0] if bulk else ranked[0]
        A(f"2. **대량 배치 처리**: `{b['name']}` (batch={b['batch']}) — FPS {b['fps']}")
        sized = [r for r in ok_rows if r.get("guardrail_pass") is True and r.get("model_size_mb") not in ("", None)]
        if sized:
            s = min(sized, key=lambda r: float(r["model_size_mb"]))
            A(f"3. **메모리 제약 환경**: `{s['name']}` — {s['model_size_mb']}MB (baseline {base['model_size_mb']}MB 대비), 가드레일 통과")
    A("")
    A("## 5. 최종 권장 조합")
    A("")
    if ranked:
        best = ranked[0]
        sp = float(best["fps"]) / float(base["fps"]) if base and float(base["fps"]) else 0
        A(f"**권장 조합: `{best['name']}`** (FPS {best['fps']}, baseline 대비 {sp:.2f}x, "
          f"p50 {best['p50_ms']}ms, Spearman {best['spearman']}, 상대MAE {best['rel_mae']})")
        A("")
        A(f"- 근거: 가드레일 통과 기법 중 최고 FPS. AUROC 하락 {best['auroc_drop'] or 0}.")
    A(f"- 원시 데이터: `{out_dir}/optimization_results_hvq.csv`")
    return "\n".join(L) + "\n"


def identify(checkpoint, bm) -> dict:
    ck = H.load_checkpoint_meta(checkpoint)
    val = ck.get("validation") or {}
    aurocs = {k: v.get("image_auroc") for k, v in val.items() if isinstance(v, dict)}
    return {
        "아키텍처": "HVQ-Trans (RuiyingLu/HVQ-Trans @12fbfa9, HVQ_TR_switch의 Real-IAD 30분기·4블록 concat 커스텀)",
        "체크포인트": f"{checkpoint.name} (epoch={ck.get('epoch')}, best_metric={ck.get('best_metric')})",
        "입력 해상도": "224x224 (ImageNet 정규화, 14x14 토큰)",
        "백본": "efficientnet_b4 (동결, outblocks [1,5,9,21] → 4블록 업샘플 concat 272ch)",
        "출력 형태": "픽셀 히트맵 224x224 (재구성 L2 거리, x16 업샘플) + 이미지 레벨 점수 = 히트맵 평균",
        "분기/카테고리": f"{len(bm)}개 (branch_mapping), 카테고리당 VQ 코드북 5단계",
        "정상/이상 기준": f"학습 시 카테고리별 validation threshold 존재 (예: audiojack={val.get('audiojack', {}).get('threshold')}), "
                        f"점수가 threshold 초과 시 이상 (image_auroc 평균 {np.mean(list(aurocs.values())) if aurocs else '?'})",
    }


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="HVQ-Trans 최적화 기법 비교 (25행)")
    p.add_argument("--input", required=True)
    p.add_argument("--sample-size", type=int, default=30)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--batch", type=int, default=1)
    p.add_argument("--batch-list", type=int, nargs="+", default=[1, 4, 8])
    p.add_argument("--warmup", type=int, default=10)
    p.add_argument("--calib-size", type=int, default=30)
    p.add_argument("--device", default="auto")
    p.add_argument("--checkpoint", default=None)
    p.add_argument("--src", default=None)
    p.add_argument("--category", default=None, help="카테고리 미추정 이미지용 기본 분기")
    p.add_argument("--no-auroc", action="store_true", help="GT 마스크 AUROC 가드레일 생략")
    p.add_argument("--output-dir", default="hvq_outputs")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    input_dir = Path(args.input)
    if not input_dir.is_dir():
        print(f"[오류] 입력 폴드가 없습니다: {input_dir}")
        return 2
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    all_images = H.collect_images(input_dir)
    if not all_images:
        print(f"[오류] 이미지가 없습니다: {input_dir}")
        return 2
    rng = random.Random(args.seed)
    sampled = all_images[:]
    rng.shuffle(sampled)
    images = sampled[: args.sample_size]
    print(f"[준비] 전체 {len(all_images)}장 중 {len(images)}장 고정 세트 (seed={args.seed})")

    rows, checkpoint, bm, hw = run_experiments(args, images, out_dir)

    ident = identify(checkpoint, bm)
    csv_path = out_dir / "optimization_results_hvq.csv"
    save_csv(rows, csv_path)
    md_path = out_dir / "optimization_report_hvq.md"
    md_path.write_text(make_report(rows, ident, args, out_dir, oc.physical_cores(), len(images), hw))
    print(f"[저장] CSV → {csv_path}")
    print(f"[저장] 보고서 → {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
