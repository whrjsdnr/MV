# Crop 정책 검토 요약

최종판정: **INCONCLUSIVE** (제품전체GT미검수).

| method | images | positive_masks | retention | removed | partial | side_mean | linear_gain | full_frame_rate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| center640 | 300 | 103 | 0.76116 | 10 | 20 | 640 | 1.6 | 0 |
| center768 | 300 | 103 | 0.901261 | 3 | 11 | 768 | 1.33333 | 0 |
| center896 | 300 | 103 | 0.996481 | 0 | 3 | 896 | 1.14286 | 0 |
| full | 300 | 103 | 1 | 0 | 0 | 1024 | 1 | 1 |
| grabcut90_m10_fullfb | 300 | 103 | 0.998519 | 0 | 1 | 876.873 | 1.19275 | 0.103333 |

후속검증후보: grabcut90_m10_fullfb .같은300Holdout에서정책변경없이결함보존/확대proxy를검증했으나제품BBox600장사람승인과독립모델성능평가가필요하다. 신규Test는사용하지않았다. 원본Resize는안전기준선으로유지한다.
