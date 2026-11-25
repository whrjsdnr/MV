# HVQ-Trans (unified) 평가 보고서 — 업스트림 네이티브 프로토콜

- 작성일: 2026-11-19
- 모델: HVQ-Trans (EfficientNet-B4 frozen + HVQ_TR_switch transformer, upstream 공식 구현)
- 체크포인트: `ckpt.pth.tar` / `ckpt_best.pth.tar` = **epoch 41** (50 epoch 계획 중 사용자 중단 — ep49 반복 SIGSEGV로 인해 ep41 분을 export, state.json 기록)
- 평가 방식: upstream 네이티브 eval (`train_val.py -e`, config `experiments/MVTec-AD/config.yaml`) — **공통 평가기(common evaluator)와 프로토콜이 다륾**
- 데이터: `data/realiad/test.json` — 4,531장 (공통 프로토콜 test와 같은 split)
- 산출물: `real-iad-backup/eval_recovered/hvq_trans_eval_log.txt` (서버 eval_local.log 전체)

## 1. 전체 성능 (mean, 30개 카테고리)

| 지표 | 의미 | Mean |
|---|---|---|
| pixel AUC | 픽셀 단위 AUROC | **0.9697** |
| max AUC | 이미지 AUROC (max-pool 16×16) | **0.8269** |
| std AUC | 이미지 AUROC (mean/std 통계량) | **0.7331** |

- 공통 프로토콜의 image AUROC와 비교 가능한 지표는 **max AUC (0.8269)** 이다 (std AUC는 upstream 고유 통계로, 다른 모델 지표와 직접 비교 불가)
- Dinomaly unified (공통 프로토콜) test image AUROC 0.9343과 비교하면 낮음 — 단, ep41 미완성 체크포인트 + 프로토콜 차이(224² 입력·네이티브 스코어링) 감안 필요

## 2. 카테고리별 결과

| 카테고리 | pixel | max | std | | 카테고리 | pixel | max | std |
|---|---|---|---|---|---|---|---|---|
| tape | 0.9993 | 0.9980 | 0.9432 | | switch | 0.9511 | 0.7529 | 0.7436 |
| sim_card_set | 0.9953 | 0.9485 | 0.8805 | | end_cap | 0.9433 | 0.8180 | 0.7221 |
| u_block | 0.9962 | 0.9015 | 0.7454 | | mint | 0.9274 | 0.6648 | 0.6296 |
| mounts | 0.9968 | 0.9015 | 0.7331 | | toy | 0.9133 | 0.6244 | 0.5480 |
| vcpill | 0.9959 | 0.9178 | 0.8174 | | usb | 0.9693 | 0.6310 | 0.6525 |
| zipper | 0.9954 | 0.9560 | 0.8363 | | button_battery | 0.9593 | 0.7271 | 0.5504 |
| porcelain_doll | 0.9905 | 0.8807 | 0.7619 | | toy_brick | 0.9772 | 0.7858 | 0.6618 |
| audiojack | 0.9947 | 0.9468 | 0.9537 | | phone_battery | 0.9886 | 0.8862 | 0.6659 |
| rolled_strip_base | 0.9933 | 0.9823 | 0.9178 | | pcb | 0.9628 | 0.6624 | 0.6198 |
| wooden_beads | 0.9933 | 0.9143 | 0.6887 | | plastic_plug | 0.9602 | 0.6786 | 0.6414 |
| fire_hood | 0.9939 | 0.9325 | 0.8067 | | bottle_cap | 0.9897 | 0.9165 | 0.7132 |
| eraser | 0.9921 | 0.9169 | 0.8176 | | wooden_beads… | | | |
| terminalblock | 0.9876 | 0.8958 | 0.7778 | | transistor1 | 0.9896 | 0.9550 | 0.9017 |
| toothbrush | 0.9669 | 0.8077 | 0.7309 | | usb_adaptor | 0.9824 | 0.8542 | 0.7953 |
| plastic_nut | 0.9665 | 0.7428 | 0.7203 | | regulator | 0.8794 | 0.5778 | 0.5037 |
| woodstick | 0.8406 | 0.6308 | 0.5125 | | **mean** | **0.9697** | **0.8269** | **0.7331** |

- pixel AUC 최고: tape 0.9993 / 최저: woodstick 0.8406
- max AUC 최고: tape 0.9980 / 최저: regulator 0.5778

## 3. 주의 사항

1. **프로토콜 상이**: 이 표는 upstream 자체 evaluator 결과로, 공통 평가기의 validation-threshold·AUPRO·좌표계 정책과 다르다. dinomaly/uniad/inp_former 보고서와 직접 비교 금지.
2. **미완성 학습**: ep41/50 checkpoint 기반이라 최종 성능이 아니다. ep49 SIGSEGV 문제 해결 후 재학습하면 개선 여지 있음.
3. 공통 프로토콜 평가는 불가: hvq_trans는 `upstream_anomaly` 공통 Backend 미구현(snapshot 기준)으로 common evaluator 경로가 없다. 필요 시 Backend 어댑터 작성이 선행 과제.
4. 평가 실행 정보: 서버 A6000, `.venv-hvq`, 단일 프로세스 평가 약 17분 (4,531장, batch 32, 224² 입력).
