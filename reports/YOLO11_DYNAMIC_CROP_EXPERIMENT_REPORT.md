# YOLO11 오프라인 동적 Crop 전처리 실험

## 1. 연구 배경과 목적

YOLO11n COCO 사전학습 모델을학습없이제품위치후보추정에쓰고,좌표를저장해오프라인데이터셋을구축하는실험이다. 실시간시스템이나최종검사모델의추론성능실험이아니다. 모델학습·Fine-tuning·유료API·OpenAI API·Push는수행하지않았다.

## 2. 기존 CenterCrop의 한계

기존제공양성마스크51,295장전수에서896/768/640Crop은각각82/967/4600이미지의위치정답을완전히제거했다. 그전수값은새표본의모집단통계와직접비교하지않는다. 본실험의동일표본에서전체·CenterCrop을다시계산했다.

## 3. YOLO11 사전학습 모델 소개

공식공개파일 yolo11n.pt,5,613,764bytes,SHA256 `0ebbc80d4a7680d14987a577cd21342b65ecfd94632bd9a8da63ae6417644ee1`. [공식모델문서](https://docs.ultralytics.com/models/yolo11),[공식다운로드](https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11n.pt),[공식라이선스](https://www.ultralytics.com/license). 공개자료는AGPL-3.0/별도Enterprise라이선스체계를표시한다. 이번에는추론용공개가중치만받았고법적적합성보증을하지않는다.

## 4. 실험 환경

WSL2 Ubuntu,Python3.12,Ultralytics8.4.210,PyTorch2.15.0+cpu,OpenCV5.0,CPU4logical/torch2threads,CUDA false. 기존uv.lock과.venv를수정하지않고outputs내별도venv에Ultralytics만추가하고기존분석패키지를읽기참조했다. 전체선언의존성설치완료를주장하지않고실제import/추론성공을검증했다. conf=0.25, IoU/NMS=0.7,imgsz640,batch1,max_det100,class-awareNMS,FP32. 초기sandbox DNS실패후공개파일접근허용으로설치/다운로드했다.

[config.json](../outputs/yolo11_dynamic_crop_v1/config.json)

[runtime.json](../outputs/yolo11_dynamic_crop_v1/runtime.json)

[manifest.json](../outputs/yolo11_dynamic_crop_v1/weights/manifest.json)

## 5. 데이터 표본 선정

| cohort | status | images |
| --- | --- | --- |
| general | NG | 600 |
| general | OK | 600 |
| mask_informed_risk | NG | 150 |

| cohort | background_type | images |
| --- | --- | --- |
| general | BLACK | 720 |
| general | GRAY | 94 |
| general | WHITE | 386 |
| mask_informed_risk | BLACK | 90 |
| mask_informed_risk | GRAY | 11 |
| mask_informed_risk | WHITE | 49 |

seed20261112. 일반1200=30품목×8선언제품×5시점,OK/NG각600,C1~C5각240,Validation/Test각600. 품목별각split에서OK2/NG2제품을난수선택했다. 마스크위치로선택하지않았다. 별도위험150=30제품×5시점,작은마스크/외곽손실기준으로선정했고일반평가와분리했다. 원래split·NG상태·has_mask를유지했다. 제품선언키는실제물리제품동일성보증은아니다.

[sample_manifest.csv](../outputs/yolo11_dynamic_crop_v1/sample_manifest.csv)

## 6. 제품 BBox 추정 방식

A최고confidence,B프레임중심과BBox중심이가장가까운것,C프레임중앙을포함하는것중최대면적,D모든검출Union. GT마스크는정책선택에사용하지않았다. 비교용native캐시는사전지정A+30%이며GT에따라선정한최적정책이아니다. COCO이름을제품분류정답으로재라벨하지않는다. 검증된제품전체BBox정답이없어제품IoU/영역Recall/PartialObjectRate와제품점유율은UNVERIFIED다. 기존OpenCV전경은정답으로사용하지않았다.

## 7. Dynamic Crop 알고리즘

검출BBox(x0,y0,x1,y1),너비w/높이h에서각변에mw/mh를추가하므로확장폭은(1+2m)w이다. 그최대변으로정사각을만들고정수경계손실보호2px를더한다. 변길이는1024상한,이미지밖이면정사각을프레임안으로평행이동한다. 원본absolute XYXY,끝좌표exclusive. 두축을각각잘라직사각으로만드는정책과다르다.

원본해상도의lossless PNG및native defect mask는outputs/native_crops에내부보관하고외부PDF에는포함하지않는다. 대안정책은좌표만저장해재사용한다. 후보없는경우원본경로참조로복귀하여중복이미지를만들지않는다. Crop캐시에는Resize/Normalize를적용하지않고후속모델입력adapter에서수행한다.

## 8. Margin 및 Fallback 정책

0/10/20/30%를비교한다. Fallback은NO_DETECTION/NO_CENTRAL_BOX에서만원본전체좌표를쓴다. confidence만으로제품전체성공을판정하지않고성공여부자체를UNVERIFIED로남긴다. 잘못된부분BBox를검출하는quality gate는제품GT부재로검증하지못했다. 따라서본Fallback은제품보존을보증하는정책이아니다.

## 9. 평가 지표 정의

검출발생률=검출1개이상이미지/전체이미지로제품검출정확도가아니다. 결함픽셀보존율=Crop안양성픽셀/원본양성픽셀,전체요약은픽셀가중합계와영상평균을구분한다. 미제공NG는평가NA,제공빈마스크는양성보존분모에서제외한다. raw dynamic의NO_CANDIDATE는NA이며0보존으로조작하지않는다. 후보조건부표와전체출력가능률,같은후보집합의paired표를함께제공한다.

NEAREST실제출력마스크양성픽셀과8연결성분수를계산하고원본성분ID도별도NN추적했다. 원본성분면적1024px²미만이small component,전체mask면적1024미만이small image,원본가장자리128px에양성하나라도있으면outer image다. 서로분모가다르다. 이미지변화지표는150일반표본에서각Crop영역을동일native영역에복원해비교했다. 256/512만실제adapter평가했고224/392/640전체조합은미실행이다.

## 10. 제품 검출 결과

| cohort | images | detected | detection_occurrence_rate | no_detection |
| --- | --- | --- | --- | --- |
| general | 1200 | 770 | 0.64167 | 430 |
| mask_informed_risk | 150 | 97 | 0.64667 | 53 |

| category | images | detected | no_detection | detection_occurrence_rate |
| --- | --- | --- | --- | --- |
| sim_card_set | 40 | 9 | 31 | 0.225 |
| audiojack | 40 | 10 | 30 | 0.25 |
| pcb | 40 | 10 | 30 | 0.25 |
| woodstick | 40 | 11 | 29 | 0.275 |
| zipper | 40 | 11 | 29 | 0.275 |
| regulator | 40 | 12 | 28 | 0.3 |
| toy_brick | 40 | 14 | 26 | 0.35 |
| eraser | 40 | 18 | 22 | 0.45 |
| terminalblock | 40 | 21 | 19 | 0.525 |
| switch | 40 | 22 | 18 | 0.55 |
| toy | 40 | 23 | 17 | 0.575 |
| plastic_plug | 40 | 23 | 17 | 0.575 |
| usb | 40 | 25 | 15 | 0.625 |
| transistor1 | 40 | 25 | 15 | 0.625 |
| usb_adaptor | 40 | 26 | 14 | 0.65 |
| end_cap | 40 | 28 | 12 | 0.7 |
| button_battery | 40 | 29 | 11 | 0.725 |
| toothbrush | 40 | 29 | 11 | 0.725 |
| phone_battery | 40 | 29 | 11 | 0.725 |
| plastic_nut | 40 | 29 | 11 | 0.725 |
| vcpill | 40 | 30 | 10 | 0.75 |
| bottle_cap | 40 | 32 | 8 | 0.8 |
| mounts | 40 | 36 | 4 | 0.9 |
| tape | 40 | 36 | 4 | 0.9 |
| u_block | 40 | 37 | 3 | 0.925 |
| rolled_strip_base | 40 | 37 | 3 | 0.925 |
| mint | 40 | 38 | 2 | 0.95 |
| fire_hood | 40 | 40 | 0 | 1 |
| porcelain_doll | 40 | 40 | 0 | 1 |
| wooden_beads | 40 | 40 | 0 | 1 |

제품정답없이COCO검출이유효제품BBox인지확정할수없다. COCO에없는품목에서도후보는나오지만제품전체를감쌌는지독립확인이필요하다. 외곽결함을남겼다는사실만으로제품전체를보존했다고가정하지않는다.

## 11. CenterCrop 비교 결과

| method | images | available | positive_masks | available_positive_masks | conditional_pixel_weighted_retention |
| --- | --- | --- | --- | --- | --- |
| center640 | 1200 | 1200 | 409 | 409 | 0.81671 |
| center768 | 1200 | 1200 | 409 | 409 | 0.94173 |
| center896 | 1200 | 1200 | 409 | 409 | 0.98588 |
| confidence_m0 | 1200 | 770 | 409 | 255 | 0.96674 |
| confidence_m10 | 1200 | 770 | 409 | 255 | 0.97404 |
| confidence_m20 | 1200 | 770 | 409 | 255 | 0.9835 |
| confidence_m30 | 1200 | 770 | 409 | 255 | 0.98577 |
| confidence_m30_fallback | 1200 | 1200 | 409 | 409 | 0.99062 |
| full | 1200 | 1200 | 409 | 409 | 1 |

원본전체출력이있는사전지정A30+Fallback의보존율은99.061840%,Center896은98.587564%로동일일반표본기준차이는0.4743%p다. 후보없는NG를제외한raw dynamic값을전체표본CenterCrop과동일분모처럼해석하지않는다.

[matched_detection_subset_summary.csv](../outputs/yolo11_dynamic_crop_v1/metrics/matched_detection_subset_summary.csv)

## 12. 결함 마스크 보존율

| method | available_positive_masks | removed | partial | preserved | median_retention | p05_retention |
| --- | --- | --- | --- | --- | --- | --- |
| center640 | 409 | 39 | 89 | 281 | 1 | 0 |
| center768 | 409 | 8 | 34 | 367 | 1 | 0.6449 |
| center896 | 409 | 0 | 14 | 395 | 1 | 1 |
| confidence_m0 | 255 | 8 | 18 | 229 | 1 | 0.62287 |
| confidence_m10 | 255 | 6 | 10 | 239 | 1 | 0.86331 |
| confidence_m20 | 255 | 5 | 6 | 244 | 1 | 1 |
| confidence_m30 | 255 | 5 | 3 | 247 | 1 | 1 |
| confidence_m30_fallback | 409 | 5 | 3 | 401 | 1 | 1 |
| full | 409 | 0 | 0 | 409 | 1 | 1 |

별도위험표본결과는method_summary.csv의cohort=mask_informed_risk를본다. 위험표본은결함위치를사용해선정했으므로일반1200과합쳐성공률을보고하지않는다. Crop으로결함이사라져도NG라벨을OK로바꾸지않는다.

## 13. 작은 결함 분석

| method | t256_output_pixels_median | t512_output_pixels_median | t256_small_component_survival | t512_small_component_survival |
| --- | --- | --- | --- | --- |
| center640 | 214 | 859 | 0.90722 | 0.90722 |
| center768 | 178 | 720 | 0.97938 | 0.97938 |
| center896 | 134 | 544 | 1 | 1 |
| confidence_m0 | 214 | 860 | 0.96403 | 0.96403 |
| confidence_m10 | 154 | 616 | 0.97122 | 0.97122 |
| confidence_m20 | 126 | 525 | 0.97842 | 0.98561 |
| confidence_m30 | 110 | 443 | 0.97122 | 0.98561 |
| confidence_m30_fallback | 108 | 436 | 0.97938 | 0.98969 |
| full | 105 | 419 | 0.98969 | 1 |

작은결함의출력확대와Crop위치손실을함께봐야한다. 남은양성pixel수가늘어도사라진component를복구한것은아니다. 모델검출정확도개선은학습실험전에는주장하지않는다.

## 14. 카테고리·시점·배경별 결과

[detection_by_background_type.csv](../outputs/yolo11_dynamic_crop_v1/metrics/detection_by_background_type.csv)

[detection_by_view.csv](../outputs/yolo11_dynamic_crop_v1/metrics/detection_by_view.csv)

[crop_by_category.csv](../outputs/yolo11_dynamic_crop_v1/metrics/crop_by_category.csv)

[crop_by_view.csv](../outputs/yolo11_dynamic_crop_v1/metrics/crop_by_view.csv)

[crop_by_outer.csv](../outputs/yolo11_dynamic_crop_v1/metrics/crop_by_outer.csv)

배경은기존border-lab-v5자동분류다. 배경과품목/시점의혼합을통제하지않은차이는인과관계가아니다. 같은선언제품5시점은독립표본5개가아니다. 일반/위험을분리한기술통계이며최적정책선택용유의성검정을하지않았다.

## 15. 오프라인 구축 비용 및 메모리

| cohort | images | mean_predict_ms | median_predict_ms | p95_predict_ms | max_rss_mb |
| --- | --- | --- | --- | --- | --- |
| general | 1200 | 56.436 | 55.514 | 71.224 | 623.66 |
| mask_informed_risk | 150 | 55.402 | 54.591 | 67.276 | 515.21 |

일반표본YOLO wall predict 합계67.723초,직렬호출기준처리량17.719images/sec. 이는디코딩/PNG저장/GT평가시간을제외한다. 프로세스RSS는torch/library를포함하고GPU메모리는사용하지않았다. 실제5시점제품단위비용은해당5개wall시간합계로CSV에서계산한다.

| index | crop_copy_ms | lossless_encode_ms | adapter_resize512_ms |
| --- | --- | --- | --- |
| count | 90 | 90 | 90 |
| mean | 0.4876 | 52.98 | 0.48102 |
| std | 0.12513 | 20.321 | 0.44532 |
| min | 0.005776 | 0.55832 | 0.12044 |
| 50% | 0.47885 | 55.895 | 0.33179 |
| 95% | 0.68125 | 79.986 | 1.7891 |
| max | 0.96874 | 81.391 | 1.8909 |

Crop/인코딩비용은품목별1장×30,사전1회후3회반복한표본추정이며디스크write미포함. 이미지별YOLO는처음1회만실행하여캐시했고같은영상YOLO반복벤치마크는하지않았다. 합성black3회warmup은각프로세스시작에만수행해별도기록했다. YOLO비용은데이터셋최초구축비용이며후속12모델의순수추론/학습시간에포함하지않는다.

### 선언 제품 5시점 YOLO 구축 비용 합계(ms)

| cohort | count | mean | median | max |
| --- | --- | --- | --- | --- |
| general | 240 | 282.178 | 280.58 | 427.618 |
| mask_informed_risk | 30 | 277.011 | 275.868 | 346.569 |

합계는동일선언제품5장의YOLO wall시간만포함하며PNG저장이나후속모델시간이아니다.

## 16. 실패 사례 분석

확정실패는NO_DETECTION또는정책C의NO_CENTRAL_BOX다. EXECUTION_ERROR는0이다. PARTIAL_OBJECT는제품GT없어미확정이다. 마스크완전제거는관측된전처리실패이지만어떤원제품부분이빠졌는지자동으로확정하지않는다. Union은관계없는배경COCO오탐까지포함할수있으며여백확장은보존율을올리면서제품확대효과를줄일수있다.

## 17. 모델별 전처리 충돌 위험

native Crop에는공통Resize/Normalize를하지않았다. PatchCore256→224와Dinomaly/INP448→392의공식중앙Crop을그대로더하면이중Crop이다. torchvision내부800Resize/Normalize와YOLO/RT-DETR0..1,ViTDet0..255를각adapter에서분리한다. 참조: reports/MODEL_INPUT_REQUIREMENTS.md. YOLO의COCOclass와후속결함class는완전히별개다.

## 18. 최종 정책 제안과 판정

**판정: INCONCLUSIVE.** 제품전체BBox정답부재로제품보존·부분물체율·정확도를확인하지못해ADOPT_CANDIDATE를선언할수없다. 오프라인구축가능성은실제추론/캐시로VERIFIED지만전품목공통전처리채택은보류한다. 먼저소규모제품전체BBox를독립검수하고품목/배경/시점별로NO_DETECTION및부분BBox를검증해야한다. Fine-tuning필요성은후속가설이며이번에수행하지않았다.

질문별답: (1)검출발생률은표와같으나제품전체안정성은미확인. (2)COCO밖품목에서도후보생성은가능하지만유효성미확인. (3)낮은품목은품목표참조. (4)배경별차이는관측되나인과미확정. (5)최고confidence가최선인지는미확정/제품정답없이선정불가. (6)여백곡선은후보조건부보존변화를보여준다. (7)CenterCrop대비동일표본의Fallback표로판단. (8)실제제품점유율은미확인이고프레임면적proxy만보고. (9)오프라인최초비용이므로실시간SLA판정불필요. (10)제품학습이필요할수있으나독립GT평가우선. (11)일괄적용보류. (12)이중Crop위험있음.

### 후속 제안: YOLO와 Center896 결합 실험

기존 결과를 확인한 뒤 사용자가 제안한 후속 탐색이다. 기존 YOLO 추론을 다시 하지 않고 저장 좌표로만 계산했다. Center896 사각형과 A30 후보 사각형의 합집합을 모두 포함하는 가장 작은 프레임 내부 정사각을 사용한다. 미검출 시 Center896을 쓰는 hybrid896과 원본 전체를 쓰는 hybrid896_fullfallback을 분리했다. 원본 기하에서 Center896보다 결함을 추가로 잘라내지 않는 포함 관계를 검증했다. 정책 선택에 GT 마스크를 쓰지 않았지만 같은 평가 표본 결과를 본 뒤 고안한 규칙이므로 독립 holdout 검증이 필요하다.

| cohort | method | positive_masks | pixel_weighted_retention | removed | partial |
| --- | --- | --- | --- | --- | --- |
| general | hybrid896 | 409 | 0.988456 | 0 | 8 |
| general | hybrid896_fullfallback | 409 | 1 | 0 | 0 |
| mask_informed_risk | hybrid896 | 103 | 0.983284 | 0 | 2 |
| mask_informed_risk | hybrid896_fullfallback | 103 | 1 | 0 | 0 |

| method | mean_native_side | full_frame_fraction | t256_mask_pixels_median | t512_mask_pixels_median |
| --- | --- | --- | --- | --- |
| hybrid896 | 967.506 | 0.4625 | 120 | 487 |
| hybrid896_fullfallback | 1013.37 | 0.820833 | 108 | 436 |

hybrid896_fullfallback은 일반409/위험103개 양성 제공 마스크를 이 표본에서 모두 보존했다. 다만 일반 이미지의82.0833%가1024 전체 프레임으로 돌아가고 평균 변길이는1013.37px이므로 대부분 전체 Resize에 가까워진다. 보존 안정성과 제품 확대 효과 사이의 교환관계가 드러난다. 전체151,050장 보존이나 제품 전체 BBox 성공을 증명하지 않으며 최종 판정은 INCONCLUSIVE로 유지한다.

![hybrid_anchor_tradeoff](../outputs/yolo11_dynamic_crop_v1/figures/hybrid_anchor_tradeoff.png)

결합은 같은 표본에서 픽셀 보존을 개선했지만 원본 전체 프레임 사용 비중이 높다. 입력 해상도를 자동으로 높이는 정책과 같지 않으며 작은 결함 검출 성능은 별도 학습 실험으로 확인한다.

[추가 좌표와 표본 결과](../outputs/yolo11_dynamic_crop_v1/hybrid_extension/summary.csv)

[후속 검증](../outputs/yolo11_dynamic_crop_v1/hybrid_extension/validation.json)

## 19. 분석 한계

제품GT·제품IoU/recall/점유율·PARTIAL_OBJECT는UNVERIFIED. 30품목균형표본은전체데이터비율의불편추정이아니다. 위험표본은의도적선택이다. confidence .25/640설정의한사전학습모델만평가했고저confidence나타모델을탐색하지않았다. 실제downstream학습성능·최적해상도·12모델순수추론성능은NOT_ANALYZED. 원본/파생사례영상공유권한미확인으로PDF에는통계그래프만포함했다.

## 20. 재현 방법 및 근거 파일

`outputs/yolo11_dynamic_crop_v1/env/bin/python scripts/yolo11_offline_crop_experiment.py smoke` → `infer` → `evaluate`. 완료이미지는체크포인트를재사용한다. 가중치/metadata/sample/geometry해시가일치해야한다. 보고서집계는`uv run --offline python scripts/report_yolo11_dynamic_crop.py`. 실제Native후보출력과분류상태·원본좌표·변환라벨은offline_native_dataset_manifest.csv와offline_native_class_labels.jsonl로추적한다. 후속모델은이좌표/PNG를재사용하고YOLO를다시실행하지않는다.

[inference_per_image.csv](../outputs/yolo11_dynamic_crop_v1/metrics/inference_per_image.csv)

[per_image_crop_metrics.csv](../outputs/yolo11_dynamic_crop_v1/metrics/per_image_crop_metrics.csv)

[offline_native_dataset_manifest.csv](../outputs/yolo11_dynamic_crop_v1/metrics/offline_native_dataset_manifest.csv)

[offline_native_class_labels.jsonl](../outputs/yolo11_dynamic_crop_v1/metrics/offline_native_class_labels.jsonl)

## 통계 그래프와 해석

### category_detection

![category_detection](../outputs/yolo11_dynamic_crop_v1/figures/category_detection.png)

일반 표본 품목당40장의 검출 발생률이다. COCO 후보가 있다는 뜻이며 제품 전체 BBox 성공률은 아니다.

### background_view_detection

![background_view_detection](../outputs/yolo11_dynamic_crop_v1/figures/background_view_detection.png)

배경·시점별 검출 발생률. 품목 구성과 배경 예측 오류가 섞여 있어 원인 효과로 해석하지 않는다.

### coco_classes

![coco_classes](../outputs/yolo11_dynamic_crop_v1/figures/coco_classes.png)

오분류된 COCO 이름이어도 위치 후보로 평가할 수 있지만 Real-IAD 제품 카테고리 정답으로 바꾸지 않는다.

### policy_availability

![policy_availability](../outputs/yolo11_dynamic_crop_v1/figures/policy_availability.png)

중앙 포함 후보가 없으면 해당 정책은 NO_CENTRAL_BOX다. 최고 confidence 정책이 최적이라는 가정을 두지 않는다. 제품 정답이 없어 실제 성공률은 미확인이다.

### margin_retention

![margin_retention](../outputs/yolo11_dynamic_crop_v1/figures/margin_retention.png)

미검출은 보존율 계산에서NA이므로 이 그래프는 후보가 있는 위치정답에 조건부다. 전체 표본 안전성을 뜻하지 않으며 별도 availability와 Fallback을 함께 본다.

### center_vs_dynamic

![center_vs_dynamic](../outputs/yolo11_dynamic_crop_v1/figures/center_vs_dynamic.png)

일반 표본 동일 이미지의 비교다. raw dynamic은 후보 없는 이미지를 처리하지 못한다. Fallback 행만 전체 표본에 출력이 있다. 아래 막대 분모가 달라질 수 있어 표의 available_positive_masks를 함께 확인한다.

### small_defect_retention

![small_defect_retention](../outputs/yolo11_dynamic_crop_v1/figures/small_defect_retention.png)

원본 마스크 면적1024px² 미만인 이미지 부분집합이다. 실제 소형 연결 성분의 생존율은 별도 표로 제공하며 서로 분모를 혼용하지 않는다.

### resized_mask_support

![resized_mask_support](../outputs/yolo11_dynamic_crop_v1/figures/resized_mask_support.png)

단순 면적비 proxy가 아니라 실제 NEAREST 마스크의 양성 픽셀 수다. Crop으로 제거된 결함은 확대해도 복원되지 않는다.

### small_component_survival

![small_component_survival](../outputs/yolo11_dynamic_crop_v1/figures/small_component_survival.png)

원본8연결 성분 ID를 NEAREST로 추적했다. 출력의 연결 성분 개수와 동일하지 않으며 두 성분이 합쳐져도 각ID가 남을 수 있다.

### aligned_image_quality

![aligned_image_quality](../outputs/yolo11_dynamic_crop_v1/figures/aligned_image_quality.png)

Crop마다 같은 원본 좌표 영역에 복원해 비교했다. 서로 다른영역의지표차이는공통전체영상품질우열을뜻하지않는다. raw dynamic은미검출로표본수가달라질수있다.

### offline_cost

![offline_cost](../outputs/yolo11_dynamic_crop_v1/figures/offline_cost.png)

가중치로드·합성warmup은분리했다. 이시간은오프라인데이터구축비용이며후속12모델순수추론시간에포함하지않는다. 이미지내용과품목혼합이비용차이에영향을줄수있다.

### category_failures

![category_failures](../outputs/yolo11_dynamic_crop_v1/figures/category_failures.png)

제품일부탐지(PARTIAL_OBJECT)는검증된제품정답이없어확정하지않았다. 여기서는검출자체가없는실패만집계한다.

### fallback_effect

![fallback_effect](../outputs/yolo11_dynamic_crop_v1/figures/fallback_effect.png)

검출실패시원본전체Resize로복귀하면출력coverage는회복되지만잘못된BBox를탐지해복귀시키는검증된gate는없다. 출력이있다는사실은제품전체보존성공이아니다.

### occupancy_unverified

![occupancy_unverified](../outputs/yolo11_dynamic_crop_v1/figures/occupancy_unverified.png)

이값은제품점유율이아니라남긴원본프레임면적이다. 제품정답이없어제품점유율개선과제품영역recall을계산하지않았으며관련주장은UNVERIFIED다.