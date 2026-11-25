# 성능 통합 보고서 — EfficientAD-S

- 소스 실험: `efficientad_s_recovery_20261117`
- 전체 30개 카테고리 중 COMPLETED 20개 + 미완료(평가복구) 10개
- 보고서 원본: `real-iad-backup/export/efficientad_s_recovery_20261117/<카테고리>/report.md`, 미완료 분은 서버 recovery receipt 기준
- ⚠ 표시 = 캘리브레이션 실패로 학습 중단, 미숙련 체크포인트 기반 복구 평가이므로 재학습 필요

## 1. Validation 성능 (카테고리별)

| 카테고리 | image AUROC | image AP | image F1 | pixel AUROC | AUPRO | 비고 |
|---|---|---|---|---|---|---|
| bottle_cap | 0.8121 | 0.6937 | - | 0.9100 | 0.7672 | |
| eraser | 0.9844 | 0.9768 | - | 0.9936 | 0.9785 | |
| mint | 0.9032 | 0.8680 | - | 0.9808 | 0.8139 | |
| mounts | 0.9756 | 0.9392 | - | 0.9808 | 0.9715 | |
| pcb | 0.5725 | 0.5061 | - | 0.1773 | 0.0000 | |
| phone_battery | 0.9900 | 0.9618 | - | 0.9979 | 0.9922 | |
| plastic_nut | 0.9371 | 0.7885 | - | 0.9593 | 0.8080 | |
| plastic_plug | 0.7845 | 0.3080 | - | 0.9914 | 0.9729 | |
| regulator | 0.8523 | 0.4980 | - | 0.9603 | 0.7462 | |
| rolled_strip_base | 0.9897 | 0.9869 | - | 0.9890 | 0.9782 | |
| sim_card_set | 0.9988 | 0.9984 | - | 0.9905 | 0.9336 | |
| tape | 0.9856 | 0.9490 | - | 0.9976 | 0.8998 | |
| terminalblock | 0.9730 | 0.9754 | - | 0.9786 | 0.9101 | |
| toothbrush | 0.9385 | 0.8311 | - | 0.8548 | 0.7358 | |
| toy | 0.7176 | 0.5653 | - | 0.8257 | 0.5710 | |
| toy_brick | 0.7796 | 0.7239 | - | 0.9314 | 0.7518 | |
| u_block | 1.0000 | 1.0000 | - | 0.9909 | 0.9720 | |
| usb_adaptor | 0.8995 | 0.7521 | - | 0.9560 | 0.8190 | |
| woodstick | 0.7725 | 0.5304 | - | 0.7916 | 0.4724 | |
| zipper | 0.9958 | 0.9913 | - | 0.9693 | 0.8454 | |
| audiojack | 0.9593 | - | - | - | - | 정상 학습 기반 (평가복구) |
| button_battery | 0.6936 | - | - | - | - | ⚠ 재학습 필요 (복구평가) |
| end_cap | 0.6761 | - | - | - | - | ⚠ 재학습 필요 (복구평가) |
| fire_hood | 0.9297 | - | - | - | - | ⚠ 재학습 필요 (미숙련 체크포인트) (복구평가) |
| porcelain_doll | 0.9735 | - | - | - | - | ⚠ 재학습 필요 (미숙련 체크포인트) (복구평가) |
| switch | 0.6509 | - | - | - | - | ⚠ 재학습 필요 (복구평가) |
| transistor1 | 0.8513 | - | - | - | - | ⚠ 재학습 필요 (미숙련 체크포인트) (복구평가) |
| usb | 0.7709 | - | - | - | - | ⚠ 재학습 필요 (복구평가) |
| vcpill | 0.7958 | - | - | - | - | ⚠ 재학습 필요 (미숙련 체크포인트) (복구평가) |
| wooden_beads | 0.7892 | - | - | - | - | ⚠ 재학습 필요 (미숙련 체크포인트) (복구평가) |

Validation 요약 (COMPLETED 20개 기준):

| 지표 | 평균 | 중앙값 | 최소 | 최대 |
|---|---|---|---|---|
| image_auroc | 0.8931 | 0.9378 | 0.5725 | 1.0000 |
| image_ap | 0.7922 | 0.8496 | 0.3080 | 1.0000 |
| image_f1 | - | - | - | - |
| pixel_auroc | 0.9113 | 0.9739 | 0.1773 | 0.9979 |
| aupro | 0.7970 | 0.8322 | 0.0000 | 0.9922 |

Test 요약 (COMPLETED 20개 기준):

| 지표 | 평균 | 중앙값 | 최소 | 최대 |
|---|---|---|---|---|
| image_auroc | 0.8905 | 0.9330 | 0.4937 | 1.0000 |
| image_ap | 0.7932 | 0.8019 | 0.4414 | 1.0000 |
| image_f1 | - | - | - | - |
| pixel_auroc | 0.9110 | 0.9675 | 0.2100 | 0.9996 |
| aupro | 0.7721 | 0.8599 | 0.0116 | 0.9990 |

## 2. Test 성능 (카테고리별)

| 카테고리 | image AUROC | image AP | image F1 | pixel AUROC | AUPRO | 비고 |
|---|---|---|---|---|---|---|
| bottle_cap | 0.8871 | 0.7175 | - | 0.9621 | 0.8769 | |
| eraser | 0.9871 | 0.9722 | - | 0.9968 | 0.9813 | |
| mint | 0.7920 | 0.6386 | - | 0.9254 | 0.7340 | |
| mounts | 0.9783 | 0.9438 | - | 0.9837 | 0.9452 | |
| pcb | 0.4937 | 0.4414 | - | 0.2100 | 0.0116 | |
| phone_battery | 0.9898 | 0.9750 | - | 0.9870 | 0.9665 | |
| plastic_nut | 0.8581 | 0.6592 | - | 0.8966 | 0.6504 | |
| plastic_plug | 0.9379 | 0.5326 | - | 0.9680 | 0.5299 | |
| regulator | 0.8444 | 0.6138 | - | 0.9149 | 0.5125 | |
| rolled_strip_base | 0.9858 | 0.9880 | - | 0.9894 | 0.8729 | |
| sim_card_set | 1.0000 | 1.0000 | - | 0.9951 | 0.9709 | |
| tape | 0.9996 | 0.9976 | - | 0.9996 | 0.9990 | |
| terminalblock | 0.9280 | 0.9016 | - | 0.9670 | 0.8468 | |
| toothbrush | 0.9220 | 0.7992 | - | 0.8783 | 0.7590 | |
| toy | 0.7978 | 0.7648 | - | 0.8987 | 0.6642 | |
| toy_brick | 0.8061 | 0.6943 | - | 0.9596 | 0.7678 | |
| u_block | 0.9988 | 0.9935 | - | 0.9938 | 0.9719 | |
| usb_adaptor | 0.9406 | 0.8046 | - | 0.9953 | 0.9725 | |
| woodstick | 0.6812 | 0.4548 | - | 0.7230 | 0.5070 | |
| zipper | 0.9810 | 0.9708 | - | 0.9761 | 0.9018 | |
| audiojack | 0.9889 | - | - | - | - | 정상 학습 기반 (평가복구) |
| button_battery | 0.6391 | - | - | - | - | ⚠ 재학습 필요 (복구평가) |
| end_cap | 0.7493 | - | - | - | - | ⚠ 재학습 필요 (복구평가) |
| fire_hood | 0.8281 | - | - | - | - | ⚠ 재학습 필요 (미숙련 체크포인트) (복구평가) |
| porcelain_doll | 0.8584 | - | - | - | - | ⚠ 재학습 필요 (미숙련 체크포인트) (복구평가) |
| switch | 0.6393 | - | - | - | - | ⚠ 재학습 필요 (복구평가) |
| transistor1 | 0.8807 | - | - | - | - | ⚠ 재학습 필요 (미숙련 체크포인트) (복구평가) |
| usb | 0.7263 | - | - | - | - | ⚠ 재학습 필요 (복구평가) |
| vcpill | 0.9085 | - | - | - | - | ⚠ 재학습 필요 (미숙련 체크포인트) (복구평가) |
| wooden_beads | 0.8953 | - | - | - | - | ⚠ 재학습 필요 (미숙련 체크포인트) (복구평가) |

## 3. 미완료 10개 카테고리 상세

| 카테고리 | 체크포인트 (offload) | 실패 원인 | 실패 지점 | 재학습 |
|---|---|---|---|---|
| audiojack | 0 (원본은 orchestrator/weekend 경로에 best 2 + state 2) | 원학습은 구 실험에서 정상 수행. recovery에서는 예측배열 버그로 평가만 복구 | - | 불필요 (정상 학습 기반) |
| button_battery | best 1 + state 2 | CalibrationError: Degenerate validation map quantiles: st | epoch 1, batch 385 | 재학습 필요 |
| end_cap | best 2 + state 2 | CalibrationError: Degenerate validation map quantiles: st | epoch 2, batch 400 | 재학습 필요 |
| fire_hood | best 2 + state 2 | CalibrationError: Degenerate validation map quantiles: st | epoch 18, batch 540 | 재학습 필요 (미숙련 체크포인트) |
| porcelain_doll | best 1 + state 2 | CalibrationError: Degenerate validation map quantiles: st | epoch 1, batch 590 | 재학습 필요 (미숙련 체크포인트) |
| switch | best 2 + state 2 | CalibrationError: Degenerate validation map quantiles: st | epoch 2, batch 605 | 재학습 필요 |
| transistor1 | best 2 + state 2 | CalibrationError: Degenerate validation map quantiles: st | epoch 2, batch 480 | 재학습 필요 (미숙련 체크포인트) |
| usb | best 2 + state 2 | CalibrationError: Degenerate validation map quantiles: st | epoch 2, batch 460 | 재학습 필요 |
| vcpill | best 2 + state 2 | CalibrationError: Degenerate validation map quantiles: st | epoch 6, batch 510 | 재학습 필요 (미숙련 체크포인트) |
| wooden_beads | best 1 + state 2 | CalibrationError: Degenerate validation map quantiles: st | epoch 1, batch 590 | 재학습 필요 (미숙련 체크포인트) |

## 4. 실패 분석 및 권고

- 9개 카테고리는 모두 `CalibrationError: Degenerate validation map quantiles: st`로 학습이 중단됨 (`calibrate_maps()`에서 student-teacher map의 validation quantile이 퇴화). 실패 시점이 epoch 1~18로 초반이라 저장된 체크포인트는 미숙련 상태.
- 복구 평가 점수가 낮은 switch(0.651/0.639), button_battery(0.694/0.639), end_cap(0.676/0.749)는 당연히 재학습 필요. AUROC이 높게 나온 나머지 6개도 미숙련 체크포인트 기반이라 정식 완료 기준과는 다른 의미.
- audiojack은 원학습이 정상(orchestrator/weekend)이라 복구 평가 0.9593/0.9889를 그대로 활용 가능. 원본 체크포인트는 `offload/.../orchestrator/weekend_20261117T072915_33fbcd3c47/efficientad_s/audiojack/`.
- 현재 서버 실행 워커(retinanet, faster_rcnn, yolo11, inp_former, hvq)와 DETECT_V2 큐에는 EfficientAD-S가 없음 — 9개 재학습은 캘리브레이션 수정 후 별도 트리거 필요.
- pull 갭: 체크포인트 위주 pull이라 failure_diagnostics, recovery receipt, 실패 run의 report.md는 서버에만 존재.

## 5. 카테고리별 Run 정보

| 카테고리 | run_id | data_kind |
|---|---|---|
| bottle_cap | `run_20261117T090924_9be051c2ffaa45dfbfbf9419a98c0d97` | REAL |
| eraser | `run_20261117T114302_a73f9cd92dad4e65bb7b313f6d626ec5` | REAL |
| mint | `run_20261117T114303_74a64fb343864f10824328e8a0926865` | REAL |
| mounts | `run_20261117T114303_640c31333e4f436b929c0353f2de7edf` | REAL |
| pcb | `run_20261118T055231_b7de08aaa6d14fdf808f8da7a0c38c54` | REAL |
| phone_battery | `run_20261117T122520_122c5d4c53bf483e8494ea6928c68bb6` | REAL |
| plastic_nut | `run_20261117T140746_2bef13e6b8a74a16a1624a12c26f1c00` | REAL |
| plastic_plug | `run_20261117T144748_c0e8de9057e249df8c613d1fb8e1caf4` | REAL |
| regulator | `run_20261118T000854_86e6a8ce46494a6da4a8727d6e8d9880` | REAL |
| rolled_strip_base | `run_20261118T000854_41e5f4e61988463dbb2f20614c8d3d8b` | REAL |
| sim_card_set | `run_20261118T000854_ae057959937346c481b579ad7c90150c` | REAL |
| tape | `run_20261118T003227_4ce836483ba34e4ebdbf264e9e73841d` | REAL |
| terminalblock | `run_20261118T010056_f76de4ea67b4466e88639fe768ac10d4` | REAL |
| toothbrush | `run_20261118T012232_a750ddd202e84826b0e43e4af0d2fec1` | REAL |
| toy | `run_20261118T021720_3f5c25b831cc4c2898ee500c400aad2d` | REAL |
| toy_brick | `run_20261118T022130_0ee77c4fdca74532a504f7297bc9c459` | REAL |
| u_block | `run_20261118T024505_bec0f4728f754b569017c27613b836a4` | REAL |
| usb_adaptor | `run_20261118T033436_2a5793b4bffe48708154ef958c655667` | REAL |
| woodstick | `run_20261118T053603_e10c45e9b92345108f784c4992e53de5` | REAL |
| zipper | `run_20261118T053603_f99631ad963745458823ec5a9ae2595c` | REAL |
| audiojack | (미완료 — 실패 run + 평가복구 run) | - |
| button_battery | (미완료 — 실패 run + 평가복구 run) | - |
| end_cap | (미완료 — 실패 run + 평가복구 run) | - |
| fire_hood | (미완료 — 실패 run + 평가복구 run) | - |
| porcelain_doll | (미완료 — 실패 run + 평가복구 run) | - |
| switch | (미완료 — 실패 run + 평가복구 run) | - |
| transistor1 | (미완료 — 실패 run + 평가복구 run) | - |
| usb | (미완료 — 실패 run + 평가복구 run) | - |
| vcpill | (미완료 — 실패 run + 평가복구 run) | - |
| wooden_beads | (미완료 — 실패 run + 평가복구 run) | - |
