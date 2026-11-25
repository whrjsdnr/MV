# UniAD (unified) 평가 보고서 — 평가 전용 복구

- 작성일: 2026-11-19
- 모델: UniAD (official pin `8a2b72aa`), unified 단일 모델 (30개 카테고리 공용)
- 소스 실험: `orchestrator/weekend_20261117T072915_33fbcd3c47` (uniad/unified)
- 학습 상태: 50 epoch 완료 (step 95,650), best `best_e39b65a1a42142019b5043f52cf74d93.pt` (sha256 `db498f57…c113e`)
  - ※ 주의: 학습-평가 통합 파이프라인이 45회 실패(평가 단계 npy 소실 반복)한 뒤 EVAL_PAUSED 상태였음. 이번 보고서는 동결 best 체크포인트로 평가만 복구한 것
- 산출물 원본: `real-iad-backup/eval_recovered/uniad_unified_report.md`, `uniad_unified_metrics.json` (서버 run: `/workspace/eval_scratch/uniad_unified/runs/run_20261119T151740_961d651…`)

## 1. 전체 성능 (30개 카테고리 통합)

| 지표 | Validation (4,400장) | Test (4,531장) |
|---|---|---|
| image AUROC | **0.7956** | **0.7914** |
| image AP | 0.6038 | 0.5880 |
| image F1 | 0.5902 | 0.5621 |
| pixel AUROC | 0.9819 | 0.9849 |
| AUPRO | 0.8851 | 0.8903 |

- Dinomaly unified (test img AUROC 0.9343) 대비 이미지 수준은 낮으나 pixel AUROC 0.985 / AUPRO 0.890으로 픽셀 분할 성능은 우수

## 2. 카테고리별 Test 성능 (image AUROC 순)

| 카테고리 | AUROC | AP | F1 | | 카테고리 | AUROC | AP | F1 |
|---|---|---|---|---|---|---|---|---|
| tape | 0.9872 | 0.9089 | 0.8333 | | vcpill | 0.8243 | 0.6541 | 0.5470 |
| zipper | 0.9592 | 0.9333 | 0.8099 | | usb_adaptor | 0.8184 | 0.6333 | 0.4828 |
| rolled_strip_base | 0.9577 | 0.9603 | 0.8831 | | plastic_nut | 0.7936 | 0.4408 | 0.5000 |
| audiojack | 0.9574 | 0.7988 | 0.7660 | | switch | 0.7581 | 0.4769 | 0.4333 |
| transistor1 | 0.9293 | 0.7848 | 0.6966 | | end_cap | 0.7527 | 0.7620 | 0.5455 |
| phone_battery | 0.9156 | 0.8490 | 0.6972 | | plastic_plug | 0.7379 | 0.1057 | 0.1071 |
| eraser | 0.9119 | 0.8213 | 0.6800 | | terminalblock | 0.7287 | 0.6514 | 0.5000 |
| bottle_cap | 0.8955 | 0.7046 | 0.4444 | | button_battery | 0.7284 | 0.6993 | 0.5385 |
| wooden_beads | 0.8903 | 0.6871 | 0.6471 | | porcelain_doll | 0.7091 | 0.2225 | 0.3800 |
| fire_hood | 0.8777 | 0.7271 | 0.5854 | | usb | 0.6979 | 0.4717 | 0.4950 |
| toothbrush | 0.8653 | 0.7304 | 0.5401 | | woodstick | 0.6766 | 0.2906 | 0.3864 |
| sim_card_set | 0.8612 | 0.7752 | 0.7538 | | pcb | 0.6281 | 0.5620 | 0.5324 |
| u_block | 0.8581 | 0.6357 | 0.4918 | | toy | 0.5769 | 0.5174 | 0.5139 |
| toy_brick | 0.8413 | 0.6651 | 0.6299 | | regulator | 0.5489 | 0.0830 | 0.1468 |
| mounts | 0.8290 | 0.6423 | 0.5588 | | mint | 0.5460 | 0.3744 | 0.3516 |

- 최고: tape 0.9872 / 최저: mint 0.5460, regulator 0.5489
- pixel 기반 지표(AUROC 0.98대)와 달리 이미지 판정 기준에서는 카테고리 편차가 큼

## 3. 평가 수행 정보

| 항목 | 값 |
|---|---|
| 평가 방식 | 동결 best 체크포인트 추론 (학습 미실행, 평가 전용 복구 run) |
| 데이터 | REAL, split v2-preserved, approved_crop |
| 입력 해상도 | 256 (학습 설정 동일) |
| 주의 | 평가 직후 서버 디스크 100% 사건 발생 — 평가 지표 기록 완료 후 report 생성이 중단되어 resume으로 완성. metric 신뢰도는 metrics.json 기준 |

## 4. 이력 메모

- 11/17~19: train+eval 통합 45회 시도 전부 평가 단계 실패 (prediction array 소실 — disk guard와 동일 정책)
- 11/19: 사용자 중단(EVAL_PAUSED) → recovery 실험 export로 체크포인트 4개 회수 완료(로컬 보유)
- 11/19: 동일 evaluator/protocol로 평가 복구 완료(이 보고서)
