"""RT-DETRv2 추론 하이퍼파라미터 그리드 탐색.

conf × iou(NMS) × imgsz 조합을 그리드 탐색하고, 정답 라벨 유무에 따라 기준을 자동 전환한다.
  - 라벨 미발견(기본): 1) 검출 수 안정성 2) 고신뢰 검출 비율 3) 속도 순으로 랭킹
  - 라벨 발견(YOLO txt / COCO json): mAP50-95 기준 랭킹

실행:
  python tune_inference.py --input <이미지폴드> [--sample-size 50] [--output rtdetr_outputs/tune_results.csv]

공통 유틸(모델 로딩, 전처리/후처리, 결과 저장)은 inference.py를 재사용한다.
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import itertools
import random
import sys
from pathlib import Path


def load_shared():
    """루트 inference.py를 파일 경로로 직접 로드(패키지 이름 충돌 회피)."""
    here = Path(__file__).resolve().parent
    spec = importlib.util.spec_from_file_location("rtdetr_pipeline_shared", here / "inference.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


shared = load_shared()


# ---------------------------------------------------------------------------
# 라벨 자동 발견 / mAP50-95
# ---------------------------------------------------------------------------
def find_yolo_labels(image_paths: list[Path]) -> dict[Path, Path] | None:
    """이미지별 YOLO 포맷 라벨(.txt)을 찾는다. 80% 이상 커버 시에만 사용."""
    found: dict[Path, Path] = {}
    for img in image_paths:
        candidates = [
            img.with_suffix(".txt"),
            img.parent.parent / "labels" / img.parent.name / (img.stem + ".txt"),
            img.parent / "labels" / (img.stem + ".txt"),
        ]
        for c in candidates:
            if c.is_file():
                found[img] = c
                break
    if image_paths and len(found) >= 0.8 * len(image_paths):
        return found
    return None


def parse_yolo_label(path: Path, img_w: int, img_h: int) -> list[tuple[int, tuple[float, float, float, float]]]:
    """YOLO 라인(cls cx cy w h, 0..1) → (cls, (x1,y1,x2,y2)) 절대좌표."""
    gts = []
    for line in Path(path).read_text().splitlines():
        parts = line.split()
        if len(parts) < 5:
            continue
        c = int(float(parts[0]))
        cx, cy, w, h = (float(v) for v in parts[1:5])
        x1, y1 = (cx - w / 2) * img_w, (cy - h / 2) * img_h
        x2, y2 = (cx + w / 2) * img_w, (cy + h / 2) * img_h
        gts.append((c, (x1, y1, x2, y2)))
    return gts


def find_coco_json(input_dir: Path) -> Path | None:
    for p in sorted(input_dir.glob("*.json")):
        try:
            head = p.read_text()[:2000]
        except OSError:
            continue
        if '"annotations"' in head and '"images"' in head and '"categories"' in head:
            return p
    return None


def iou_xyxy(a: tuple, b: tuple) -> float:
    x1 = max(a[0], b[0]); y1 = max(a[1], b[1])
    x2 = min(a[2], b[2]); y2 = min(a[3], b[3])
    iw, ih = max(0.0, x2 - x1), max(0.0, y2 - y1)
    inter = iw * ih
    area_a = max(0.0, a[2] - a[0]) * max(0.0, a[3] - a[1])
    area_b = max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


def compute_map(all_dets: list[list[tuple[int, float, tuple]]],
                all_gts: list[list[tuple[int, tuple]]],
                class_ids: list[int],
                iou_thresholds=None) -> tuple[float, float]:
    """COCO 스타일 mAP50-95와 mAP50 (numpy only, 점수 내림차순 그리디 매칭)."""
    if iou_thresholds is None:
        iou_thresholds = [round(0.5 + 0.05 * i, 2) for i in range(10)]
    aps_per_thr: list[float] = []
    for thr in iou_thresholds:
        ap_list = []
        for c in class_ids:
            dets = []  # (score, img_idx, bbox)
            for idx, dlist in enumerate(all_dets):
                for (cls, score, box) in dlist:
                    if cls == c:
                        dets.append((score, idx, box))
            dets.sort(key=lambda x: -x[0])
            n_gt = sum(1 for glist in all_gts for (cls, _) in glist if cls == c)
            if n_gt == 0:
                continue
            matched = [set() for _ in all_gts]
            tp = []
            fp = []
            for score, idx, box in dets:
                best_iou, best_j = 0.0, -1
                for j, (cls, gbox) in enumerate(all_gts[idx]):
                    if cls != c or j in matched[idx]:
                        continue
                    v = iou_xyxy(box, gbox)
                    if v > best_iou:
                        best_iou, best_j = v, j
                if best_iou >= thr and best_j >= 0:
                    matched[idx].add(best_j)
                    tp.append(1); fp.append(0)
                else:
                    tp.append(0); fp.append(1)
            if not dets:
                ap_list.append(0.0)
                continue
            cum_tp = 0; cum_fp = 0
            precisions = []
            recalls = []
            for t, f in zip(tp, fp):
                cum_tp += t; cum_fp += f
                precisions.append(cum_tp / (cum_tp + cum_fp))
                recalls.append(cum_tp / n_gt)
            # 101-point interpolation envelope
            ap = 0.0
            for r in [i / 100 for i in range(101)]:
                p_max = 0.0
                for p, rc in zip(precisions, recalls):
                    if rc >= r:
                        p_max = max(p_max, p)
                ap += p_max
            ap_list.append(ap / 101.0)
        aps_per_thr.append(sum(ap_list) / len(ap_list) if ap_list else 0.0)
    map50_95 = sum(aps_per_thr) / len(aps_per_thr)
    return map50_95, aps_per_thr[0]


# ---------------------------------------------------------------------------
# 지표 계산
# ---------------------------------------------------------------------------
def percentile(sorted_vals: list[float], q: float) -> float:
    if not sorted_vals:
        return 0.0
    idx = min(len(sorted_vals) - 1, max(0, int(round((q / 100.0) * (len(sorted_vals) - 1)))))
    return sorted_vals[idx]


def run_combo(engine, images, conf, iou, imgsz, batch):
    results, stats = shared.run_inference(images, engine, conf=conf, iou=iou,
                                          imgsz=imgsz, batch_size=batch, show_progress=False)
    s = shared.detect_summary(results)
    lat = sorted(stats["per_image_forward_ms"])
    row = {
        "conf": conf, "iou": iou, "imgsz": imgsz, "engine": engine.name,
        "n_images": len(images),
        "mean_dets": round(s["mean_dets_per_img"], 4),
        "zero_det_frac": round(s["zero_det_images"] / max(len(images), 1), 4),
        "max_dets": s["max_dets_in_img"],
        "mean_score": round(s["mean_score"], 4),
        "high_conf_ratio": round(s["high_conf_ratio"], 4),
        "fwd_ms_mean": round(stats["forward_ms"] / max(len(images), 1), 2),
        "p50_ms": round(percentile(lat, 50), 2),
        "fps": round(len(images) / (stats["wall_s"] or 1e-9), 3),
    }
    det_for_map = [
        [(d["class_id"], d["score"], tuple(d["bbox"])) for d in r["detections"]]
        for r in results
    ]
    return row, det_for_map


def rank_no_label(rows: list[dict]) -> list[dict]:
    """라벨 없음: 1) 검출 수 안정성(중앙값에서의 편차로 급격한 과다/과소 제외)
    2) 고신뢰 검출 비율 3) 속도 순 랭킹."""
    dets = sorted(r["mean_dets"] for r in rows)
    med = percentile(dets, 50)
    q1, q3 = percentile(dets, 25), percentile(dets, 75)
    iqr = max(q3 - q1, 1e-6)
    for r in rows:
        r["stability_dev"] = abs(r["mean_dets"] - med)
        r["excluded"] = r["stability_dev"] > 1.5 * iqr
    pool = [r for r in rows if not r["excluded"]] or rows
    pool.sort(key=lambda r: (-r["high_conf_ratio"], -r["mean_score"], -r["fps"]))
    for i, r in enumerate(pool):
        r["rank"] = i + 1
    return pool


def rank_with_map(rows: list[dict]) -> list[dict]:
    rows.sort(key=lambda r: -r["map50_95"])
    for i, r in enumerate(rows):
        r["rank"] = i + 1
    return rows


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def _cell(v) -> str:
    return f"{v:.4g}" if isinstance(v, float) else str(v)


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="RT-DETRv2 추론 하이퍼파라미터 그리드 탐색")
    p.add_argument("--input", required=True, help="이미지 폴드")
    p.add_argument("--sample-size", type=int, default=50, help="샘플링 이미지 수")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--output", default="rtdetr_outputs/tune_results.csv", help="CSV 저장 경로")
    p.add_argument("--conf", type=float, nargs="+",
                   default=[0.1, 0.15, 0.2, 0.25, 0.3, 0.4, 0.5])
    p.add_argument("--iou", type=float, nargs="+", default=[0.4, 0.5, 0.6, 0.7])
    p.add_argument("--imgsz", type=int, nargs="+", default=[640, 960, 1280])
    p.add_argument("--batch", type=int, default=4)
    p.add_argument("--engine", choices=["pt", "onnx"], default="pt")
    p.add_argument("--device", default="auto")
    p.add_argument("--checkpoint", default=None)
    p.add_argument("--src", default=None)
    p.add_argument("--no-ema", action="store_true")
    p.add_argument("--labels-dir", default=None, help="YOLO 라벨 폴드를 명시 지정")
    p.add_argument("--coco-json", default=None, help="COCO 어노테이션 json 명시 지정")
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

    all_images = shared.collect_images(input_dir)
    if not all_images:
        print(f"[오류] 이미지가 없습니다: {input_dir}")
        return 2
    rng = random.Random(args.seed)
    sampled = all_images[:]
    rng.shuffle(sampled)
    sampled = sampled[: args.sample_size]
    print(f"[준비] 전체 {len(all_images)}장 중 {len(sampled)}장 샘플링 (seed={args.seed})")

    # 라벨 모드 판정
    yolo_map = find_yolo_labels(sampled)
    coco_path = Path(args.coco_json) if args.coco_json else find_coco_json(input_dir)
    mode = "stability"
    gt_yolo: dict[Path, list] = {}
    class_ids: list[int] = []
    if yolo_map is not None:
        mode = "map"
        print(f"[라벨] YOLO 라벨 발견 ({len(yolo_map)}개 이미지) → mAP50-95 모드")
        for img in sampled:
            from PIL import Image
            with Image.open(img) as im:
                w, h = im.size
            gt_yolo[img] = parse_yolo_label(yolo_map[img], w, h)
        class_ids = sorted({c for g in gt_yolo.values() for c, _ in g})
    elif coco_path is not None:
        print("[라벨] COCO json 발견 → COCO mAP 모드는 pycocotools 연동이 필요해 YOLO 라벨 지정을 권장합니다. "
              "이번 실행은 stability 모드로 진행합니다.")
    else:
        print("[라벨] 라벨 미발견 → stability 모드 (검출 수 안정성·고신뢰 비율·속도)")

    engines: dict[int, object] = {}

    def get_engine(imgsz: int):
        if imgsz not in engines:
            if args.engine == "pt":
                engines[imgsz] = shared.PTEngine(checkpoint, imgsz, device, src_root,
                                                 half=False, use_ema=use_ema)
            else:
                out_dir = Path(args.output).parent
                onnx_path = out_dir / f"{checkpoint.stem}_{imgsz}.onnx"
                if not onnx_path.exists():
                    shared.export_onnx(checkpoint, imgsz, onnx_path, src_root=src_root, use_ema=use_ema)
                engines[imgsz] = shared.ONNXEngine(
                    onnx_path, num_classes=shared.count_classes(
                        shared.extract_state_dict(checkpoint, use_ema)))
        return engines[imgsz]

    combos = list(itertools.product(args.conf, args.iou, args.imgsz))
    print(f"[탐색] 조합 {len(combos)}개 (conf={args.conf} × iou={args.iou} × imgsz={args.imgsz})")

    rows: list[dict] = []
    try:
        from tqdm import tqdm
        combo_iter = tqdm(combos, desc="그리드 탐색", unit="combo")
    except ImportError:
        combo_iter = combos

    for conf, iou, imgsz in combo_iter:
        engine = get_engine(imgsz)
        row, det_for_map = run_combo(engine, sampled, conf, iou, imgsz, args.batch)
        row["mode"] = mode
        if mode == "map":
            gt_list = [gt_yolo[img] for img in sampled]
            map50_95, map50 = compute_map(det_for_map, gt_list, class_ids)
            row["map50_95"] = round(map50_95, 4)
            row["map50"] = round(map50, 4)
        rows.append(row)

    for e in engines.values():
        e.release()

    ranked = rank_with_map(rows) if mode == "map" else rank_no_label(rows)

    out_csv = Path(args.output)
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["rank", "conf", "iou", "imgsz", "engine", "mode", "n_images",
                  "mean_dets", "zero_det_frac", "max_dets", "mean_score", "high_conf_ratio",
                  "fwd_ms_mean", "p50_ms", "fps"]
    if mode == "map":
        fieldnames += ["map50_95", "map50"]
    else:
        fieldnames += ["stability_dev", "excluded"]
    with out_csv.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in ranked:
            writer.writerow({k: r.get(k, "") for k in fieldnames})
    print(f"[저장] CSV → {out_csv}")

    # 상위 5개 표 출력
    print("\n[상위 5개 조합]")
    header_keys = ["rank", "conf", "iou", "imgsz", "mean_dets", "high_conf_ratio", "fps"]
    if mode == "map":
        header_keys += ["map50_95", "map50"]
    else:
        header_keys += ["stability_dev"]
    widths = {}
    for k in header_keys:
        inner = max((len(_cell(r.get(k))) for r in ranked[:5]), default=4)
        widths[k] = max(len(k), inner)
    print("  " + "  ".join(k.ljust(widths[k]) for k in header_keys))
    for r in ranked[:5]:
        print("  " + "  ".join(_cell(r.get(k)).ljust(widths[k]) for k in header_keys))
    if mode == "stability":
        excluded = [r for r in rows if r.get("excluded")]
        if excluded:
            print(f"\n[참고] 안정성 기준 제외 조합 {len(excluded)}개 (검출 수가 중앙값 대비 급격히 편차)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
