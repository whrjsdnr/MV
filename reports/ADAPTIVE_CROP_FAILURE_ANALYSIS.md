# Adaptive Crop 실패와 미검증 분석

| gate_cohort | positive_masks | raw_A_loss_images | loss_passed | defect_proxy_missed_risk_rate |
| --- | --- | --- | --- | --- |
| calibration | 105 | 0 | 0 | NA |
| development_general | 409 | 0 | 0 | NA |
| development_risk | 103 | 0 | 0 | NA |
| final_holdout | 100 | 0 | 0 | NA |
| retrospective_old_holdout | 103 | 1 | 0 | 0 |
| train_reference | 0 | 0 | 0 | NA |

제품 GT0이므로 위 표는 결함 손실 대리 지표다. 제품 위험 오통과율로 해석하지 않는다. 부분 손실과 제거는 평가용 마스크에서만 확인했다.

| case | category | view | cohort | research_policy | raw_retention | raw_state |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | zipper | C4 | retrospective_old_holdout | C | 0.953162 | partial |
| 2 | audiojack | C1 | final_holdout | A | NA | not_provided |
| 3 | audiojack | C2 | final_holdout | B | NA | not_provided |
| 4 | button_battery | C5 | final_holdout | C | 1 | preserved |
| 5 | audiojack | C1 | calibration | A | NA | not_provided |
| 6 | button_battery | C2 | calibration | B | 1 | preserved |
| 7 | eraser | C2 | calibration | C | NA | not_provided |
| 8 | audiojack | C1 | development_general | A | 1 | preserved |
| 9 | button_battery | C2 | development_general | B | NA | not_provided |
| 10 | button_battery | C2 | development_general | C | 1 | preserved |

GrabCut 중앙90% 초기화로 원본 외곽 돌출 부품이 초기 배경이 될 수 있다. 반복 안정성은 정답성을 보장하지 않고, 여러 전경 방법의 공통 누락은 합의 지표로 감지되지 않을 수 있다. 참조가 품목·시점별 n=3이라 전역 기준을 사용한 것도 편향 위험이다.

현재 정상으로 보이는 Crop에도 제품 일부가 누락됐는지는 사람 GT 검수 전 UNVERIFIED다. 향후 위험 Recall, False Pass Rate와 False Reject Rate를 실제 제품 GT로 별도 계산한다.

[내부 상세 그림](ADAPTIVE_CROP_QUALITY_GATE_REPORT.md), [위험별 집계](../outputs/adaptive_crop_gate_v1/metrics/risk_signal_summary.csv).