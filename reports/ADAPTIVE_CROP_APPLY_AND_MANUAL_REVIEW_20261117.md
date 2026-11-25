# 전체 자동 Crop 적용 및 수동 검수 (2026-11-17)

사용자 지시에 따라 자동 후보를 새 CSV에 적용하고 손실·위험 사례만 별도 수동 검수로 분리한다. 기존 수동 승인 좌표가 최우선이며 기존 원본/원장/데이터 ZIP/학습 설정은 변경하지 않는다.

## 적용 규칙

1. 최신 명시적 APPROVED_CROP 좌표 우선. 사람이 확인한 원본 유지도 그대로 둔다.
2. 미승인 이미지는 기존 이미지 기반 Quality Gate의 A(GrabCut90+Margin10%), B(Center896), C(원본 유지) 결정을 적용한다.
3. 기존 연구 제한 min_side=1024를 적용하지 않는 별도 `image_gate+auto-review` 버전이다. 자동 좌표는 사람 승인이나 제품 GT로 표시하지 않는다.
4. GT/마스크는 선택 후에만 감사하고, 손실 관측만으로 자동 좌표를 사후 변경하지 않는다. 사람이 범위를 수정한다.
5. 계산 오류는 원본 유지+오류 상태로 기록하고 최종 검수 목록에도 포함한다.

## 먼저 검수할 13장

검수 화면: **http://127.0.0.1:8773** (실행 중, localhost 전용).

- 필수 검수 13장: 제품 GT BBox 일부 손실 12장 + 이전 보류 1장.
- 추가 검수 권장 33장: 이미지 기반 Gate가 REVIEW인 확대 후보.
- GT BBox 일부 손실은 제품 픽셀 실제 소실과 동일한 지표가 아니므로 원본을 보고 사람이 확인한다.

현재 중간 적용본은 전체151,050행이며 특징2,772장 범위에서 자동 Crop2,181장(A2,148/B33)과 기존 사람 Crop1,587장을 반영했다. 나머지 계산이 끝나지 않은 행은 원본 유지로 표시한다. 중간본을 전수 자동 처리 완료본으로 해석하지 않는다.

[중간 전처리 CSV](../outputs/adaptive_crop_applied_20261117_v1/preview_ready/preprocessing_metadata_applied.csv), [필수 13장 검수 CSV](../outputs/adaptive_crop_applied_20261117_v1/preview_ready/manual_review_required.csv), [권장 검수 33장](../outputs/adaptive_crop_applied_20261117_v1/preview_ready/manual_review_recommended.csv).

검수 방법: 원본과 GT 범위를 확인 → 드래그로 Crop 조정 → 보존 점검 → 검수자/확인 입력 → 승인·저장. 새 검수 원장은 preview_ready/manual_crop_review_ledger.jsonl이며 이전 원장을 수정하지 않는다. '검수 반영한 새 전처리 CSV 만들기'는 새 파일을 내보내며 다른 행의 기존 승인 정보도 보존한다. 전수 최종 생성기는 이 새 원장을 별도 overlay로 읽어 최종 CSV에 반영한다.

## 전수 실행 중

현재 기존2,550장 + 신규 smoke10장은 재사용하고 미계산148,490장을 CPU worker2개로 처리 중이다. 초기 속도 약4장/초, 예상 약10시간에 CSV 생성/사후 감사 시간을 더한 정도다. 실행 부하에 따라 달라진다. 모델 학습·YOLO 재추론·다운로드는 하지 않는다.

실시간 진행률:

```bash
cat outputs/crop_feature_recovery_smoke_20261117_v1/progress.json
cat outputs/adaptive_crop_applied_20261117_v1/pipeline_state.json
```

자동 후속 단계: 전수 특징 추출 완료 → 전체 자동 적용 CSV → 제공 마스크/결함 BBox/제품 GT 사후 감사 → 최종 단일 전처리 CSV+필수/권장 검수 목록+보고서.

완료 시 생성 예정 경로(아직 전수 완료 파일로 사용하지 말 것):

- outputs/adaptive_crop_applied_20261117_v1/full_metadata/preprocessing_metadata_applied.csv
- outputs/adaptive_crop_applied_20261117_v1/full_metadata/manual_review_required.csv
- outputs/adaptive_crop_applied_20261117_v1/full_metadata/manual_review_recommended.csv
- outputs/adaptive_crop_applied_20261117_v1/FULL_ADAPTIVE_CROP_APPLICATION.md

실제 완료 여부는 pipeline_state.json의 COMPLETED_WITH_MANUAL_REVIEW_REQUIRED와 post_crop_audit_validation.json을 확인한다. 예외가 발생하면 FAILED와 traceback을 남긴다. 메타데이터 단계 재시도 경로는 state의 metadata_dir가 기준이다.

## 중단 시 재개

중복 실행은 파일 잠금으로 거부된다. 이미 실행 중이면 아래 명령을 다시 실행하지 않는다.

```bash
# 특징 작업이 실제로 중단됐을 때만 재개
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 uv run --offline python scripts/compute_missing_crop_features.py \
  --output outputs/crop_feature_recovery_smoke_20261117_v1 --workers 2 --resume

# 특징 작업이 끝나거나 별도로 계속 실행 중일 때 후속 자동화를 재개
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 uv run --offline python scripts/run_full_adaptive_crop_recovery.py \
  --output outputs/adaptive_crop_applied_20261117_v1 \
  --features outputs/crop_feature_recovery_smoke_20261117_v1 --wait-features --resume
```

## 검증과 한계

신규 기능 및 기존 Crop/검수 회귀 테스트45개 통과. `/`, `/item/0`, `/image/0` HTTP200과 실제 이미지 바이트를 확인했다. 실제 브라우저 Canvas 표시 검증은 사용자 확인이 필요하다. 실제 승인 요청을 자동으로 보내지 않았다.

제품 GT 없는 이미지의 전체 제품 보존은 UNVERIFIED다. 필수 검수 목록에 없다고 안전이 독립적으로 입증된 것은 아니다. 기존 데이터 ZIP/실행 중 학습의 Manifest는 교체하지 않았으며, 새 CSV를 학습에 사용하면 새 Manifest SHA를 가진 별도 실험으로 기록한다. 객체탐지 v2는 기존 원본 전체 입력 계약을 유지한다.

## 사용자 확인 반영 — 하늘색 제품 박스 재사용

13장 중 저장한 수정3건은 해당 좌표를 유지하고, 나머지10장은 사용자가 하늘색 박스가 잘 맞는다고 확인해 기존 검수 제품 GT에10% 여백을 더한 Crop으로 반영했다. USER_CONFIRMED_REFERENCE_REUSE 상태로 구분하며 승인 원장에 가짜 APPROVED_CROP를 추가하지 않았다. source: user_confirmed_reference_overrides.json. 전수 최종 생성기도 이 명시적 참조 재사용 정책과 새 수동 원장을 읽는다.

현재 반영 중간 CSV: outputs/adaptive_crop_applied_20261117_v1/review_resolved_preview/preprocessing_metadata_final.csv. 마스크 손실0, 제공 제품 GT12장 중10장은 하늘색 기반 범위에 포함된다. 나머지2장은 사용자가 직접 저장한 Crop과 기존 GT BBox에 차이가 있지만, 해당 제품 BBox 손실 경고에 risk_ack=True로 명시적으로 승인한 기록이 있다. 그 차이는 감사 수치에 남기며 같은 손실을 다시 검수하라고 요청하지 않는다. 이후 새로 발견된 다른 종류의 손실까지 묵시적으로 승인한 것으로 취급하지 않는다.
