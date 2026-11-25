"""HVQ-Trans (hvq_best.pt) 이상탐지 추론 CLI.

inference.py와 동일한 규약: --input/--output/--engine {pt,onnx}/--imgsz/--batch/--device/--half.
이미지별 이상 점수(히트맵 평균) JSON + 히트맵 시각화 저장.

  python inference_hvq.py --input <이미지폴드> [--output hvq_outputs/infer] [--engine onnx]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import hvq_common as H


def log(msg: str) -> None:
    print(msg, flush=True)


def save_heatmap_vis(image_path: Path, pred, out_path: Path) -> None:
    """히트맵(jet 컬러) + 원본 오버레이 저장."""
    import numpy as np  # noqa: PLC0415
    from PIL import Image  # noqa: PLC0415

    heat = pred[0].cpu().numpy()
    heat = (heat - heat.min()) / (heat.max() - heat.min() + 1e-9)
    try:
        import matplotlib.cm as cm  # noqa: PLC0415

        rgba = cm.get_cmap("jet")(heat)[..., :3]
    except Exception:  # noqa: BLE001
        rgba = np.stack([heat, np.zeros_like(heat), 1 - heat], axis=-1)
    heat_img = Image.fromarray((rgba * 255).astype("uint8"))

    with Image.open(image_path) as img:
        base = img.convert("RGB").resize(heat_img.size)
    overlay = Image.blend(base, heat_img, alpha=0.45)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    overlay.save(out_path)


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="HVQ-Trans 이상탐지 추론 (pt/onnx)")
    p.add_argument("--input", required=True, help="이미지 폴드")
    p.add_argument("--output", default="hvq_outputs/infer", help="출력 폴드")
    p.add_argument("--engine", choices=["pt", "onnx"], default="pt")
    p.add_argument("--checkpoint", default=None, help="기본: 루트의 hvq_best.pt 자동 탐색")
    p.add_argument("--src", default=None, help="HVQ 소스 스냅샷 경로")
    p.add_argument("--imgsz", type=int, default=224)
    p.add_argument("--batch", type=int, default=4)
    p.add_argument("--device", default="auto")
    p.add_argument("--half", action="store_true", help="FP16 (CUDA에서만 자동 적용)")
    p.add_argument("--category", default=None, help="모든 이미지를 이 카테고리로 처리 (미지정 시 자동 추정)")
    p.add_argument("--max-images", type=int, default=None)
    p.add_argument("--save-heatmaps", action="store_true", default=True)
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    input_dir = Path(args.input)
    if not input_dir.is_dir():
        log(f"[오류] 입력 폴드가 없습니다: {input_dir}")
        return 2
    checkpoint = Path(args.checkpoint) if args.checkpoint else H.MV_ROOT / "hvq_best.pt"
    if not checkpoint.is_file():
        cands = sorted(H.MV_ROOT.glob("hvq*.pt"), key=lambda p: p.stat().st_mtime)
        if not cands:
            log(f"[오류] 체크포인트를 찾지 못했습니다: {checkpoint}")
            return 2
        checkpoint = cands[-1]
    device = "cpu"
    if args.device != "cpu":
        import torch  # noqa: PLC0415

        if args.device == "auto":
            device = "cuda:0" if torch.cuda.is_available() else "cpu"
        elif args.device.startswith("cuda") and torch.cuda.is_available():
            device = args.device
        else:
            log(f"[device] {args.device} 요청했으나 CUDA 미사용 가능 → CPU 폴드백")
    src_root = H.discover_source(explicit=args.src)

    images = H.collect_images(input_dir)
    if args.max_images:
        images = images[: args.max_images]
    if not images:
        log(f"[오류] 이미지가 없습니다: {input_dir}")
        return 2

    out_dir = Path(args.output)
    heat_dir = out_dir / "heatmaps"
    heat_dir.mkdir(parents=True, exist_ok=True)

    log(f"[준비] 이미지 {len(images)}장, checkpoint={checkpoint.name}, engine={args.engine}, "
        f"device={device}, batch={args.batch}")

    if args.engine == "pt":
        engine = H.HVQPTEngine(checkpoint, device, src_root, half=args.half)
    else:
        onnx_path = out_dir / f"{checkpoint.stem}.onnx"
        if not onnx_path.exists():
            log(f"[onnx] 변환 모델이 없어 변환을 수행합니다: {onnx_path.name}")
            H.export_onnx(checkpoint, onnx_path, src_root=src_root)
        engine = H.HVQONNXEngine(onnx_path, 30)

    branch_mapping = engine.branch_mapping if hasattr(engine, "branch_mapping") else H.load_branch_mapping(checkpoint)

    from PIL import Image  # noqa: PLC0415
    from tqdm import tqdm  # noqa: PLC0415

    results = []
    forward_ms = 0.0
    wall_start = time.perf_counter()
    iterator = tqdm(range(0, len(images), args.batch), desc="추론", unit="batch")
    for start in iterator:
        paths = images[start:start + args.batch]
        pil = [Image.open(p).convert("RGB") for p in paths]
        batch = H.preprocess(pil, args.imgsz)
        labels = H.labels_for_images(paths, branch_mapping, default=args.category)
        t0 = time.perf_counter()
        pred = engine.infer(batch, labels)
        forward_ms += (time.perf_counter() - t0) * 1000.0
        scores = H.scores_from_pred(pred)
        for path, score, hm, cat in zip(paths, scores, pred, pil):
            item = {
                "file": str(path),
                "category": H.resolve_category(path, branch_mapping, args.category) or args.category,
                "score": round(float(score), 4),
            }
            if args.save_heatmaps:
                vis = heat_dir / (path.stem + ".jpg")
                save_heatmap_vis(path, hm, vis)
                item["heatmap"] = str(vis)
            results.append(item)
            cat.close()
        for i in pil:
            i.close()
    wall_s = time.perf_counter() - wall_start
    engine.release()

    payload = {
        "checkpoint": str(checkpoint),
        "engine": args.engine,
        "imgsz": args.imgsz,
        "n_images": len(images),
        "forward_ms_per_img": round(forward_ms / len(images), 1),
        "fps_model": round(len(images) / (forward_ms / 1000.0), 3),
        "fps_pipeline": round(len(images) / wall_s, 3),
        "scores": results,
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "anomaly_scores.json"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2))

    scores = [r["score"] for r in results]
    log("")
    log("=" * 58)
    log(f"[요약] 엔진={args.engine}  imgsz={args.imgsz}")
    log(f"  총 이미지 수        : {len(images)}")
    log(f"  평균 추론 시간      : {forward_ms / len(images):.1f} ms/img (모델 forward)")
    log(f"  FPS                 : {len(images) / (forward_ms / 1000.0):.2f} (모델) / "
        f"{len(images) / wall_s:.2f} (전체)")
    log(f"  점수 범위           : {min(scores):.2f} ~ {max(scores):.2f} (평균 {sum(scores)/len(scores):.2f})")
    log(f"[저장] JSON → {json_path}")
    log(f"[저장] 히트맵 {len(results)}장 → {heat_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
