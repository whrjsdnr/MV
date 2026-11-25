# YOLO11 오프라인 Crop 의사결정 요약

판정: **INCONCLUSIVE**. 학습없는실제추론1350장(일반1200/위험150),오류0. 원본해상도PNG/좌표캐시생성완료. 제품전체GT가없어제품전체보존성공을선언하지않는다.

| method | available | available_positive_masks | conditional_pixel_weighted_retention | removed | partial |
| --- | --- | --- | --- | --- | --- |
| center640 | 1200 | 409 | 0.81671 | 39 | 89 |
| center768 | 1200 | 409 | 0.94173 | 8 | 34 |
| center896 | 1200 | 409 | 0.98588 | 0 | 14 |
| confidence_m0 | 770 | 255 | 0.96674 | 8 | 18 |
| confidence_m10 | 770 | 255 | 0.97404 | 6 | 10 |
| confidence_m20 | 770 | 255 | 0.9835 | 5 | 6 |
| confidence_m30 | 770 | 255 | 0.98577 | 5 | 3 |
| confidence_m30_fallback | 1200 | 409 | 0.99062 | 5 | 3 |
| full | 1200 | 409 | 1 | 0 | 0 |

우선결정: 검증제품BBox표본확보,COCO미검출/부분객체gate검증,품목별채택여부,남은결함과크롭손실의교환관계. YOLO비용은최초데이터구축에만계상한다. 모델adapter는nativeCrop후개별Resize/Normalize를한다. 최고confidence+30%는사전지정탐색캐시일뿐추천확정정책이아니다.

## 후속 결합 후보

| method | pixel_weighted_retention | removed | partial | full_frame_fraction |
| --- | --- | --- | --- | --- |
| hybrid896 | 0.988456 | 0 | 8 | 0.4625 |
| hybrid896_fullfallback | 1 | 0 | 0 | 0.820833 |

Center896와YOLO A30의합집합을남기는후속탐색이다. 전체Fallback결합은표본마스크100%를보존했으나82.08%는전체프레임이어서확대효과가제한된다. 같은결과를본뒤고안한규칙으로독립검증이필요하다.
