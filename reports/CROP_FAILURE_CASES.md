# Crop 실패·검수 대기 사례

제공mask손실은관측값이고자동BBox의실제제품완전성은미검수다.

| cohort | category | view | case_id | method | original_pixels | kept_pixels | retention | mask_state |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| dev_general | toothbrush | C1 | c4d6d7243733a893 | center896 | 10019 | 9388 | 0.93702 | partial |
| dev_general | toothbrush | C2 | 91a2064000fdb2d3 | center896 | 13462 | 13039 | 0.968578 | partial |
| dev_general | toothbrush | C4 | 91a2898592a67e06 | center896 | 9430 | 9244 | 0.980276 | partial |
| dev_general | toy_brick | C1 | 40fb19d400e7f3ab | center896 | 3488 | 2914 | 0.835436 | partial |
| dev_general | woodstick | C4 | ec7515e8b7474dda | center896 | 3230 | 2301 | 0.712384 | partial |
| dev_general | woodstick | C1 | 80c0a0256deb4f45 | center896 | 1994 | 1667 | 0.836008 | partial |
| dev_general | woodstick | C2 | 57c82cbf3bee7e0b | center896 | 804 | 556 | 0.691542 | partial |
| dev_general | woodstick | C2 | 3c3db3babfb50727 | center896 | 4962 | 4113 | 0.8289 | partial |
| dev_general | woodstick | C3 | db259b5133ccdbec | center896 | 3870 | 1330 | 0.343669 | partial |
| dev_general | zipper | C1 | 0c5d196b004a2ae1 | center896 | 34734 | 33380 | 0.961018 | partial |
| dev_general | zipper | C2 | dccda5d67adef8a9 | center896 | 20789 | 17893 | 0.860696 | partial |
| dev_general | zipper | C4 | 9448ffdda52c30eb | center896 | 6527 | 3089 | 0.473265 | partial |
| dev_general | zipper | C5 | 96f4e8d0852decbe | center896 | 35015 | 29374 | 0.838898 | partial |
| dev_general | zipper | C4 | 6e780e9532a75b54 | center896 | 18243 | 15851 | 0.868881 | partial |
| dev_risk | woodstick | C3 | e93cd74355008f41 | center896 | 114 | 0 | 0 | removed |
| dev_risk | zipper | C2 | 1d6e5fc528121e82 | center896 | 6484 | 5281 | 0.814466 | partial |
| dev_risk | zipper | C4 | 4f51f3fdec7cd137 | center896 | 999 | 158 | 0.158158 | partial |
| independent_validation_products | woodstick | C1 | 7590b6d672b9f355 | center896 | 4558 | 3991 | 0.875603 | partial |
| independent_validation_products | woodstick | C2 | f3e00aebab30df2a | center896 | 1985 | 1747 | 0.880101 | partial |
| independent_validation_products | zipper | C4 | 1c2968db72038284 | center896 | 7558 | 7522 | 0.995237 | partial |
| independent_validation_products | zipper | C4 | 1c2968db72038284 | grabcut90_m10_fullfb | 7558 | 7204 | 0.953162 | partial |

[전수표본실패목록](../outputs/object_aware_crop_v1/metrics/frozen_and_center_failure_cases.csv). 그림자·유사색·얇은부품·테두리초기화가실패원인후보이며인과로확정하지않았다. 사람승인전제품GT지표는UNVERIFIED다.
