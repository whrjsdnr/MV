"""RT-DETRv2 추론 엔진 벤치마크 (pt vs onnx × imgsz × batch).

처리량(FPS)과 지연시간(p50/p95)을 측정해 마크다운 표로 출력하고 benchmark_result.md로 저장한다.
전처리/후처리는 두 엔진이 동일 코드를 사용하므로 비교가 공정하다.

실행:
  python benchmark.py --input <이미지폴드> [--sample-size 60] [--imgsz 640 960 1280]
"""

from __future__ import annotations

import argparse
import importlib.util
import platform
import random
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path


def load_shared():
    here = Path(__file__).resolve().parent
    spec = importlib.util.spec_from_file_location("rtdetr_pipeline_shared", here / "inference.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


shared = load_shared()


def percentile(vals: list[float], q: float) -> float:
    if not vals:
        return 0.0
    s = sorted(vals)
    idx = min(len(s) - 1, max(0, int(round((q / 100.0) * (len(s) - 1)))))
    return s[idx]


def bench_config(engine, images, imgsz, batch_size, warmup_batches, reps):
    """한 (engine, imgsz, batch) 설정을 측정한다."""
    import torch  # noqa: PLC0415
    from PIL import Image  # noqa: PLC0415

    # 워밍업
    warm = images[:batch_size * warmup_batches] or images[:1]
    for start in range(0, len(warm), batch_size):
        paths = warm[start:start + batch_size]
        pil = [Image.open(p).convert("RGB") for p in paths]
        batch = shared.preprocess(pil, imgsz)
        with torch.no_grad() if engine.name == "pt" else _nullctx():
            engine.infer(batch)

    per_image_ms: list[float] = []
    fwd_ms = 0.0
    total_start = time.perf_counter()
    total_imgs = 0
    for _ in range(reps):
        for start in range(0, len(images), batch_size):
            paths = images[start:start + batch_size]
            pil = [Image.open(p).convert("RGB") for p in paths]
            orig = torch.tensor([[i.width, i.height] for i in pil])
            batch = shared.preprocess(pil, imgsz)
            t0 = time.perf_counter()
            logits, boxes = engine.infer(batch)
            fwd_ms += (time.perf_counter() - t0) * 1000.0
            shared.postprocess(logits, boxes, orig, conf=0.25, iou=0.5)
            dt = (time.perf_counter() - t0) * 1000.0
            per_image_ms.extend([dt / len(paths)] * len(paths))
            total_imgs += len(paths)
            for i in pil:
                i.close()
    total_s = time.perf_counter() - total_start
    return {
        "imgs": total_imgs,
        "p50_ms": percentile(per_image_ms, 50),
        "p95_ms": percentile(per_image_ms, 95),
        "mean_ms": statistics.mean(per_image_ms) if per_image_ms else 0.0,
        "fps": total_imgs / total_s if total_s > 0 else 0.0,
        "fwd_ms_img": fwd_ms / max(total_imgs, 1),
        "total_s": total_s,
    }


class _nullctx:
    def __enter__(self):
        return None

    def __exit__(self, *a):
        return False


def env_info(device: str) -> dict:
    import torch  # noqa: PLC0415

    info = {
        "python": platform.python_version(),
        "torch": torch.__version__,
        "torchvision": __import__("torchvision").__version__,
        "device": device,
        "cpu_count": os_cpu_count(),
        "date": datetime.now().isoformat(timespec="seconds"),
    }
    try:
        import onnxruntime  # noqa: PLC0415

        info["onnxruntime"] = onnxruntime.__version__
    except ImportError:
        info["onnxruntime"] = "(미설치)"
    return info


def os_cpu_count() -> int:
    try:
        return len(__import__("os").sched_getaffinity(0))
    except (AttributeError, OSError):
        return __import__("os").cpu_count() or 0


def make_markdown(rows: list[dict], info: dict, args) -> str:
    lines = []
    lines.append("# RT-DETRv2 추론 벤치마크 결과")
    lines.append("")
    lines.append(f"- 측정 일시: {info['date']}")
    lines.append(f"- Python {info['python']} / torch {info['torch']} / torchvision {info['torchvision']} / onnxruntime {info['onnxruntime']}")
    lines.append(f"- 장치: {info['device']} (CPU 코어 {info['cpu_count']}개, FP16={'사용' if info['device'].startswith('cuda') else '미지원(CPU)'})")
    lines.append(f"- 입력: {args.input} (샘플 {args.sample_size}장, seed={args.seed}, reps={args.reps})")
    lines.append(f"- 고정 파라미터: conf=0.25, iou=0.5 / 지연시간은 배치당 벽시계÷배치크기 (전처리+추론+후처리)")
    lines.append("")
    lines.append("| 엔진 | imgsz | batch | 이미지수 | p50 (ms) | p95 (ms) | 평균 (ms) | FPS(전체) | forward ms/img | 총 소요(s) |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|")
    for r in sorted(rows, key=lambda x: (x["engine"], x["imgsz"], x["batch"])):
        lines.append(
            f"| {r['engine']} | {r['imgsz']} | {r['batch']} | {r['imgs']} "
            f"| {r['p50_ms']:.1f} | {r['p95_ms']:.1f} | {r['mean_ms']:.1f} "
            f"| {r['fps']:.2f} | {r['fwd_ms_img']:.1f} | {r['total_s']:.1f} |"
        )
    lines.append("")
    if rows:
        best = max(rows, key=lambda x: x["fps"])
        lines.append(f"**최고 처리량**: {best['engine']} @ imgsz={best['imgsz']} batch={best['batch']} "
                     f"→ {best['fps']:.2f} FPS (p50 {best['p50_ms']:.1f} ms)")
    lines.append("")
    lines.append("> 참고: 동일 전처리/후처리 코드를 사용하므로 엔진 간 비교는 모델 실행 부분 차이를 반영한다.")
    return "\n".join(lines) + "\n"


def print_table(rows: list[dict]) -> None:
    print("\n[벤치마크 결과]")
    header = ("engine", "imgsz", "batch", "imgs", "p50_ms", "p95_ms", "mean_ms", "fps", "fwd_ms/img", "total_s")
    print("  " + "  ".join(header))
    for r in sorted(rows, key=lambda x: (x["engine"], x["imgsz"], x["batch"])):
        print(f"  {r['engine']:<6}{r['imgsz']:<7}{r['batch']:<7}{r['imgs']:<8}"
              f"{r['p50_ms']:<9.1f}{r['p95_ms']:<9.1f}{r['mean_ms']:<10.1f}"
              f"{r['fps']:<10.2f}{r['fwd_ms_img']:<14.1f}{r['total_s']:.1f}")


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="RT-DETRv2 추론 벤치마크 (pt vs onnx)")
    p.add_argument("--input", required=True, help="이미지 폴드")
    p.add_argument("--sample-size", type=int, default=60)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--imgsz", type=int, nargs="+", default=[640, 960, 1280])
    p.add_argument("--batch", type=int, nargs="+", default=[1, 4])
    p.add_argument("--engine", nargs="+", choices=["pt", "onnx"], default=["pt", "onnx"])
    p.add_argument("--reps", type=int, default=1, help="전체 패스 반복 횟수")
    p.add_argument("--warmup-batches", type=int, default=2)
    p.add_argument("--device", default="auto")
    p.add_argument("--checkpoint", default=None)
    p.add_argument("--src", default=None)
    p.add_argument("--no-ema", action="store_true")
    p.add_argument("--output", default="benchmark_result.md", help="마크다운 저장 경로")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    input_dir = Path(args.input)
    if not input_dir.is_dir():
        print(f"[오류] 입력 폴드가 없습니다: {input_dir}")
        return 2

    checkpoint = Path(args.checkpoint) if args.checkpoint else shared.find_checkpoint()
    src_root = shared.discover_model_source(explicit=args.src)
    device = shared.resolve_device(args.device)
    use_ema = not args.no_ema
    half = device.startswith("cuda")  # FP16 자동 판단: CUDA에서만 활성

    all_images = shared.collect_images(input_dir)
    if not all_images:
        print(f"[오류] 이미지가 없습니다: {input_dir}")
        return 2
    rng = random.Random(args.seed)
    sampled = all_images[:]
    rng.shuffle(sampled)
    images = sampled[: args.sample_size]
    print(f"[준비] 전체 {len(all_images)}장 중 {len(images)}장 샘플링 (seed={args.seed}), device={device}, FP16={half}")

    info = env_info(device)
    rows: list[dict] = []
    for engine_name in args.engine:
        for imgsz in args.imgsz:
            if engine_name == "pt":
                engine = shared.PTEngine(checkpoint, imgsz, device, src_root,
                                         half=half, use_ema=use_ema)
            else:
                onnx_path = Path(args.output).parent / f"{checkpoint.stem}_{imgsz}.onnx"
                if not onnx_path.exists():
                    shared.export_onnx(checkpoint, imgsz, onnx_path, src_root=src_root, use_ema=use_ema)
                engine = shared.ONNXEngine(
                    onnx_path, num_classes=shared.count_classes(
                        shared.extract_state_dict(checkpoint, use_ema)))
            for bs in args.batch:
                print(f"[측정] {engine_name} imgsz={imgsz} batch={bs} ...", flush=True)
                r = bench_config(engine, images, imgsz, bs, args.warmup_batches, args.reps)
                r.update({"engine": engine_name, "imgsz": imgsz, "batch": bs})
                rows.append(r)
                print(f"       fps={r['fps']:.2f}  p50={r['p50_ms']:.1f}ms  p95={r['p95_ms']:.1f}ms", flush=True)
            engine.release()

    print_table(rows)
    md = make_markdown(rows, info, args)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md)
    print(f"\n[저장] 마크다운 → {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
