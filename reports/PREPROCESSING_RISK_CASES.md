# 전처리 위험 사례 — 원본 이미지 제외

원본·파생 이미지 공유권한이 불확실하여 픽셀 사례를 포함하지 않았다. case_id는 상대경로의SHA256앞12자리이며 개인경로가아니다. 같은case_id가여러Crop에나올수있다. 아래는손실최악순의검토예시이며무작위대표표본이아니다.

| case_id | category | view | defect_type | crop | defect_pixels | kept_pixels | retention | crop_state |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| crop_b8d60feee97c | mint | C1 | ZW | 640 | 23 | 0 | 0 | removed |
| crop_a8d57085a6e4 | mint | C1 | YW | 640 | 32 | 0 | 0 | removed |
| crop_444b582af3a7 | mint | C2 | YW | 640 | 32 | 0 | 0 | removed |
| crop_427b1d46ee95 | end_cap | C3 | ZW | 640 | 33 | 0 | 0 | removed |
| crop_e0d44582f8ec | phone_battery | C1 | AK | 640 | 33 | 0 | 0 | removed |
| crop_e041495a5b94 | phone_battery | C5 | ZW | 640 | 33 | 0 | 0 | removed |
| crop_b9c5a11caea2 | mint | C2 | ZW | 640 | 35 | 0 | 0 | removed |
| crop_889688cd85f2 | mint | C1 | YW | 640 | 36 | 0 | 0 | removed |
| crop_010da67b5d95 | usb_adaptor | C2 | ZW | 640 | 40 | 0 | 0 | removed |
| crop_ec6f5867501d | usb_adaptor | C3 | ZW | 640 | 44 | 0 | 0 | removed |
| crop_a2f99424c499 | mint | C1 | QS | 640 | 45 | 0 | 0 | removed |
| crop_816b560be9fa | mint | C5 | YW | 640 | 45 | 0 | 0 | removed |
| crop_b8d60feee97c | mint | C1 | ZW | 768 | 23 | 0 | 0 | removed |
| crop_a8d57085a6e4 | mint | C1 | YW | 768 | 32 | 0 | 0 | removed |
| crop_e0d44582f8ec | phone_battery | C1 | AK | 768 | 33 | 0 | 0 | removed |
| crop_e041495a5b94 | phone_battery | C5 | ZW | 768 | 33 | 0 | 0 | removed |
| crop_cbb6ec35214d | mint | C1 | ZW | 768 | 48 | 0 | 0 | removed |
| crop_565ad927be5a | audiojack | C1 | ZW | 768 | 61 | 0 | 0 | removed |
| crop_3dd485bb6e50 | mint | C4 | ZW | 768 | 64 | 0 | 0 | removed |
| crop_957c44254382 | mint | C3 | ZW | 768 | 64 | 0 | 0 | removed |
| crop_794deac92616 | mint | C1 | YW | 768 | 65 | 0 | 0 | removed |
| crop_e547fba21c0a | mint | C1 | YW | 768 | 66 | 0 | 0 | removed |
| crop_7a07b1a16740 | mint | C2 | YW | 768 | 72 | 0 | 0 | removed |
| crop_e70c1dd059f8 | mint | C1 | YW | 768 | 72 | 0 | 0 | removed |
| crop_3505936f4c35 | mint | C1 | YW | 896 | 73 | 0 | 0 | removed |
| crop_322458d7f968 | phone_battery | C1 | ZW | 896 | 95 | 0 | 0 | removed |
| crop_e93cd7435500 | woodstick | C3 | AK | 896 | 114 | 0 | 0 | removed |
| crop_0c6ce7576563 | mint | C1 | YW | 896 | 179 | 0 | 0 | removed |
| crop_b56c73258a38 | mint | C1 | YW | 896 | 242 | 0 | 0 | removed |
| crop_5ac1214ab314 | plastic_nut | C5 | QS | 896 | 249 | 0 | 0 | removed |
| crop_3aa111ea76ae | zipper | C2 | PS | 896 | 270 | 0 | 0 | removed |
| crop_e77052f04362 | plastic_nut | C5 | QS | 896 | 289 | 0 | 0 | removed |
| crop_c95f061854d1 | plastic_nut | C3 | QS | 896 | 333 | 0 | 0 | removed |
| crop_05dcc916ebdd | plastic_nut | C5 | AK | 896 | 361 | 0 | 0 | removed |
| crop_4385827357a8 | plastic_nut | C5 | QS | 896 | 376 | 0 | 0 | removed |
| crop_629e173ec548 | tape | C3 | PS | 896 | 384 | 0 | 0 | removed |

완전제거된NG의상태를OK로변경하지않는다. 부분잘림에서는기존BBox와mask가같이변환되어야한다. 작은component의일부만남아도기존이미지타입을새정답으로확장하지않는다.

대표위험: (1)896Crop에서가장자리결함82이미지완전제거 (2)640은4600제거·9175부분잘림 (3)sim_card_set등6품목은제품밝기통과0 (4)그림자/반사/구멍을배경으로잘못치환할수있음 (5)PatchCore/Dinomaly/INP앞단Crop추가시이중Crop (6)ViTDet0..255와YOLO0..1의입력범위혼용 (7)GT미제공NG의빈negative변환 (8)검은NG전체mask의공간분포지배.

[anonymous_crop_risk_cases.csv](../outputs/preprocessing_review_20261112_v2/review_assets/statistics/anonymous_crop_risk_cases.csv)

[mask_crop_category.csv](../outputs/preprocessing_review_20261112_v2/review_assets/statistics/mask_crop_category.csv)

[mask_crop_by_size.csv](../outputs/preprocessing_review_20261112_v2/review_assets/statistics/mask_crop_by_size.csv)