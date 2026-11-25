# Real-IAD 데이터 분석 통합 및 전처리 정책 검토 보고서

작성 UTC: 2026-11-12T00:27:50.549854+00:00. 상태: 수치/파일/정적 소스 검증 VERIFIED, 의미/실행 미검증 UNVERIFIED, 미수행 NOT_ANALYZED. 정책은 제안이며 확정하지 않는다.

## 1. Executive Summary

151,050 JPG(OK72,840/NG78,210), 제공 마스크51,329,30품목,C1~C5. 선언된5시점 그룹30,210개이며 이미지 수와 구분한다. 기존 전체 해상도453,150행을 재사용했다. 제품 영역 자동 품질 통과78,526(51.987%)장으로 전체 대표 표본이 아니다. 896 Crop에서도82개의 양성 위치 정답 이미지가 완전히 제거되어 전 품목 공통Crop 안전성을 확정할 수 없다.

검토 결론: 전체Resize를 대조군으로 유지하고 Crop·배경 치환·모델 기본 전처리와 공통 어댑터의 충돌을 별도 실험으로 검증한다. 12모델은 입력이 동일하지 않다. 모델 학습·가중치 다운로드·API 호출·Push는 수행하지 않았다.

## 2. 데이터셋 개요

[category_status_counts.csv](../outputs/preprocessing_review_20261112_v2/review_assets/statistics/category_status_counts.csv)

| category | status | images | declared_products | with_mask |
| --- | --- | --- | --- | --- |
| audiojack | NG | 2585 | 517 | 1296 |
| audiojack | OK | 2465 | 493 | 0 |
| bottle_cap | NG | 2555 | 511 | 1631 |
| bottle_cap | OK | 2460 | 492 | 0 |
| button_battery | NG | 2585 | 517 | 2150 |
| button_battery | OK | 2415 | 483 | 0 |
| end_cap | NG | 2600 | 520 | 2183 |
| end_cap | OK | 2410 | 482 | 0 |
| eraser | NG | 2605 | 521 | 1488 |
| eraser | OK | 2460 | 492 | 0 |
| fire_hood | NG | 2520 | 504 | 1350 |
| fire_hood | OK | 2505 | 501 | 0 |
| mint | NG | 3635 | 727 | 2099 |
| mint | OK | 1670 | 334 | 0 |
| mounts | NG | 2555 | 511 | 1338 |
| mounts | OK | 2495 | 499 | 0 |
| pcb | NG | 2545 | 509 | 2289 |
| pcb | OK | 2465 | 493 | 0 |
| phone_battery | NG | 2585 | 517 | 1550 |
| phone_battery | OK | 2415 | 483 | 0 |
| plastic_nut | NG | 2500 | 500 | 1246 |
| plastic_nut | OK | 2510 | 502 | 0 |
| plastic_plug | NG | 2570 | 514 | 1419 |
| plastic_plug | OK | 2425 | 485 | 0 |
| porcelain_doll | NG | 2585 | 517 | 1255 |
| porcelain_doll | OK | 2415 | 483 | 0 |
| regulator | NG | 2610 | 522 | 1080 |
| regulator | OK | 2490 | 498 | 0 |
| rolled_strip_base | NG | 2565 | 513 | 2525 |
| rolled_strip_base | OK | 2485 | 497 | 0 |
| sim_card_set | NG | 2540 | 508 | 2069 |
| sim_card_set | OK | 2490 | 498 | 0 |
| switch | NG | 2590 | 518 | 1994 |
| switch | OK | 2460 | 492 | 0 |
| tape | NG | 2600 | 520 | 1443 |
| tape | OK | 2500 | 500 | 0 |
| terminalblock | NG | 2615 | 523 | 2008 |
| terminalblock | OK | 2435 | 487 | 0 |
| toothbrush | NG | 2560 | 512 | 2027 |
| toothbrush | OK | 2445 | 489 | 0 |
| toy | NG | 2530 | 506 | 2190 |
| toy | OK | 2495 | 499 | 0 |
| toy_brick | NG | 2530 | 506 | 1536 |
| toy_brick | OK | 2480 | 496 | 0 |
| transistor1 | NG | 2515 | 503 | 2117 |
| transistor1 | OK | 2485 | 497 | 0 |
| u_block | NG | 2495 | 499 | 1214 |
| u_block | OK | 2495 | 499 | 0 |
| usb | NG | 2590 | 518 | 1754 |
| usb | OK | 2460 | 492 | 0 |
| usb_adaptor | NG | 2710 | 542 | 1520 |
| usb_adaptor | OK | 2305 | 461 | 0 |
| vcpill | NG | 2505 | 501 | 1470 |
| vcpill | OK | 2520 | 504 | 0 |
| wooden_beads | NG | 2830 | 566 | 1684 |
| wooden_beads | OK | 2175 | 435 | 0 |
| woodstick | NG | 2500 | 500 | 1073 |
| woodstick | OK | 2505 | 501 | 0 |
| zipper | NG | 2500 | 500 | 2331 |
| zipper | OK | 2505 | 501 | 0 |

NG78,210 중51,329(65.6297%)은 위치 정답이 제공되고26,881은 미제공이다. 미제공을 정상/empty detection label로 취급하지 않는다. 실제 누락인지 의도된 미제공인지 원본 annotation manifest 없이 확정할 수 없다. 제공PNG34개는 실제0픽셀인 빈 정답으로 미제공과 다르다.

## 3. 분석 실행 및 검증 상태

| domain | scope | status | note |
| --- | --- | --- | --- |
| metadata | 151050 JPG,51329 PNG; Windows split | VERIFIED | declared product groups; physical identity UNVERIFIED |
| brightness | 151050 JPG; whole grayscale | VERIFIED | v6 cache imported and regrouped by preserved split |
| regional_brightness | 151050 JPG; border-lab-v5, accepted78526 | VERIFIED | values numerically checked; product GT accuracy UNVERIFIED |
| heatmap | Train NG54805; provided masks36173;presence64 | VERIFIED | occupancy_known/positive, unobserved NaN |
| bbox | 60629 boxes,8classes | VERIFIED | 7 masked conflicting images excluded; unannotated NG excluded |
| mask | 51329 PNG,gray>0 | VERIFIED | all grayscale values are supported; not independent semantic boundary proof |
| resolution | 151050x3 frozen metric rows | VERIFIED | numeric cache rebound metadata without recomputation |
| crop | 51329 provided masks;60629 boxes;300 product samples | VERIFIED | heuristic product geography remains UNVERIFIED |
| content | 202379 exact byte hashes | VERIFIED | cross-split count belongs to old split; canonical quality review is separate |

v1/v2 마스크 체크포인트51,329개의 내용·입력해시가 같아 PNG를 다시 읽지 않았다. 중단 때 미저장된300표본 제품 기하만 완료하고 이미지별로 체크포인트화했다. 과거 실패는 마스크 미제공 NaN merge키 중복이었으며 원본과 계산 결과를 보존했다. 최신 v2 complete.json으로 완료 범위를 확인한다.

## 4. 메타데이터 및 클래스 분포

| defect_type | status | images | declared_products | with_mask |
| --- | --- | --- | --- | --- |
| AK | NG | 11360 | 2272 | 6774 |
| BX | NG | 2805 | 561 | 2569 |
| CH | NG | 4470 | 894 | 2911 |
| HS | NG | 15305 | 3061 | 8702 |
| OK | OK | 72840 | 14568 | 0 |
| PS | NG | 2525 | 505 | 2120 |
| QS | NG | 17385 | 3477 | 12600 |
| UNRESOLVED | NG | 10 | 2 | 7 |
| YW | NG | 2145 | 429 | 1417 |
| ZW | NG | 22205 | 4441 | 14229 |

| view | status | images | declared_products | with_mask |
| --- | --- | --- | --- | --- |
| C1 | NG | 15642 | 15642 | 9415 |
| C1 | OK | 14568 | 14568 | 0 |
| C2 | NG | 15642 | 15642 | 10163 |
| C2 | OK | 14568 | 14568 | 0 |
| C3 | NG | 15642 | 15642 | 10534 |
| C3 | OK | 14568 | 14568 | 0 |
| C4 | NG | 15642 | 15642 | 11138 |
| C4 | OK | 14568 | 14568 | 0 |
| C5 | NG | 15642 | 15642 | 10079 |
| C5 | OK | 14568 | 14568 | 0 |

| split | status | images | declared_products | with_mask |
| --- | --- | --- | --- | --- |
| test | NG | 11530 | 2306 | 7515 |
| test | OK | 11130 | 2226 | 0 |
| train | NG | 54805 | 10961 | 36173 |
| train | OK | 50930 | 10186 | 0 |
| validation | NG | 11875 | 2375 | 7641 |
| validation | OK | 10780 | 2156 | 0 |

class imbalance는 defect_type별 이미지 수와 declared_products를 함께 비교한다. 정상14,568그룹/불량15,642그룹=30,210그룹이다. 제품 기준은 category/status/defect/serial 선언 키이며 실제 물리 제품 식별의 독립성은 UNVERIFIED다. 모든 그룹은5시점이며 보존한 분할에서 제품 단위 중복은0이다. Train105,735/Validation22,655/Test22,660.

## 5. 배경색과 제품 밝기 분석

| background_type | NG | OK | NG_fraction |
| --- | --- | --- | --- |
| BLACK | 47356 | 43415 | 0.521708 |
| GRAY | 5599 | 5627 | 0.498753 |
| MIXED | 5 | 5 | 0.5 |
| UNKNOWN | 3 | 6 | 0.333333 |
| WHITE | 25247 | 23787 | 0.514888 |

배경 분류는 가장자리4%의Lab/HSV/gray, 연결성 및 신뢰도 기반이며 전체 평균만으로 나누지 않았다. WHITE/BLACK은 자동 예측, GRAY는 무채색만 의미하지 않아 중간 밝기의 유색 배경도 포함한다. confidence는 보정된 정확도 확률이 아니다.

[selection_joint_distribution.csv](../outputs/preprocessing_review_20261112_v2/review_assets/statistics/selection_joint_distribution.csv)

| quality_group | background_type | images | within_quality_fraction |
| --- | --- | --- | --- |
| accepted | BLACK | 57501 | 0.732254 |
| accepted | GRAY | 486 | 0.00618903 |
| accepted | WHITE | 20539 | 0.261557 |
| not_accepted | BLACK | 33270 | 0.458745 |
| not_accepted | GRAY | 10740 | 0.148089 |
| not_accepted | MIXED | 10 | 0.000137885 |
| not_accepted | UNKNOWN | 9 | 0.000124097 |
| not_accepted | WHITE | 28495 | 0.392904 |

통과 집단 BLACK73.2254%, 미통과45.8745%로27.3509%p 차이다. 통과 집단 GRAY0.6189%, 미통과14.8089%다. 분할 성공이 배경·품목에 따라 달라 제품 밝기에서 선택 편향이 있다. 6개 품목 sim_card_set, tape, toothbrush, u_block, usb_adaptor, zipper는 통과가0이므로 제품 영역 밝기 결론을 제시할 수 없다.

### 품질 통과/미통과 집단의 비교 분모

카테고리별 분포와 통과율은 selection_category.csv 및 그래프에 있다. 아래 집단별 비율은 각 집단 내부 분포이고, 시점별 통과 확률과 구분한다. 미통과 실제 제품 크기·위치는 정답 분할 부재로 UNVERIFIED이며 후보 기하 차이만 진단할 수 있다.

| quality_group | status | images | within_quality_fraction |
| --- | --- | --- | --- |
| accepted | NG | 41025 | 0.522438 |
| accepted | OK | 37501 | 0.477562 |
| not_accepted | NG | 37185 | 0.512727 |
| not_accepted | OK | 35339 | 0.487273 |

| quality_group | view | images | within_quality_fraction |
| --- | --- | --- | --- |
| accepted | C1 | 18658 | 0.237603 |
| accepted | C2 | 17678 | 0.225123 |
| accepted | C3 | 13244 | 0.168658 |
| accepted | C4 | 15807 | 0.201296 |
| accepted | C5 | 13139 | 0.16732 |
| not_accepted | C1 | 11552 | 0.159285 |
| not_accepted | C2 | 12532 | 0.172798 |
| not_accepted | C3 | 16966 | 0.233936 |
| not_accepted | C4 | 14403 | 0.198596 |
| not_accepted | C5 | 17071 | 0.235384 |

실패/불확실 사유는 중복된다. 주요 사유별 관측 수는 다음과 같으며 합계를 미통과72,524장으로 해석하면 안 된다.

| reason | images |
| --- | --- |
| possible_shadow_highlight_or_similar_color_product | 65120 |
| color_edge_methods_disagree | 32192 |
| grabcut_disagrees | 19214 |
| product_touches_border_or_mixed_background | 18780 |
| weak_border_color_support | 78 |
| mixed_border_luminance | 8 |
| foreground_too_small_or_color_indistinguishable | 7 |
| no_strong_foreground_seed | 7 |
| substantial_edges_outside_product_candidate | 4 |

300표본의 후보 중심·면적은 미통과 집단의 실제 제품 측정값이 아니다. 통과150장의896 Crop 제품 보존 평균은0.999365,768은0.981085,640은0.899842이며, 원본 제품 점유율 평균0.334715가각각0.436837/0.581222/0.756590으로바뀐다. 남은영역의점유율증가가잘린제품이나결함의복구를뜻하지않는다.

## 6. 정상/불량 밝기 비교

[regional_global_statistics.csv](../outputs/preprocessing_review_20261112_v2/review_assets/statistics/regional_global_statistics.csv)

| status | metric | total_images | valid | mean | median | p05 | p95 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| NG | whole_mean | 78210 | 78210 | 97.5629 | 64.8388 | 21.7273 | 216.112 |
| NG | background_mean | 78210 | 41025 | 68.9427 | 5.60163 | 0.0229516 | 254.974 |
| NG | product_mean | 78210 | 41025 | 125.205 | 125.133 | 51.5263 | 187.992 |
| NG | product_pixel_ratio | 78210 | 41025 | 0.335658 | 0.31839 | 0.194992 | 0.493564 |
| NG | defect_mean | 78210 | 51295 | 108.605 | 106.38 | 26.2472 | 203.658 |
| NG | defect_local_difference | 78210 | 22411 | -6.06074 | -1.90503 | -76.3866 | 52.7706 |
| NG | product_minus_background | 78210 | 41025 | 56.2626 | 122.447 | -201.753 | 183.406 |
| OK | whole_mean | 72840 | 72840 | 98.1374 | 64.2983 | 21.7408 | 215.726 |
| OK | background_mean | 72840 | 37501 | 73.424 | 5.26355 | 0.020411 | 254.974 |
| OK | product_mean | 72840 | 37501 | 121.56 | 119.38 | 52.7548 | 188.745 |
| OK | product_pixel_ratio | 72840 | 37501 | 0.335886 | 0.319016 | 0.19603 | 0.497772 |
| OK | defect_mean | 72840 | 0 | NA | NA | NA | NA |
| OK | defect_local_difference | 72840 | 0 | NA | NA | NA | NA |
| OK | product_minus_background | 72840 | 37501 | 48.1364 | 116.047 | -200.473 | 183.635 |

560개 품목×결함×시점 비교 중 제품 양쪽 표본이 확보된 비교는326개다. 동일 통과 표본에서 배경 제거 후 절대 NG−OK 차이가 줄어든 경우67개, 부호가 바뀐 경우64개다. 전체 영상과 통과 영상의 차이는 선택 효과이며 통과 영상 내 전체→제품 차이는 영역 효과다. 두 효과를 분리하지 않고 배경 편향이 해소됐다고 결론내리지 않는다.

[brightness_interpretation_changes.csv](../outputs/preprocessing_review_20261112_v2/review_assets/statistics/brightness_interpretation_changes.csv)

[regional_per_image_percentile_summary.csv](../outputs/preprocessing_review_20261112_v2/review_assets/statistics/regional_per_image_percentile_summary.csv)

P05/P50/P95는 영상 내부 픽셀 분위수와 영상별 평균의 모집단 분위수를 구분한다. per-image-percentile 집계는 영상별 분위수 평균/중앙값이며 전수 픽셀을 합친 분위수가 아니다. 분포 겹침은 영상 평균값의32bin histogram overlap, Cohen d는 두 집단 pooled sample SD 기준이며 검정/인과지표가 아니다.

## 7. 결함 국소 대비 분석

유효한 제품 내부 국소 주변을 확보한22,411장에 한한다. 원본 해상도에서 결함 밖12px dilation ring과 erosion한 제품 core의 교집합,20px 이상, 결함-제품 겹침90% 이상을 사용했다. 결함 평균−주변 평균의 부호와 분포를 보며 배경이 섞인 전체 outside-mask 밝기와 혼용하지 않는다. 나머지는 미확인으로 유지한다.

| status | metric | total_images | valid | mean | std | median | p05 | p95 | minimum | maximum |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| NG | defect_local_difference | 78210 | 22411 | -6.06074 | 36.7079 | -1.90503 | -76.3866 | 52.7706 | -158.93 | 153.398 |
| OK | defect_local_difference | 72840 | 0 | NA | NA | NA | NA | NA | NA | NA |

## 8. 해상도 정보 손실 분석

| target | psnr_db | ssim | edge_recall | edge_f1 | local_contrast_retention | high_frequency_proxy_retention |
| --- | --- | --- | --- | --- | --- | --- |
| 256 | 35.6323 | 0.943659 | 0.17824 | 0.243461 | 0.604359 | 0.0664721 |
| 512 | 40.985 | 0.975989 | 0.473716 | 0.570144 | 0.761417 | 0.165695 |
| 1024 | 120 | 1 | 1 | 1 | 1 | 1 |

[overall_statistics.csv](../outputs/preprocessing_review_20261112_v2/review_assets/statistics/overall_statistics.csv)

기존 보고값512 PSNR40.985/SSIM.975989/EdgeRecall.473716/국소대비.761417,256의35.632/.943659/.178240/.604359를 CSV와 반올림 허용오차 내 대조했다. 재계산하지 않았다. 원본1024 자기비교PSNR은120dB 저장상한, 에너지 분모0인 검은2이미지×3해상도6행의 비율은NA다.

INTER_AREA 축소→INTER_LINEAR 원본크기 복원, grayscale Gaussian11 sigma1.5 SSIM, exact-pixel Canny100/200 Recall/F1. 고주파는 Laplacian energy 대리값이며 FFT 직접 측정이 아니다. 위치 이동만으로 EdgeRecall이 떨어질 수 있어 모델 검출 실패율로 변환하지 않는다.

| category | images | mean | median | p05 | p95 |
| --- | --- | --- | --- | --- | --- |
| toy_brick | 5010 | 0.860115 | 0.875057 | 0.760578 | 0.907058 |
| woodstick | 5005 | 0.871078 | 0.8778 | 0.79963 | 0.917123 |
| fire_hood | 5025 | 0.88159 | 0.893752 | 0.793637 | 0.9174 |
| sim_card_set | 5030 | 0.904895 | 0.909972 | 0.863139 | 0.932552 |
| usb_adaptor | 5015 | 0.921011 | 0.916412 | 0.903857 | 0.946004 |
| zipper | 5005 | 0.922767 | 0.91875 | 0.885711 | 0.953526 |
| switch | 5050 | 0.926113 | 0.925297 | 0.912729 | 0.937209 |
| pcb | 5010 | 0.926783 | 0.927561 | 0.902966 | 0.948156 |
| end_cap | 5010 | 0.943808 | 0.942033 | 0.931951 | 0.959282 |
| phone_battery | 5000 | 0.94412 | 0.940849 | 0.922624 | 0.97751 |
| rolled_strip_base | 5050 | 0.944795 | 0.945591 | 0.928781 | 0.959019 |
| mint | 5305 | 0.946267 | 0.944292 | 0.931466 | 0.968475 |
| usb | 5050 | 0.946361 | 0.94707 | 0.927901 | 0.962937 |
| u_block | 4990 | 0.949032 | 0.94358 | 0.93431 | 0.973959 |
| plastic_nut | 5010 | 0.950325 | 0.94717 | 0.937483 | 0.975 |
| plastic_plug | 4995 | 0.951948 | 0.94419 | 0.927477 | 0.983313 |
| tape | 5100 | 0.954087 | 0.956132 | 0.937657 | 0.968478 |
| wooden_beads | 5005 | 0.956524 | 0.954948 | 0.941107 | 0.97529 |
| toy | 5025 | 0.956638 | 0.952266 | 0.942411 | 0.975641 |
| bottle_cap | 5015 | 0.956675 | 0.968883 | 0.895538 | 0.97639 |
| eraser | 5065 | 0.958243 | 0.960575 | 0.933836 | 0.973469 |
| audiojack | 5050 | 0.958564 | 0.957393 | 0.950013 | 0.967187 |
| button_battery | 5000 | 0.962143 | 0.963833 | 0.927225 | 0.982144 |
| terminalblock | 5050 | 0.966474 | 0.967747 | 0.958526 | 0.973615 |
| toothbrush | 5005 | 0.967828 | 0.97315 | 0.940879 | 0.982777 |
| regulator | 5100 | 0.96888 | 0.96854 | 0.963147 | 0.975053 |
| mounts | 5050 | 0.97213 | 0.971308 | 0.963425 | 0.979302 |
| transistor1 | 5000 | 0.977366 | 0.980913 | 0.95444 | 0.986953 |
| vcpill | 5025 | 0.978528 | 0.979086 | 0.965864 | 0.990621 |
| porcelain_doll | 5000 | 0.9837 | 0.984728 | 0.977221 | 0.987049 |

| view | target | images | mean | median | p05 | p95 |
| --- | --- | --- | --- | --- | --- | --- |
| C1 | 256 | 30210 | 0.933148 | 0.951794 | 0.811255 | 0.979821 |
| C1 | 512 | 30210 | 0.972091 | 0.979122 | 0.930194 | 0.991122 |
| C2 | 256 | 30210 | 0.946884 | 0.950101 | 0.895641 | 0.982789 |
| C2 | 512 | 30210 | 0.977258 | 0.980421 | 0.954711 | 0.993846 |
| C3 | 256 | 30210 | 0.9467 | 0.949712 | 0.879893 | 0.983219 |
| C3 | 512 | 30210 | 0.977185 | 0.97964 | 0.950187 | 0.993944 |
| C4 | 256 | 30210 | 0.948362 | 0.947004 | 0.895063 | 0.984396 |
| C4 | 512 | 30210 | 0.977731 | 0.979098 | 0.956291 | 0.993857 |
| C5 | 256 | 30210 | 0.943203 | 0.950792 | 0.881576 | 0.983672 |
| C5 | 512 | 30210 | 0.975678 | 0.979483 | 0.950503 | 0.994143 |

| status | target | images | mean | median | p05 | p95 |
| --- | --- | --- | --- | --- | --- | --- |
| NG | 256 | 78210 | 0.944427 | 0.951612 | 0.878223 | 0.982082 |
| NG | 512 | 78210 | 0.976295 | 0.980085 | 0.949619 | 0.993532 |
| OK | 256 | 72840 | 0.942835 | 0.94871 | 0.87902 | 0.983713 |
| OK | 512 | 72840 | 0.97566 | 0.97904 | 0.949765 | 0.993908 |

기존 대표영상·확대 비교는 로컬 reports/RESOLUTION_DETAILED_ANALYSIS.md 및 회의 PDF에 있으나 공유 권한 미확정으로 이 외부 ZIP에 넣지 않았다. 실제 이미지 사례를 공유하지 않는 한계는 통계 그래프가 대신 검증할 수 없다.

## 9. 결함 크기와 해상도 관계

| target | boxes | images | short_under2 | short_under4 | area_under16 | short_median |
| --- | --- | --- | --- | --- | --- | --- |
| 1024 | 60629 | 51288 | 0 | 38 | 26 | 38 |
| 512 | 60629 | 51288 | 38 | 1525 | 816 | 19 |
| 256 | 60629 | 51288 | 1525 | 8667 | 5025 | 9.5 |

| crop | target | remaining_boxes | removed | short_side_under2 | short_side_median | short_side_p05 |
| --- | --- | --- | --- | --- | --- | --- |
| 640 | 256 | 54796 | 5833 | 533 | 14.8 | 3.6 |
| 640 | 512 | 54796 | 5833 | 163 | 29.6 | 7.2 |
| 768 | 256 | 59418 | 1211 | 671 | 12.6667 | 3 |
| 768 | 512 | 59418 | 1211 | 70 | 25.3333 | 6 |
| 896 | 256 | 60539 | 90 | 977 | 10.8571 | 2.57143 |
| 896 | 512 | 60539 | 90 | 48 | 21.7143 | 5.14286 |
| 1024 | 256 | 60629 | 0 | 1525 | 9.5 | 2.25 |
| 1024 | 512 | 60629 | 0 | 38 | 19 | 4.5 |

전체60,629박스 중512 단변2px미만38개,256은1,525개로 기존 결과와 같다. 이는 기하학적 위험 지표다. 전체SSIM이 높아도 미세 결함은 희석될 수 있다. 기존336이미지 ROI 검수는670유효해상도행이며 전체 주석 이미지의 전수ROI 분석은 NOT_ANALYZED다.

## 10. CenterCrop 적합성 분석

[mask_crop_overall.csv](../outputs/preprocessing_review_20261112_v2/review_assets/statistics/mask_crop_overall.csv)

| crop | provided_masks | positive_masks | empty_masks | removed | partial | preserved | pixel_weighted_retention | image_mean_retention | image_median_retention | p05 | minimum |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 640 | 51329 | 51295 | 34 | 4600 | 9175 | 37520 | 0.842422 | 0.842529 | 1 | 0 | 0 |
| 768 | 51329 | 51295 | 34 | 967 | 3983 | 46345 | 0.949045 | 0.957033 | 1 | 0.70308 | 0 |
| 896 | 51329 | 51295 | 34 | 82 | 1029 | 50184 | 0.987357 | 0.994142 | 1 | 1 | 0 |
| 1024 | 51329 | 51295 | 34 | 0 | 0 | 51295 | 1 | 1 | 1 | 1 | 1 |

Crop 좌표는 원본1024에서 [a,a,a+s,a+s], a=(1024−s)/2, 끝좌표 exclusive다. 정확한 defect pixel retention=kept/original positive pixels. 픽셀 가중 보존율과 이미지 평균 보존율을 둘 다 보고했다. 완전 제거 수는 마스크 이미지 단위이며 물리 결함 수가 아니다. 빈34마스크는 보존율NA다.

| crop | segmentation_status | sample_images | valid_product_estimates | mean_retention | minimum_retention | mean_crop_occupancy |
| --- | --- | --- | --- | --- | --- | --- |
| 640 | accepted_heuristic | 150 | 150 | 0.899842 | 0.651429 | 0.75659 |
| 640 | uncertain | 150 | 0 | NA | NA | NA |
| 768 | accepted_heuristic | 150 | 150 | 0.981085 | 0.868578 | 0.581222 |
| 768 | uncertain | 150 | 0 | NA | NA | NA |
| 896 | accepted_heuristic | 150 | 150 | 0.999365 | 0.98107 | 0.436837 |
| 896 | uncertain | 150 | 0 | NA | NA | NA |
| 1024 | accepted_heuristic | 150 | 150 | 1 | 1 | 0.334715 |
| 1024 | uncertain | 150 | 0 | NA | NA | NA |

[mask_crop_by_size.csv](../outputs/preprocessing_review_20261112_v2/review_assets/statistics/mask_crop_by_size.csv)

[mask_crop_resize_area_proxy.csv](../outputs/preprocessing_review_20261112_v2/review_assets/statistics/mask_crop_resize_area_proxy.csv)

제품 점유율은기존300표본 중 자동 품질 통과150장만 제공한다. 미통과 실제 제품 크기·위치는 UNVERIFIED. 미통과 후보 중심·면적은 알고리즘 오류를 포함할 수 있어 진단용으로만 표시한다. 전체 제품 위치/점유율 전수 분석은 NOT_ANALYZED다.

Crop후 결함 면적 proxy=kept_pixels×(target/crop)^2. 연속 좌표의 기하적 예상면적이며 실제 Resize된 binary mask의 양성 픽셀 수는 아니다. 실제 보간·threshold 후 support/연결성 변화는 NOT_ANALYZED다. 작은 pixel support가 실제로 살아남는지는 별도 adapter 시험이 필요하다.

## 11. 마스크 및 BBox 품질

전체PNG grayscale uint8,0..255의256값이 관측된다. 검증정책 >0는 공식 평가 convention과336마스크×6threshold 실험에 근거한다. 높은threshold가 경계를 침식/분절할 수 있어 임의127로 바꾸지 않았다. 이것은 제공 주석 경계의 의미가 독립적으로 증명됐다는 뜻은 아니다.

8방향 연결 성분, 필터 없음, XYXY 원본 absolute좌표. 클래스는AK/BX/CH/HS/PS/QS/YW/ZW 8개. 한 이미지의 모든 성분에 같은 defect_type 부여 가정을 유지한다. 클래스 경로 불일치10이미지 중마스크있는7이미지는 detector label에서 제외한다.

[bbox_defect_distribution.csv](../outputs/preprocessing_review_20261112_v2/review_assets/statistics/bbox_defect_distribution.csv)

| defect_type | boxes | images | area_median | area_p05 | area_p95 | aspect_median | edge_band_count |
| --- | --- | --- | --- | --- | --- | --- | --- |
| AK | 7107 | 6763 | 980 | 210 | 5688.2 | 1.13043 | 119 |
| BX | 2649 | 2569 | 7446 | 1155.2 | 66938.4 | 1 | 688 |
| CH | 4232 | 2909 | 5781.5 | 120 | 86076.3 | 0.769231 | 430 |
| HS | 9266 | 8694 | 5328 | 558.25 | 35248 | 1.1768 | 307 |
| PS | 2192 | 2120 | 3122 | 608 | 19012.6 | 0.956897 | 697 |
| QS | 14019 | 12590 | 4347 | 560.9 | 23436.7 | 1.0122 | 1695 |
| YW | 2215 | 1415 | 658 | 70 | 8165.4 | 1.11538 | 128 |
| ZW | 18949 | 14228 | 1540 | 96 | 13443.6 | 1.02083 | 1060 |

Box crop: x0′=clip(x0−a,0,s), x1′=clip(x1−a,0,s), y도동일. w/h가0인 박스는 유효 라벨로 내보내지 않고 제거 이력을 남긴다. Resize t에서는좌표×t/s. YOLO는마지막에normalized cxcywh,class0..7;COCO1..8;torchvision0배경/1..8;Detectron2contiguous0..7를 분리한다. binary mask는NEAREST 후보이나 저자baseline과의 차이를 명시한다.

## 12. 5시점 상호보완성

| sum | ng_declared_products |
| --- | --- |
| 1 | 3461 |
| 2 | 2702 |
| 3 | 1433 |
| 4 | 2065 |
| 5 | 5981 |

[five_view_within_product_brightness_range.csv](../outputs/preprocessing_review_20261112_v2/review_assets/statistics/five_view_within_product_brightness_range.csv)

[five_view_brightness_correlation.csv](../outputs/preprocessing_review_20261112_v2/review_assets/statistics/five_view_brightness_correlation.csv)

동일 제품의 시점별 밝기 범위와 상관을썼다. 시점별 마스크 제공은 결함이 그시점에 보이지 않는 것과 같지 않다. 위치정답 미제공, 제공빈마스크, 제공양성마스크를 구분한다. 실제 결함 가시성의 독립 육안 정답 전수분석과 3D제품 시점 정합은 NOT_ANALYZED다. 개별입력은 제품분할을 유지하며 제품결합은 누락시점/시점순서/NG전체라벨과 국소라벨 차이를 명시한다.

## 13. 데이터 누수 및 품질 위험

보존Windows seed42 분할에서 선언제품 누수0, 정확한바이트 cross-split중복0이다. 초기hash 탐색split에서는 같은 검은JPG2장이Train/Test로 나뉘었으므로 content audit의cross-split=1을최종split에 그대로 적용하면 틀린다. 두검은영상은현재둘다Train이다. 실제동일물리제품이서로다른serial로등장하는지는UNVERIFIED다. perceptual duplicate도NOT_ANALYZED다.

전검정NG의전영역마스크가위치빈도에큰영향을준다. 원본지표는보존하고 quality_review의제외민감도를함께검토해야한다. 과거146060/50115규모와현재차이는이전Windows checkpoint에서u_block4990/1214추가와일치한다. 제외된역사적이유/최초수치의출처는미확인이다.

## 14. 12개 모델 입력 요구사항

[커밋·파일·함수 근거와 모델별 전체 필드](MODEL_INPUT_REQUIREMENTS.md). 11저장소(두torchvision detector공유)에서12모델후보를조사했다. 모든모델정적자료가있지만실제실행·variant확정·가중치별override는UNVERIFIED다. 확인못한mean/std나보간을모델이름으로추정하지않는다.

## 15. 전처리 전략별 근거와 위험

| 전략 | 목적·근거 | 예상 이점(가설) | 손실 위험 | 권장 비교·확정 범위 |
|---|---|---|---|---|
| 배경 증강 | 배경×품목×시점×라벨 연관 및선택편향 | 배경 shortcut 완화 가능 | 제품 구멍/반사/경계/결함 변경,분할불확실 | 원본대조군→작은제품내부밝기증강→검증마스크기반치환;Train만정책추정,Val/Test원본유지 |
| CenterCrop+Resize | 실제마스크/박스교집합,원본여백 | 남은제품확대·픽셀예산효율 | 완전제거·부분잘림·이중Crop | 전체Resize 대조,896/768/640은후보. 공통크기확정불가 |
| 좌표 adapter | 원본XYXY보존,끝좌표exclusive | 모델별형식분리·재현성 | round오차/scale·padding누락/class remap | crop→clip→제거기록→resize→최종format, mask동일기하 |
| Normalize/dtype | 모델별0..1/0..255 및내부Normalize차이 | 입력contract 일관성 | 이중Normalize/채널역전/FP16수치 | 모델commit/variant고정후dummy+실제소량 adapter검증. 강한전처리없는baseline우선 |

배경 치환이 필요하다는 인과적 근거는 아직 없고 현 분할의 선택 편향만으로 확정하지 않는다. Train증강은정상/불량모두같은정책적용후class조건부편향을검사한다. Crop으로 결함이 사라진NG를정상으로바꾸지 않는다. 학습/평가시Crop의위험허용기준은회의결정이다.

## 16. 모델 실험 전 해결할 사항

①미제공 위치정답의dataset adapter정책 ②검은영상과10경로충돌의정정/보류 ③모델별필수Normalize·Resize·head고정 ④분할과실제물리제품identity보강 ⑤제품정답마스크없는배경치환의검수 ⑥박스/마스크좌표변환 및일부결함제거의학습정책. 모델성능개선을확정하지않는다.

## 17. 데이터 파이프라인 설계에 필요한 결정

원본불변→manifest(has_mask/quality/declared_product/split)→선택적기하(transform행렬·crop·pad이력)→라벨동시변환→모델별색상/범위/정규화/dtype adapter→제품단위평가. raw NG전체와detector-supervised subset을분리하되원래품질라벨을보존한다. 6+6모델의최종선정기준은image/pixel AUROC/AUPRO와class별AP/작은객체recall,운영장치지연/메모리를함께정한다. 이번에학습·지연측정은하지않았다.

## 18. 분석 한계 및 미검증 항목

| 항목 | 상태 | 이유 |
|---|---|---|
| 제공mask CenterCrop 교집합·BBox기하 | VERIFIED | 전수체크포인트/범위/단조성/identity |
| 전경품질통과밝기수치 | VERIFIED | 수치재현·결측정책검사;전체대표성없음 |
| 자동전경정답정확도·미통과실제제품위치 | UNVERIFIED | 수작업정답마스크없음 |
| 300표본제품기하의전체일반화 | UNVERIFIED | 균형대표표본이며추정오차포함 |
| 실제Resize마스크support/연결성전수 | NOT_ANALYZED | 연속면적proxy만계산 |
| Fourier대역고주파·perceptual중복·3D정합 | NOT_ANALYZED | 기존결과없음 |
| 12모델실행·학습성능·속도 | UNVERIFIED | 정적소스만조사 |
| 원본이미지사례외부공유 | UNVERIFIED | 권한미확인으로ZIP제외 |

## 19. 결과 파일과 재현 명령어

[전처리 결정 근거](PREPROCESSING_DECISION_EVIDENCE.csv), [위험 사례](PREPROCESSING_RISK_CASES.md), [분석 인덱스](ANALYSIS_EVIDENCE_INDEX.md). 상세 집계와 검증은 아래 상대 링크로 제공한다. 패키지는 원본/파생 영상사례 없이 통계 PNG만 포함한다.

복구검증/남은체크포인트명령: `uv run --offline python scripts/resume_preprocessing_review.py` (완료마커가있는실행은재실행하지않음). 모델자료는 outputs/model_sources_20261112_v1의commit/sha manifest참조. 보고서/ZIP생성: `uv run --offline python scripts/build_preprocessing_review_package.py` (기존최종산출물이있으면보호중단). 원본CSV해시와추가분석complete.json을함께확인한다.

## 통계 그래프와 해석

### dataset_composition

![dataset_composition](../outputs/preprocessing_review_20261112_v2/review_assets/figures/dataset_composition.png)

전체 이미지와 선언된 5시점 제품 그룹 수를 분리했다. 동일 물리 제품이 다른 serial로 재사용되는지까지 검증한 독립 제품 수는 아니다.

### crop_global

![crop_global](../outputs/preprocessing_review_20261112_v2/review_assets/figures/crop_global.png)

원본 마스크 >0 픽셀의 정확한 교집합이다. 완전 제거는 제공 양성 마스크 이미지 단위이며 실제 물리 결함 수와 다르다. 두 보존율은 픽셀 가중과 이미지 평균으로 분모가 다르다.

### crop_category_view

![crop_category_view](../outputs/preprocessing_review_20261112_v2/review_assets/figures/crop_category_view.png)

품목·시점별 중앙 Crop의 영향이 다르다. 전체 평균이 높아도 일부 위치 정답이 완전히 제거된다. 품목별 표본 수는 연결된 집계 CSV에서 확인한다.

### selection_bias

![selection_bias](../outputs/preprocessing_review_20261112_v2/review_assets/figures/selection_bias.png)

품질 통과는 정답 분할 정확도가 아니다. 통과 집단에서 BLACK 비중이 높으므로 제품 밝기 통계를 전체 영상으로 일반화하면 선택 편향 위험이 있다.

### selection_coverage_reasons

![selection_coverage_reasons](../outputs/preprocessing_review_20261112_v2/review_assets/figures/selection_coverage_reasons.png)

6품목은 통과 영상이0이다. 그림자·반사·유사색과 알고리즘 불일치가 주요 거절 사유다. 사유는 중복되므로 합계가 미통과 수와 같지 않다.

### brightness_paired

![brightness_paired](../outputs/preprocessing_review_20261112_v2/review_assets/figures/brightness_paired.png)

동일 통과 표본의 전체 밝기와 제품 밝기를 비교하여 선택 효과와 영역 제거 효과를 분리한다. 이 그래프의 제품 영역은 자동 추정이며 정답 정확도는 UNVERIFIED다.

### defect_local_and_background

![defect_local_and_background](../outputs/preprocessing_review_20261112_v2/review_assets/figures/defect_local_and_background.png)

국소 대비는 제품 내부 주변이 확보된22,411장에 한한다. 배경 타입은 밝기 경계 후보 기반 자동 예측이며 라벨과의 연관이 배경 원인임을 증명하지 않는다.

### product_geometry

![product_geometry](../outputs/preprocessing_review_20261112_v2/review_assets/figures/product_geometry.png)

미통과 후보 중심은 선택 편향 진단용일 뿐 제품의 실제 중심이 아니다. 제품 보존율·점유율은 통과 표본에 한정하며 전체151,050장에 일반화하지 않는다.

### bbox_geometry_risk

![bbox_geometry_risk](../outputs/preprocessing_review_20261112_v2/review_assets/figures/bbox_geometry_risk.png)

Crop 후 남은 박스가 커져도 이미 사라진 결함은 복구되지 않는다. 제거 박스와 생존 박스의2px 위험을 함께 평가한다. 박스 면적은 실제 결함 픽셀 면적과 다르다.

### resolution_distribution_ssim

![resolution_distribution_ssim](../outputs/preprocessing_review_20261112_v2/review_assets/figures/resolution_distribution_ssim.png)

기존151,050장 해상도 지표의 통계 그래프를 재사용했다. 유효 수·단위는 그래프와 집계표를 참조하며 영상 유사성이 모델 정확도를 의미하지 않는다.

### resolution_distribution_edge_recall

![resolution_distribution_edge_recall](../outputs/preprocessing_review_20261112_v2/review_assets/figures/resolution_distribution_edge_recall.png)

기존151,050장 해상도 지표의 통계 그래프를 재사용했다. 유효 수·단위는 그래프와 집계표를 참조하며 영상 유사성이 모델 정확도를 의미하지 않는다.

### resolution_distribution_edge_f1

![resolution_distribution_edge_f1](../outputs/preprocessing_review_20261112_v2/review_assets/figures/resolution_distribution_edge_f1.png)

기존151,050장 해상도 지표의 통계 그래프를 재사용했다. 유효 수·단위는 그래프와 집계표를 참조하며 영상 유사성이 모델 정확도를 의미하지 않는다.

### resolution_distribution_local_contrast_retention

![resolution_distribution_local_contrast_retention](../outputs/preprocessing_review_20261112_v2/review_assets/figures/resolution_distribution_local_contrast_retention.png)

기존151,050장 해상도 지표의 통계 그래프를 재사용했다. 유효 수·단위는 그래프와 집계표를 참조하며 영상 유사성이 모델 정확도를 의미하지 않는다.

### resolution_distribution_high_frequency_proxy_retention

![resolution_distribution_high_frequency_proxy_retention](../outputs/preprocessing_review_20261112_v2/review_assets/figures/resolution_distribution_high_frequency_proxy_retention.png)

기존151,050장 해상도 지표의 통계 그래프를 재사용했다. 유효 수·단위는 그래프와 집계표를 참조하며 영상 유사성이 모델 정확도를 의미하지 않는다.

### resolution_category_comparison

![resolution_category_comparison](../outputs/preprocessing_review_20261112_v2/review_assets/figures/resolution_category_comparison.png)

기존151,050장 해상도 지표의 통계 그래프를 재사용했다. 유효 수·단위는 그래프와 집계표를 참조하며 영상 유사성이 모델 정확도를 의미하지 않는다.

### resolution_view_comparison

![resolution_view_comparison](../outputs/preprocessing_review_20261112_v2/review_assets/figures/resolution_view_comparison.png)

기존151,050장 해상도 지표의 통계 그래프를 재사용했다. 유효 수·단위는 그래프와 집계표를 참조하며 영상 유사성이 모델 정확도를 의미하지 않는다.

### resolution_status_comparison

![resolution_status_comparison](../outputs/preprocessing_review_20261112_v2/review_assets/figures/resolution_status_comparison.png)

기존151,050장 해상도 지표의 통계 그래프를 재사용했다. 유효 수·단위는 그래프와 집계표를 참조하며 영상 유사성이 모델 정확도를 의미하지 않는다.

## 전체 공유 집계표

- [anonymous_crop_risk_cases.csv](../outputs/preprocessing_review_20261112_v2/review_assets/statistics/anonymous_crop_risk_cases.csv)

- [artifact_inventory_summary.csv](../outputs/preprocessing_review_20261112_v2/review_assets/statistics/artifact_inventory_summary.csv)

- [background_label_crosstab.csv](../outputs/preprocessing_review_20261112_v2/review_assets/statistics/background_label_crosstab.csv)

- [background_stratified_comparison.csv](../outputs/preprocessing_review_20261112_v2/review_assets/statistics/background_stratified_comparison.csv)

- [bbox_category_distribution.csv](../outputs/preprocessing_review_20261112_v2/review_assets/statistics/bbox_category_distribution.csv)

- [bbox_crop_category_view.csv](../outputs/preprocessing_review_20261112_v2/review_assets/statistics/bbox_crop_category_view.csv)

- [bbox_crop_counts.csv](../outputs/preprocessing_review_20261112_v2/review_assets/statistics/bbox_crop_counts.csv)

- [bbox_crop_resize_risk.csv](../outputs/preprocessing_review_20261112_v2/review_assets/statistics/bbox_crop_resize_risk.csv)

- [bbox_defect_distribution.csv](../outputs/preprocessing_review_20261112_v2/review_assets/statistics/bbox_defect_distribution.csv)

- [bbox_projected_size_risk.csv](../outputs/preprocessing_review_20261112_v2/review_assets/statistics/bbox_projected_size_risk.csv)

- [bbox_view_distribution.csv](../outputs/preprocessing_review_20261112_v2/review_assets/statistics/bbox_view_distribution.csv)

- [brightness_interpretation_changes.csv](../outputs/preprocessing_review_20261112_v2/review_assets/statistics/brightness_interpretation_changes.csv)

- [category_statistics.csv](../outputs/preprocessing_review_20261112_v2/review_assets/statistics/category_statistics.csv)

- [category_status_counts.csv](../outputs/preprocessing_review_20261112_v2/review_assets/statistics/category_status_counts.csv)

- [category_view_status_statistics.csv](../outputs/preprocessing_review_20261112_v2/review_assets/statistics/category_view_status_statistics.csv)

- [defect_counts.csv](../outputs/preprocessing_review_20261112_v2/review_assets/statistics/defect_counts.csv)

- [existing_roi_summary.csv](../outputs/preprocessing_review_20261112_v2/review_assets/statistics/existing_roi_summary.csv)

- [five_view_brightness_correlation.csv](../outputs/preprocessing_review_20261112_v2/review_assets/statistics/five_view_brightness_correlation.csv)

- [five_view_within_product_brightness_range.csv](../outputs/preprocessing_review_20261112_v2/review_assets/statistics/five_view_within_product_brightness_range.csv)

- [heatmap_summary.csv](../outputs/preprocessing_review_20261112_v2/review_assets/statistics/heatmap_summary.csv)

- [mask_crop_by_size.csv](../outputs/preprocessing_review_20261112_v2/review_assets/statistics/mask_crop_by_size.csv)

- [mask_crop_category.csv](../outputs/preprocessing_review_20261112_v2/review_assets/statistics/mask_crop_category.csv)

- [mask_crop_defect.csv](../outputs/preprocessing_review_20261112_v2/review_assets/statistics/mask_crop_defect.csv)

- [mask_crop_overall.csv](../outputs/preprocessing_review_20261112_v2/review_assets/statistics/mask_crop_overall.csv)

- [mask_crop_resize_area_proxy.csv](../outputs/preprocessing_review_20261112_v2/review_assets/statistics/mask_crop_resize_area_proxy.csv)

- [mask_crop_view.csv](../outputs/preprocessing_review_20261112_v2/review_assets/statistics/mask_crop_view.csv)

- [output_version_inventory.csv](../outputs/preprocessing_review_20261112_v2/review_assets/statistics/output_version_inventory.csv)

- [overall_statistics.csv](../outputs/preprocessing_review_20261112_v2/review_assets/statistics/overall_statistics.csv)

- [product_geometry_sample_overall.csv](../outputs/preprocessing_review_20261112_v2/review_assets/statistics/product_geometry_sample_overall.csv)

- [product_geometry_summary.csv](../outputs/preprocessing_review_20261112_v2/review_assets/statistics/product_geometry_summary.csv)

- [provided_view_count_per_ng_product.csv](../outputs/preprocessing_review_20261112_v2/review_assets/statistics/provided_view_count_per_ng_product.csv)

- [regional_background_statistics.csv](../outputs/preprocessing_review_20261112_v2/review_assets/statistics/regional_background_statistics.csv)

- [regional_category_statistics.csv](../outputs/preprocessing_review_20261112_v2/review_assets/statistics/regional_category_statistics.csv)

- [regional_global_statistics.csv](../outputs/preprocessing_review_20261112_v2/review_assets/statistics/regional_global_statistics.csv)

- [regional_per_image_percentile_summary.csv](../outputs/preprocessing_review_20261112_v2/review_assets/statistics/regional_per_image_percentile_summary.csv)

- [regional_view_statistics.csv](../outputs/preprocessing_review_20261112_v2/review_assets/statistics/regional_view_statistics.csv)

- [segmentation_category_coverage.csv](../outputs/preprocessing_review_20261112_v2/review_assets/statistics/segmentation_category_coverage.csv)

- [segmentation_selection_brightness.csv](../outputs/preprocessing_review_20261112_v2/review_assets/statistics/segmentation_selection_brightness.csv)

- [selected_evidence_versions.csv](../outputs/preprocessing_review_20261112_v2/review_assets/statistics/selected_evidence_versions.csv)

- [selection_background_type.csv](../outputs/preprocessing_review_20261112_v2/review_assets/statistics/selection_background_type.csv)

- [selection_candidate_diagnostics.csv](../outputs/preprocessing_review_20261112_v2/review_assets/statistics/selection_candidate_diagnostics.csv)

- [selection_category.csv](../outputs/preprocessing_review_20261112_v2/review_assets/statistics/selection_category.csv)

- [selection_failure_reasons.csv](../outputs/preprocessing_review_20261112_v2/review_assets/statistics/selection_failure_reasons.csv)

- [selection_joint_distribution.csv](../outputs/preprocessing_review_20261112_v2/review_assets/statistics/selection_joint_distribution.csv)

- [selection_sample_candidate_geometry.csv](../outputs/preprocessing_review_20261112_v2/review_assets/statistics/selection_sample_candidate_geometry.csv)

- [selection_status.csv](../outputs/preprocessing_review_20261112_v2/review_assets/statistics/selection_status.csv)

- [selection_view.csv](../outputs/preprocessing_review_20261112_v2/review_assets/statistics/selection_view.csv)

- [split_counts.csv](../outputs/preprocessing_review_20261112_v2/review_assets/statistics/split_counts.csv)

- [status_statistics.csv](../outputs/preprocessing_review_20261112_v2/review_assets/statistics/status_statistics.csv)

- [stepwise_distribution.csv](../outputs/preprocessing_review_20261112_v2/review_assets/statistics/stepwise_distribution.csv)

- [strict_selection_sensitivity_comparison.csv](../outputs/preprocessing_review_20261112_v2/review_assets/statistics/strict_selection_sensitivity_comparison.csv)

- [train_normal_only_augmentation_candidates.csv](../outputs/preprocessing_review_20261112_v2/review_assets/statistics/train_normal_only_augmentation_candidates.csv)

- [train_product_augmentation_candidates.csv](../outputs/preprocessing_review_20261112_v2/review_assets/statistics/train_product_augmentation_candidates.csv)

- [view_mask_counts.csv](../outputs/preprocessing_review_20261112_v2/review_assets/statistics/view_mask_counts.csv)

- [view_statistics.csv](../outputs/preprocessing_review_20261112_v2/review_assets/statistics/view_statistics.csv)