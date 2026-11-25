# Dinomaly (unified) 평가 보고서 — 평가 전용 복구

- 작성일: 2026-11-19
- 모델: Dinomaly (DINOv2 ViT-B/14 + official pin `1f252be0`), unified 단일 모델 (30개 카테고리 공용)
- 소스 실험: `remaining_models_recovery_20261117` (job/dinomaly/unified)
- 학습 상태: COMPLETED (50 epochs, 47,850 steps, best `best_889515576adb42ac82ea5e355f4e798f.pt`, sha256 `53d81a82…5e95ca`)
- 평가 경위: 학습 COMPLETED 후 report/metrics가 서버에서 소실 → 동결 best 체크포인트로 추론·평가만 수행 (학습 미실행)
- 산출물 원본: `real-iad-backup/eval_recovered/dinomaly_unified_report.md`, `dinomaly_unified_metrics.json` (서버 run: `/workspace/eval_scratch/dinomaly_unified/runs/run_20261119T130225_53e2d77d…`)

## 1. 전체 성능 (30개 카테고리 통합)

| 지표 | Validation (4,400장) | Test (4,531장) |
|---|---|---|
| image AUROC | **0.9362** | **0.9343** |
| image AP | 0.8682 | 0.8530 |
| image F1 | 0.7862 | 0.7769 |
| pixel AUROC | 0.9940 | 0.9947 |
| AUPRO | 0.9431 | 0.9427 |

- Threshold 정책: validation-only 보정 (image 0.1204 / pixel 0.1655, pixel score range [0.0047, 0.4454]) → 동일 정책으로 test 평가
- 비교: EfficientAD-S COMPLETED 20개 val AUROC 평균 0.8931 / PatchCore 0.8954 대비 unified 단일 모델치고 우수

## 2. 카테고리별 Test 성능 (image AUROC 순)

| 카테고리 | AUROC | AP | F1 | | 카테고리 | AUROC | AP | F1 |
|---|---|---|---|---|---|---|---|---|
| tape | 1.0000 | 1.0000 | 0.9744 | | usb | 0.9372 | 0.8872 | 0.7500 |
| zipper | 0.9990 | 0.9982 | 0.8889 | | fire_hood | 0.9281 | 0.8231 | 0.6984 |
| rolled_strip_base | 0.9990 | 0.9990 | 0.9583 | | plastic_plug | 0.9172 | 0.5849 | 0.5000 |
| phone_battery | 0.9957 | 0.9897 | 0.9184 | | toy | 0.9164 | 0.8916 | 0.8175 |
| terminalblock | 0.9900 | 0.9807 | 0.8989 | | usb_adaptor | 0.9101 | 0.7626 | 0.6875 |
| audiojack | 0.9895 | 0.9584 | 0.6154 | | toothbrush | 0.9072 | 0.8072 | 0.6372 |
| transistor1 | 0.9890 | 0.9668 | 0.8395 | | eraser | 0.8983 | 0.7935 | 0.6364 |
| mounts | 0.9854 | 0.9644 | 0.8919 | | end_cap | 0.8320 | 0.8388 | 0.6842 |
| wooden_beads | 0.9824 | 0.9596 | 0.8923 | | woodstick | 0.8251 | 0.4278 | 0.5169 |
| bottle_cap | 0.9812 | 0.9280 | 0.8000 | | mint | 0.8061 | 0.7104 | 0.5000 |
| plastic_nut | 0.9786 | 0.8563 | 0.8571 | | toy_brick | 0.7822 | 0.6056 | 0.6080 |
| u_block | 0.9769 | 0.8543 | 0.7429 | | regulator | 0.7785 | 0.5910 | 0.5000 |
| vcpill | 0.9726 | 0.9478 | 0.8462 | | | | | |
| button_battery | 0.9620 | 0.9514 | 0.8174 | | | | | |
| switch | 0.9562 | 0.8807 | 0.8767 | | | | | |
| sim_card_set | 0.9528 | 0.8381 | 0.9322 | | | | | |
| pcb | 0.9429 | 0.9494 | 0.8182 | | | | | |
| porcelain_doll | 0.9416 | 0.7579 | 0.4242 | | | | | |

- 최고: tape 1.0000 / 최저: regulator 0.7785
- 상위 15개 카테고리 모두 0.94 이상
- 상대적 약점: regulator(0.779), toy_brick(0.782), mint(0.806), woodstick(0.825), end_cap(0.832)

## 3. 평가 수행 정보

| 항목 | 값 |
|---|---|
| 평가 방식 | 동결 best 체크포인트 추론 (학습 미실행, `evaluation_only_recovery`) |
| 데이터 | REAL, split v2-preserved, approved_crop 정책 |
| 입력 해상도 | 256 (학습 설정 동일) |
| 장비 | NVIDIA RTX A6000, torch 2.6.0+cu126 |
| 재현성 | validation cohort sha `64b628aa…`, protocol sha `582a7377…` (metrics.json 기록) |

## 4. 주의 및 후속

- 이 지표는 "학습 완료 후 정상 평가 절차가 소실되어 복구한 것"이며, 표준 train→eval 파이프라인과 동일한 evaluator·protocol·threshold 정책 사용
- 평가 run의 dense map(score map)은 disk 정책에 따라 회수됨(metrics/보고서/예시 이미지는 영구 보존)
- uniAD 평가는 동일 방식으로 진행 중이며, 이 보고서와 같은 형식으로 추가 예정
