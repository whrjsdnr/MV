# 성능 통합 보고서 — INP-Former

- 소스 실험: `remaining_models_recovery_20261117 (inp_former)`
- 완료 카테고리: 13개 (비REAL 데이터: 0개)
- 보고서 원본: `real-iad-backup/export/remaining_models_recovery_20261117 (inp_former)/<카테고리>/report.md`
- 지표 출처: 각 카테고리 보고서의 Validation(§7) / Test(§8) 섹션

## Validation 성능 (카테고리별)

| 카테고리 | image AUROC | image AP | image F1 | pixel AUROC | AUPRO |
|---|---|---|---|---|---|
| audiojack | 0.9494 | 0.9087 | - | 0.9940 | 0.9566 |
| bottle_cap | 0.9888 | 0.9775 | - | 0.9969 | 0.9897 |
| button_battery | 0.9893 | 0.9842 | - | 0.9884 | 0.9387 |
| end_cap | 0.8500 | 0.8065 | - | 0.9709 | 0.9316 |
| eraser | 0.9952 | 0.9868 | - | 0.9987 | 0.9930 |
| fire_hood | 0.9686 | 0.9173 | - | 0.9981 | 0.9779 |
| mint | 0.9317 | 0.8978 | - | 0.9836 | 0.8703 |
| mounts | 0.9731 | 0.9251 | - | 0.9979 | 0.9934 |
| pcb | 0.8427 | 0.7909 | - | 0.9856 | 0.9160 |
| phone_battery | 1.0000 | 1.0000 | - | 0.9989 | 0.9939 |
| plastic_nut | 0.9683 | 0.8133 | - | 0.9986 | 0.9900 |
| plastic_plug | 0.9458 | 0.6218 | - | 0.9723 | 0.9076 |
| toy_brick | 0.8390 | 0.7870 | - | 0.9842 | 0.9038 |

Validation 요약:

| 지표 | 평균 | 중앙값 | 최소 | 최대 |
|---|---|---|---|---|
| image_auroc | 0.9417 | 0.9683 | 0.8390 | 1.0000 |
| image_ap | 0.8782 | 0.9087 | 0.6218 | 1.0000 |
| image_f1 | - | - | - | - |
| pixel_auroc | 0.9899 | 0.9940 | 0.9709 | 0.9989 |
| aupro | 0.9510 | 0.9566 | 0.8703 | 0.9939 |

## Test 성능 (카테고리별)

| 카테고리 | image AUROC | image AP | image F1 | pixel AUROC | AUPRO |
|---|---|---|---|---|---|
| audiojack | 0.9711 | 0.9267 | - | 0.9987 | 0.9940 |
| bottle_cap | 0.9869 | 0.9451 | - | 0.9966 | 0.9896 |
| button_battery | 0.9493 | 0.9201 | - | 0.9768 | 0.8987 |
| end_cap | 0.8069 | 0.8136 | - | 0.9682 | 0.8894 |
| eraser | 0.9686 | 0.8933 | - | 0.9987 | 0.9930 |
| fire_hood | 0.9157 | 0.7852 | - | 0.9967 | 0.9564 |
| mint | 0.8377 | 0.7624 | - | 0.9645 | 0.8227 |
| mounts | 0.9342 | 0.8958 | - | 0.9979 | 0.9905 |
| pcb | 0.7615 | 0.7750 | - | 0.9783 | 0.8687 |
| phone_battery | 0.9998 | 0.9995 | - | 0.9985 | 0.9958 |
| plastic_nut | 0.9675 | 0.9106 | - | 0.9981 | 0.9917 |
| plastic_plug | 0.8607 | 0.3239 | - | 0.9960 | 0.9267 |
| toy_brick | 0.7924 | 0.6524 | - | 0.9890 | 0.9071 |

Test 요약:

| 지표 | 평균 | 중앙값 | 최소 | 최대 |
|---|---|---|---|---|
| image_auroc | 0.9040 | 0.9342 | 0.7615 | 0.9998 |
| image_ap | 0.8157 | 0.8933 | 0.3239 | 0.9995 |
| image_f1 | - | - | - | - |
| pixel_auroc | 0.9891 | 0.9966 | 0.9645 | 0.9987 |
| aupro | 0.9403 | 0.9564 | 0.8227 | 0.9958 |

## 카테고리별 Run 정보

| 카테고리 | run_id | data_kind |
|---|---|---|
| audiojack | `run_20261118T073833_893d980db6474cebac6084a986fe23a3` | REAL |
| bottle_cap | `run_20261118T090752_c53962e225b94798a44ee2d7e95be84e` | REAL |
| button_battery | `run_20261118T101635_9a7dec63580f435da455dc1f9c6d5424` | REAL |
| end_cap | `run_20261118T111131_8a0c2403214946c985ce2963d4957d7e` | REAL |
| eraser | `run_20261118T121333_3dce231c6f184959804b6e0fc9eed61c` | REAL |
| fire_hood | `run_20261118T132722_5c6fb457edd7453ebccd2cf38ed4469f` | REAL |
| mint | `run_20261118T143149_d063843f6b6d4003944af5f151c9d2ea` | REAL |
| mounts | `run_20261118T235655_43cea7e459ad4b53976012bc363a2f81` | REAL |
| pcb | `run_20261119T000615_4308c4284fda41a79ec230adf4777c42` | REAL |
| phone_battery | `run_20261119T010049_030a7873379b4085be988e69dc9fe58c` | REAL |
| plastic_nut | `run_20261119T053306_a0b93146bd534b199595eceda56ac46c` | REAL |
| plastic_plug | `run_20261119T055535_cac1cdb686e44beb88c392f052bb5baf` | REAL |
| toy_brick | `run_20261119T074748_c1bbaf1ddcda4cff9cdbdd91bcc50d7e` | REAL |
