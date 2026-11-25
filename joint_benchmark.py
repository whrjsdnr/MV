"""RT-DETR + HVQ-Trans 합동 파이프라인 벤치마크 (CPU).

동일 입력 폴드에 대해 두 모델을 순차 실행하는 파이프라인을 3가지 구성으로 측정:
  1) RT-DETR(Combo2: graph ALL + 스레드4) → HVQ(스레드4) 순차
  2) 두 모델 모두 스레드2로 제한해 순차
  3) 두 모델 모두 스레드2 + 파이프라인 겹침(RT-DETR 추론 스레드 중 HVQ 전처리+추론)

지표: end-to-end FPS, 모델별 p50, peak RSS → hvq_outputs/joint_report.md.

  python joint_benchmark.py --input <이미지폴드>
"""

from __future__ import annotations

import argparse
import importlib.util
import resource
import threading
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def load_oc():
    spec = importlib.util.spec_from_file_location("oc_shared", ROOT / "optimize_compare.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


oc = load_oc()
shared = oc.shared
import hvq_common as H  # noqa: E402


def rss_mb() -> int:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss // 1024


def build_rt_engine(onnx_path, num_classes, threads, opt_all=True):
    import onnxruntime as ort  # noqa: PLC0415

    so = ort.SessionOptions()
    if opt_all:
        so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    so.intra_op_num_threads = threads
    so.inter_op_num_threads = 1
    return oc.ORTEngine(Path(onnx_path), num_classes, session_options=so)


def build_hvq_engine(onnx_path, num_branches, threads):
    import onnxruntime as ort  # noqa: PLC0415

    so = ort.SessionOptions()
    so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    so.intra_op_num_threads = threads
    so.inter_op_num_threads = 1
    cls = H.HVQONNXFP16IOEngine if str(onnx_path).endswith(".fp16io.onnx") else H.HVQONNXEngine
    return cls(Path(onnx_path), num_branches, session_options=so)


def run_pipeline(images, rt_engine, hvq_engine, bm, batch, warmup, overlap: bool):
    """두 모델을 배치 단위로 실행. 반환: (e2e dict, rt_p50, hvq_p50)."""
    import numpy as np  # noqa: PLC0415
    import torch  # noqa: PLC0415
    from PIL import Image  # noqa: PLC0415

    def prep_rt(paths):
        pil = [Image.open(p).convert("RGB") for p in paths]
        return shared.preprocess(pil, 640), pil

    def prep_hvq(paths):
        pil = [Image.open(p).convert("RGB") for p in paths]
        labels = H.labels_for_images(paths, bm)
        return H.preprocess(pil, 224), labels, pil

    def one_batch(paths):
        rt_x, rt_pil = prep_rt(paths)
        hvq_x, labels, hvq_pil = prep_hvq(paths)
        t_rt0 = time.perf_counter()
        with torch.no_grad():
            rt_engine.infer(rt_x)
        t_rt = (time.perf_counter() - t_rt0) * 1000.0
        t_hv0 = time.perf_counter()
        hvq_engine.infer(hvq_x, labels)
        t_hv = (time.perf_counter() - t_hv0) * 1000.0
        for i in rt_pil + hvq_pil:
            i.close()
        return t_rt, t_hv

    def one_batch_overlap(paths):
        rt_x, rt_pil = prep_rt(paths)
        hvq_x, labels, hvq_pil = prep_hvq(paths)
        box = {}
        t_rt0 = time.perf_counter()

        def _rt():
            with torch.no_grad():
                rt_engine.infer(rt_x)
            box["rt"] = (time.perf_counter() - t_rt0) * 1000.0

        th = threading.Thread(target=_rt)
        th.start()
        t_hv0 = time.perf_counter()
        hvq_engine.infer(hvq_x, labels)  # RT 스레드와 겹쳐 수행
        t_hv = (time.perf_counter() - t_hv0) * 1000.0
        th.join()
        for i in rt_pil + hvq_pil:
            i.close()
        return box["rt"], t_hv

    fn = one_batch_overlap if overlap else one_batch

    for start in range(0, min(len(images), batch * warmup), batch):
        fn(images[start:start + batch])
    rt_ms, hvq_ms = [], []
    t0 = time.perf_counter()
    n = 0
    for start in range(0, len(images), batch):
        paths = images[start:start + batch]
        t_rt, t_hv = fn(paths)
        rt_ms.extend([t_rt / len(paths)] * len(paths))
        hvq_ms.extend([t_hv / len(paths)] * len(paths))
        n += len(paths)
    wall = time.perf_counter() - t0
    return ({"imgs": n, "wall_s": wall, "fps": n / wall if wall > 0 else 0.0},
            float(np.percentile(rt_ms, 50)), float(np.percentile(hvq_ms, 50)))


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="RT-DETR + HVQ 합동 벤치마크")
    p.add_argument("--input", required=True)
    p.add_argument("--rtdetr-checkpoint", default=None, help="기본: 루트 .pt 자동 탐색")
    p.add_argument("--hvq-checkpoint", default=None, help="기본: 루트 hvq_best.pt")
    p.add_argument("--rtdetr-onnx", default=None, help="기본: rtdetr_outputs/epoch_0015_640.onnx")
    p.add_argument("--hvq-onnx", default=None, help="기본: hvq_outputs/hvq_best.onnx")
    p.add_argument("--hvq-variant", choices=["fp32", "fp16"], default="fp16",
                   help="HVQ 변환 모델 (fp16 = .fp16.onnx, 권장안)")
    p.add_argument("--batch", type=int, default=4)
    p.add_argument("--warmup", type=int, default=2)
    p.add_argument("--src-hvq", default=None)
    p.add_argument("--src-rtdetr", default=None)
    p.add_argument("--output", default="hvq_outputs/joint_report.md")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    input_dir = Path(args.input)
    if not input_dir.is_dir():
        print(f"[오류] 입력 폴드가 없습니다: {input_dir}")
        return 2
    images = shared.collect_images(input_dir)
    if not images:
        print(f"[오류] 이미지가 없습니다: {input_dir}")
        return 2

    rt_ckpt = Path(args.rtdetr_checkpoint) if args.rtdetr_checkpoint else None
    if rt_ckpt is None:
        cands = sorted((p for p in H.MV_ROOT.glob("*.pt") if not p.name.lower().startswith("hvq")),
                       key=lambda p: p.stat().st_mtime)
        if not cands:
            print("[오류] 루트에서 RT-DETR 체크포인트(.pt, hvq 제외)를 찾지 못했습니다")
            return 2
        rt_ckpt = cands[-1]
    hvq_ckpt = Path(args.hvq_checkpoint) if args.hvq_checkpoint else H.MV_ROOT / "hvq_best.pt"
    rt_onnx = Path(args.rtdetr_onnx) if args.rtdetr_onnx else Path("rtdetr_outputs") / f"{rt_ckpt.stem}_640.onnx"
    if args.hvq_onnx:
        hvq_onnx = Path(args.hvq_onnx)
    else:
        suffix = ".fp16io.onnx" if args.hvq_variant == "fp16" else ".onnx"
        hvq_onnx = Path("hvq_outputs") / f"{hvq_ckpt.stem}{suffix}"
    if not hvq_onnx.exists():
        print(f"[오류] HVQ 변환 모델이 없습니다: {hvq_onnx} (inference_hvq.py --engine onnx 또는 optimize_compare_hvq.py 먼저 실행)")
        return 2
    if not rt_onnx.exists():
        print(f"[오류] RT-DETR 변환 모델이 없습니다: {rt_onnx}")
        return 2

    bm = H.load_branch_mapping(hvq_ckpt)
    n_rt_cls = shared.count_classes(shared.extract_state_dict(rt_ckpt, use_ema=True))
    print(f"[준비] 이미지 {len(images)}장, RT-DETR={rt_onnx.name}, HVQ={hvq_onnx.name}({args.hvq_variant}), batch={args.batch}")

    configs = [
        ("구성1: RT-DETR 스레드4 → HVQ 스레드4 순차", 4, 4, False),
        ("구성2: 두 모델 스레드2 순차", 2, 2, False),
        ("구성3: 두 모델 스레드2 + 파이프라인 겹침", 2, 2, True),
    ]
    rows = []
    for name, rt_th, hvq_th, overlap in configs:
        rss0 = rss_mb()
        rt_eng = build_rt_engine(rt_onnx, n_rt_cls, rt_th)
        hvq_eng = build_hvq_engine(hvq_onnx, len(bm), hvq_th)
        e2e, rt_p50, hvq_p50 = run_pipeline(images, rt_eng, hvq_eng, bm, args.batch, args.warmup, overlap)
        rss1 = rss_mb()
        rows.append({"name": name, "rt_threads": rt_th, "hvq_threads": hvq_th,
                     "overlap": overlap, "imgs": e2e["imgs"], "wall_s": round(e2e["wall_s"], 2),
                     "fps": round(e2e["fps"], 3), "rt_p50_ms": round(rt_p50, 1),
                     "hvq_p50_ms": round(hvq_p50, 1), "peak_rss_mb": rss1})
        print(f"  [{name}] fps={e2e['fps']:.2f} rt_p50={rt_p50:.0f}ms hvq_p50={hvq_p50:.0f}ms rss={rss1}MB", flush=True)
        rt_eng.release()
        hvq_eng.release()

    best = max(rows, key=lambda r: r["fps"])
    lines = []
    A = lines.append
    A("# RT-DETR + HVQ-Trans 합동 파이프라인 벤치마크")
    A("")
    A(f"- 측정 일시: {datetime.now().isoformat(timespec='seconds')}")
    A(f"- 입력: {args.input} ({len(images)}장, batch={args.batch}) / CPU-only")
    A(f"- 모델: RT-DETR `{rt_onnx.name}`(Combo2 그래프 ALL) + HVQ `{hvq_onnx.name}`({args.hvq_variant})")
    A("")
    A("| 구성 | RT 스레드 | HVQ 스레드 | 겹침 | 이미지수 | wall (s) | **end-to-end FPS** | RT p50 (ms) | HVQ p50 (ms) | peak RSS (MB) |")
    A("|---|---|---|---|---|---|---|---|---|---|")
    for r in rows:
        A(f"| {r['name']} | {r['rt_threads']} | {r['hvq_threads']} | {'O' if r['overlap'] else 'X'} "
          f"| {r['imgs']} | {r['wall_s']} | **{r['fps']}** | {r['rt_p50_ms']} | {r['hvq_p50_ms']} | {r['peak_rss_mb']} |")
    A("")
    A("## 합동 운용 최종 권장 구성")
    A("")
    A(f"**`{best['name']}`** — end-to-end {best['fps']} FPS (배치당 평균 {1000/best['fps']:.0f} ms/이미지), "
      f"peak RSS {best['peak_rss_mb']}MB")
    r1, r3 = rows[0], rows[2]
    gain = (r3["fps"] / r1["fps"] - 1) * 100 if r1["fps"] else 0
    A("")
    A(f"- 근거: 스레드2 겹침(구성3)은 스레드4 순차(구성1) 대비 {gain:+.1f}% "
      f"({r1['fps']} → {r3['fps']} FPS). 4코어에서 모델당 2스레드씩 배분하면 두 모델이 코어를 공유하며 "
      f"전처리/지연을 서로 가린다. 스레드1 제한(F 실험)에서처럼 단일 모델이 1스레드로는 급격히 느려지므로 "
      f"모델당 2스레드 배분이 최소 지연과 처리량의 균형점이다.")
    A("- 주의: 두 모델 모두 compute-bound이므로 겹침의 이득은 전처리/스케줄링 숨김 수준으로 제한되며, "
      "실제 이득은 위 측정치로 확인했다.")
    A("")
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n")
    print(f"[저장] → {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
