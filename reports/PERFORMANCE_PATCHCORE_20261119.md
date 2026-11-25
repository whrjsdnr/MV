# 성능 통합 보고서 — PatchCore

- 소스 실험: `patchcore_array_hotfix_20261117`
- 완료 카테고리: 30개 (비REAL 데이터: 0개)
- 보고서 원본: `real-iad-backup/export/patchcore_array_hotfix_20261117/<카테고리>/report.md`
- 지표 출처: 각 카테고리 보고서의 Validation(§7) / Test(§8) 섹션

## Validation 성능 (카테고리별)

| 카테고리 | image AUROC | image AP | image F1 | pixel AUROC | AUPRO |
|---|---|---|---|---|---|
| audiojack | 0.9320 | 0.8927 | - | 0.9946 | 0.9623 |
| bottle_cap | 0.9938 | 0.9869 | - | 0.9983 | 0.9942 |
| button_battery | 0.9863 | 0.9830 | - | 0.9910 | 0.9516 |
| end_cap | 0.8369 | 0.8165 | - | 0.9732 | 0.9271 |
| eraser | 0.9829 | 0.9667 | - | 0.9982 | 0.9906 |
| fire_hood | 0.9314 | 0.8978 | - | 0.9972 | 0.9714 |
| mint | 0.9146 | 0.8694 | - | 0.9864 | 0.8662 |
| mounts | 0.9858 | 0.9556 | - | 0.9983 | 0.9956 |
| pcb | 0.8812 | 0.8216 | - | 0.9956 | 0.9658 |
| phone_battery | 0.9932 | 0.9850 | - | 0.9984 | 0.9920 |
| plastic_nut | 0.9054 | 0.7410 | - | 0.9953 | 0.9770 |
| plastic_plug | 0.7974 | 0.1322 | - | 0.9797 | 0.9395 |
| porcelain_doll | 0.9765 | 0.8928 | - | 0.9988 | 0.9907 |
| regulator | 0.9777 | 0.8520 | - | 0.9992 | 0.9964 |
| rolled_strip_base | 1.0000 | 1.0000 | - | 0.9980 | 0.9945 |
| sim_card_set | 0.9974 | 0.9964 | - | 0.9958 | 0.9511 |
| switch | 0.9735 | 0.9264 | - | 0.9989 | 0.9911 |
| tape | 0.9900 | 0.9623 | - | 0.9992 | 0.9731 |
| terminalblock | 0.9891 | 0.9882 | - | 0.9979 | 0.9898 |
| toothbrush | 0.9647 | 0.9199 | - | 0.9865 | 0.9470 |
| toy | 0.8233 | 0.7645 | - | 0.9788 | 0.9232 |
| toy_brick | 0.7624 | 0.6990 | - | 0.9784 | 0.8662 |
| transistor1 | 0.9943 | 0.9795 | - | 0.9978 | 0.9889 |
| u_block | 0.9910 | 0.8961 | - | 0.9997 | 0.9990 |
| usb | 0.9705 | 0.9438 | - | 0.9943 | 0.9593 |
| usb_adaptor | 0.8385 | 0.6862 | - | 0.9929 | 0.9244 |
| vcpill | 0.9308 | 0.7747 | - | 0.9842 | 0.9167 |
| wooden_beads | 0.9064 | 0.8037 | - | 0.9939 | 0.9351 |
| woodstick | 0.5290 | 0.2214 | - | 0.9357 | 0.5191 |
| zipper | 0.9972 | 0.9949 | - | 0.9955 | 0.9658 |

Validation 요약:

| 지표 | 평균 | 중앙값 | 최소 | 최대 |
|---|---|---|---|---|
| image_auroc | 0.9251 | 0.9720 | 0.5290 | 1.0000 |
| image_ap | 0.8450 | 0.8970 | 0.1322 | 1.0000 |
| image_f1 | - | - | - | - |
| pixel_auroc | 0.9911 | 0.9955 | 0.9357 | 0.9997 |
| aupro | 0.9455 | 0.9658 | 0.5191 | 0.9990 |

## Test 성능 (카테고리별)

| 카테고리 | image AUROC | image AP | image F1 | pixel AUROC | AUPRO |
|---|---|---|---|---|---|
| audiojack | 0.9884 | 0.9631 | - | 0.9991 | 0.9950 |
| bottle_cap | 0.9943 | 0.9785 | - | 0.9989 | 0.9958 |
| button_battery | 0.9478 | 0.9140 | - | 0.9887 | 0.8997 |
| end_cap | 0.8144 | 0.8485 | - | 0.9643 | 0.8681 |
| eraser | 0.9531 | 0.8963 | - | 0.9978 | 0.9877 |
| fire_hood | 0.9464 | 0.8484 | - | 0.9960 | 0.9532 |
| mint | 0.7920 | 0.6709 | - | 0.9771 | 0.8377 |
| mounts | 0.9731 | 0.9354 | - | 0.9988 | 0.9918 |
| pcb | 0.9380 | 0.9424 | - | 0.9961 | 0.9462 |
| phone_battery | 0.9896 | 0.9740 | - | 0.9974 | 0.9739 |
| plastic_nut | 0.9639 | 0.8779 | - | 0.9984 | 0.9928 |
| plastic_plug | 0.8634 | 0.4144 | - | 0.9918 | 0.9107 |
| porcelain_doll | 0.9178 | 0.6520 | - | 0.9983 | 0.9899 |
| regulator | 0.9407 | 0.6583 | - | 0.9991 | 0.9926 |
| rolled_strip_base | 0.9887 | 0.9892 | - | 0.9975 | 0.9882 |
| sim_card_set | 0.9735 | 0.9463 | - | 0.9980 | 0.9850 |
| switch | 0.9607 | 0.8624 | - | 0.9954 | 0.9754 |
| tape | 1.0000 | 1.0000 | - | 0.9996 | 0.9987 |
| terminalblock | 0.9882 | 0.9747 | - | 0.9986 | 0.9939 |
| toothbrush | 0.9526 | 0.8851 | - | 0.9905 | 0.9526 |
| toy | 0.9116 | 0.8766 | - | 0.9773 | 0.9028 |
| toy_brick | 0.8155 | 0.7320 | - | 0.9883 | 0.9001 |
| transistor1 | 0.9857 | 0.9398 | - | 0.9987 | 0.9923 |
| u_block | 0.9900 | 0.9416 | - | 0.9995 | 0.9972 |
| usb | 0.9412 | 0.8558 | - | 0.9956 | 0.9668 |
| usb_adaptor | 0.9699 | 0.9137 | - | 0.9973 | 0.9814 |
| vcpill | 0.9669 | 0.9392 | - | 0.9958 | 0.9736 |
| wooden_beads | 0.9849 | 0.9724 | - | 0.9918 | 0.9184 |
| woodstick | 0.5989 | 0.2049 | - | 0.9235 | 0.7078 |
| zipper | 0.9821 | 0.9690 | - | 0.9981 | 0.9860 |

Test 요약:

| 지표 | 평균 | 중앙값 | 최소 | 최대 |
|---|---|---|---|---|
| image_auroc | 0.9344 | 0.9623 | 0.5989 | 1.0000 |
| image_ap | 0.8526 | 0.9139 | 0.2049 | 1.0000 |
| image_f1 | - | - | - | - |
| pixel_auroc | 0.9916 | 0.9974 | 0.9235 | 0.9996 |
| aupro | 0.9518 | 0.9784 | 0.7078 | 0.9987 |

## 카테고리별 Run 정보

| 카테고리 | run_id | data_kind |
|---|---|---|
| audiojack | `run_20261117T080001_398294fc44e24307838fd4b064cd9528` | REAL |
| bottle_cap | `run_20261117T081016_3886217e12aa460e9f74dd388e310484` | REAL |
| button_battery | `run_20261117T081834_29d94ca61760495bb2739eb3f69dac3c` | REAL |
| end_cap | `run_20261117T082525_36419862cd3643e29557067c1655d08f` | REAL |
| eraser | `run_20261117T083218_58e7f98d702c4d548dae38bb84abff7d` | REAL |
| fire_hood | `run_20261117T084101_02b73281f4634c0aba7cba50f0cd000b` | REAL |
| mint | `run_20261117T084956_da28feb124b8499aa5052acaf2c363bf` | REAL |
| mounts | `run_20261117T085858_cf5d5208ae704c6fb7ca7859699bb502` | REAL |
| pcb | `run_20261117T090814_0bf31fad74c74811acb49e050a8f5f9f` | REAL |
| phone_battery | `run_20261117T091458_528115ef983143ab8f39a91df4d50e94` | REAL |
| plastic_nut | `run_20261117T092439_70c0657e79c44f468fd29cade4f325e5` | REAL |
| plastic_plug | `run_20261117T093528_1b9faefb90184e93b74c0558af5c1bd3` | REAL |
| porcelain_doll | `run_20261117T094701_1af6e2dc2c114246a85710c4c0266bc6` | REAL |
| regulator | `run_20261117T095748_ffc1e72de3f0446dbd1d9603e8365bb9` | REAL |
| rolled_strip_base | `run_20261117T100944_47b2c0ea32f04b8883decc5877e7551b` | REAL |
| sim_card_set | `run_20261117T101610_c9f7a04c1e0c4c828dc578a2a56ce7e9` | REAL |
| switch | `run_20261117T102403_c806092f56e14db9b05497ee2680d3b2` | REAL |
| tape | `run_20261117T114102_2b5b208bf3804ab18ec4e7c130c0c26e` | REAL |
| terminalblock | `run_20261117T114856_1cdfdbbb417f45dcb255883dcbf690b5` | REAL |
| toothbrush | `run_20261117T115807_eefec5bd37aa4fefaed69300793753cd` | REAL |
| toy | `run_20261117T120647_3798315f36aa417299ed14bc6a3e9e29` | REAL |
| toy_brick | `run_20261117T121645_10b7448dde18422392da53eec4169ac2` | REAL |
| transistor1 | `run_20261117T122735_5f9263d3cf4a474b9dc74a3083639706` | REAL |
| u_block | `run_20261118T005154_395fbe4ea842482ea80e4efe4d1393ad` | REAL |
| usb | `run_20261118T010723_4d83ef46c79642e68a1e7f6af76bcdc4` | REAL |
| usb_adaptor | `run_20261118T012157_98d6e7e6f3284cd98721c39c3ce997a4` | REAL |
| vcpill | `run_20261118T013341_38bdffe619f347b5abd22b228527eee6` | REAL |
| wooden_beads | `run_20261118T014513_871c7512799541888260a0e4ea06a559` | REAL |
| woodstick | `run_20261118T015818_5f19dfdd432644bca511ec111d9f9cd6` | REAL |
| zipper | `run_20261118T021116_e2c1d8fecacb4a79a61e58b14e03cdd8` | REAL |
