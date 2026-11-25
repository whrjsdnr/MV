# Adaptive Crop 정책 판단

판정: INCONCLUSIVE. 사람 제품 GT와 팀 허용치가 없어 전체 적용 미승인.

| method | positive_masks | retention | removed | partial | side_mean | magnification_mean |
| --- | --- | --- | --- | --- | --- | --- |
| fixed_full | 100 | 1 | 0 | 0 | 1024 | 1 |
| fixed_center896 | 100 | 1 | 0 | 0 | 896 | 1.14286 |
| fixed_grabcut10 | 100 | 1 | 0 | 0 | 884.117 | 1.17238 |
| research_risk_full | 100 | 1 | 0 | 0 | 906.823 | 1.14365 |
| research_review_center | 100 | 1 | 0 | 0 | 901.703 | 1.14936 |
| research_validated_scope | 100 | 1 | 0 | 0 | 1024 | 1 |
| deployment_default | 100 | 1 | 0 | 0 | 1024 | 1 |

| method | A_rate | B_rate | C_rate | full_frame_rate |
| --- | --- | --- | --- | --- |
| fixed_full | 0 | 0 | 1 | 1 |
| fixed_center896 | 0 | 1 | 0 | 0 |
| fixed_grabcut10 | 0.99 | 0 | 0.01 | 0.12 |
| research_risk_full | 0.833333 | 0 | 0.166667 | 0.246667 |
| research_review_center | 0.833333 | 0.04 | 0.126667 | 0.206667 |
| research_validated_scope | 0 | 0 | 1 | 1 |
| deployment_default | 0 | 0 | 1 | 1 |

신규 Final300장 결과다. 제품 보존율·제품 위험 오통과율은 UNVERIFIED. Deployment C100%는 확대 효과가0이고 연구 제안과 구분한다. 원본 전체151050장 Crop은 수행하지 않았다.

우선순위:600제품BBox 사람 검수 → 위험 오통과 검증 → 팀 손실 기준 결정 → 새 Calibration/Final 평가 → 품목·시점별 적용 범위 승인. 이후 실제12모델 성능은 별도 실험.

[상세 보고서](ADAPTIVE_CROP_QUALITY_GATE_REPORT.md), [수치](../outputs/adaptive_crop_gate_v1/metrics/policy_summary.csv).