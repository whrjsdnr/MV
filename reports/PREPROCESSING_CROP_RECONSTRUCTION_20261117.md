# 전처리 Crop CSV 전수 재구성 및 적용 상태 (2026-11-17)

## 결론

수동 검수 좌표는 누락되지 않았다. 최신 Crop 원장 1,641개 이력 → 최신 1,595개 항목 중 APPROVED_CROP 1,594건을 대조했다. reviewed_v1은 재검수 전 43건이 달랐고 reviewed_v2·팀 배포 v2·이번 재구성 최종 CSV는 최신 승인과 불일치 0건이다. 실제 축소 Crop 1,587장과 사람이 확인한 원본 유지 7장을 구분한다.

반면 전체 자동 적응형 Crop은 이전 작업에서 수행되지 않았다. 기존 generate_full_crop_manifest.py는 production_mode=FULL_FRAME_UNVERIFIED_SCOPES, approved_scopes={}를 assert하고 crop=[0,0,width,height]를 무조건 저장한다. 이는 전수 좌표 생성 완료이며 전수 GrabCut/YOLO 실행 완료가 아니다. 기존 보고의 '전체 좌표 생성'을 '전체 적응형 Crop 완료'로 해석하면 안 된다.

## 지금 사용할 파일

- [preprocessing_metadata_final.csv](../outputs/preprocessing_reconstructed_20261117_v1/preprocessing_metadata_final.csv): 전체 151,050행, 최신 사람이 승인한 Crop 좌표를 우선 적용한 재구성 파일. 실험 후보를 승인으로 승격하지 않는다.
- [자동 후보 적용 비교 CSV](../outputs/preprocessing_reconstructed_20261117_v1/preprocessing_metadata_cached_adaptive_candidate.csv): 전체 151,050행이지만 캐시가 있는 미검수 이미지 중 추가 1,499장에 AUTO_CACHED_B 적용. 제품 보존 UNVERIFIED인 비교용이며 학습용 확정 파일로 권장하지 않는다.
- [수동 검토·미계산 이미지](../outputs/preprocessing_reconstructed_20261117_v1/manual_review_or_uncomputed_images.csv): 승인 미완료 149,456행. NOT_COMPUTED는 미평가이며 확정 실패가 아니다. 기존 검수 서버의 queue schema와 다른 조사용 목록이다.
- [우선 검토 1장](../outputs/preprocessing_reconstructed_20261117_v1/manual_review_priority.csv): 자동 후보에서 사람 제품 GT가 잘린 사례.

원본 좌표 XYXY, x1/y1은 exclusive다. crop_x0/crop_y0/crop_x1/crop_y1을 그대로 사용한다. 추가 CenterCrop을 자동 적용하지 않는다. 이 새 CSV는 독립 파일이며 기존 v2 ZIP 내부 canonical이나 학습 설정을 교체하지 않았다. 기존 실행의 Manifest SHA와 비교 조건을 유지한다.

## YOLO·적응형·수동 기록 연결

|자료|실제 범위|새 파일에서의 의미|
|---|---:|---|
|YOLO11 저장 추론|1,350장|검출 및 30% margin 후보를 별도 yolo_crop_candidates.csv에 보존. 원본 stat 일치 확인. COCO bbox를 검증된 제품 GT로 간주하지 않음|
|기존 Quality Gate 특징|2,550장|현재 원본 SHA256 일치 확인 후 기존 고정 정책 재사용|
|기존 자동 특징 미계산|148,500장|NOT_COMPUTED, 원본 유지. 정상 Gate PASS로 표시하지 않음|
|최신 Crop 승인|1,594장|1,587장 Crop, 7장 전체 유지. 자동 후보보다 우선|
|제품 GT|600장|Crop 승인과 별개. 원장 변경 없이 사후 평가에만 사용|
|43장 재검수|43장|reviewed_v2·배포 canonical·이번 최종 CSV 모두 최신 원장과 일치|

기존 고정 policy.json의 research_candidate는 min1024_proxy1이다. GrabCut A 후보의 crop_side<1024이면 Center896 안전성 검사 B 또는 원본 C로 전환한다. 따라서 캐시를 재연결해도 대부분의 실제 확대 후보는 GrabCut이 아닌 B다. 사용자 의도인 전체 이미지별 GrabCut 적응형 확대가 이미 끝났다고 볼 근거는 없다. 이번 재구성은 이 정책을 임의 완화하지 않았다.

## 자동 후보 사후 감사

비교 CSV에서 새로 바뀐 1,499장을 감사했다. 제공된 양성 마스크 470장의 픽셀 가중 보존율 100%, 일부/완전 소실 0장, 결함 BBox Clip/제거 0개다. 그러나 사람 제품 GT가 있는 379장 중 1장에서 제품 BBox 일부가 잘렸다. 해당 이미지는 vcpill/OK/S0451/vcpill_0451_OK_C2_20230921094244.jpg다. 마스크가 없는 정상 이미지이므로 결함 마스크 보존 지표만으로는 이 실패가 드러나지 않는다.

이 결과로 자동 후보를 전체 적용 안전으로 판정하지 않는다. 사후 GT를 보고 자동 좌표를 고치지 않았다. 기존 승인 원장에도 새 승인을 쓰지 않았다. 미검수 범위 제품 보존은 UNVERIFIED다.

[후보 손실 감사 JSON](../outputs/preprocessing_reconstructed_20261117_v1/automatic_candidate_loss_audit.json), [행별 감사 CSV](../outputs/preprocessing_reconstructed_20261117_v1/automatic_candidate_loss_audit.csv), [승인 버전 비교](../outputs/preprocessing_reconstructed_20261117_v1/approval_version_comparison.csv).

## 구현 및 검증

추가 코드: mv_analysis/crop_reconstruction.py, scripts/rebuild_preprocessing_metadata.py, scripts/compute_missing_crop_features.py, scripts/audit_rebuilt_crop_candidates.py, tests/test_crop_reconstruction.py.

전체 151,050행 ID/경로 중복·정수 좌표·범위·전체 프레임 플래그·30,210개 선언 제품의 C1~C5·Split 누수를 검사했다. 누락 원본 0, 좌표 오류 0, 승인 불일치 0이다. 기존 입력 CSV·원장·정책·캐시 해시는 전후 동일하다. 전체 JPG를 다시 디코딩한 검사는 아니며 각 CSV에서 30품목 대표와 수동/자동 사례의 실제 Crop 로딩을 별도로 수행했다. 자세한 표본 수는 geometry_and_loading_validation.json을 참조한다.

재계산 도구는 신규 8장 처리 후 --resume으로 다음 2장을 처리했다. 성공 10장, 오류 0, 중복 처리 0이며 실제 Crop 이미지 파일은 생성하지 않았다. 새 10장은 smoke 캐시에만 있고 이번 최종 CSV에 적용하지 않았다. 기존 148,500장 미계산 중 현재 신규 smoke 10장을 제외한 미계산은 148,490장이다. 전체 완료로 보고하지 않는다.

## 다음 전수 처리의 실제 범위와 비용

현재 부하에서 6장 기존 특징 추출 평균 약 0.86초/장, 8장 smoke는 5.83초, resume 2장은 2.75초다. 단일 worker 전수는 약 30~57시간 수준의 관측 환산이며 보장값이 아니다. CPU 사용량·동시 학습 부하에 따라 달라진다. 현재 실행 중인 다른 학습을 중단하지 않았으며 장시간 전수 처리는 자동 시작하지 않았다.

기존 frozen 정책으로 미계산 특징을 채우는 작업과, GrabCut A 정책을 다시 선택·검증하는 작업은 다르다. 특징만 채워도 기존 min_side=1024 조건은 남는다. 실제 전체 확대 정책을 사용하려면 사람 검수 우선순위 유지, 제품 손실 허용 기준, 독립 검증과 적용 범위 결정이 필요하다. GT/결함 마스크로 개별 자동 좌표를 사후 선택하는 정책은 만들지 않는다.

## 재현 명령

```bash
# 현재 증거만 재구성. 출력 디렉터리는 반드시 새 경로로 지정한다.
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 uv run --offline python scripts/rebuild_preprocessing_metadata.py \
  --output outputs/preprocessing_reconstructed_new

# 미계산 특징을 소량 생성. 기본 worker=1, 원본 변경 및 Crop 이미지 저장 없음.
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 uv run --offline python scripts/compute_missing_crop_features.py \
  --output outputs/crop_feature_recovery_new --workers 1 --max-new-images 10

# 동일 캐시에서 다음 10장만 이어서 처리한다. --max-new-images를 생략하면 나머지 전수 장시간 실행.
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 uv run --offline python scripts/compute_missing_crop_features.py \
  --output outputs/crop_feature_recovery_new --workers 1 --max-new-images 10 --resume

# 추가 특징을 연결해 또 다른 새 CSV를 만든다. 기존 결과를 덮어쓰지 않는다.
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 uv run --offline python scripts/rebuild_preprocessing_metadata.py \
  --additional-features outputs/crop_feature_recovery_new --output outputs/preprocessing_reconstructed_with_more_features

# 후보 사후 감사(원본 마스크는 선택 입력으로 사용하지 않는다).
uv run --offline python scripts/audit_rebuilt_crop_candidates.py --directory outputs/preprocessing_reconstructed_new
```

전처리 자체는 다음처럼 수행한다. 크기 1024를 하드코딩하지 않고 각 행을 사용한다.

```python
from mv_analysis.crop_manifest import iter_metadata, load_crop_rgb
for row in iter_metadata('outputs/preprocessing_reconstructed_20261117_v1/preprocessing_metadata_final.csv'):
    rgb = load_crop_rgb(row, data_root='dataset')
    # rgb는 해당 행의 승인 Crop 또는 원본 유지 영역. 이후 모델별 Resize/Normalize.
```

현재 v2 계약의 객체탐지 D1/D2는 원본 전체를 유지한다. 이 CSV는 이상탐지 Crop/공통 원본 좌표 참조용이며 객체탐지에 임의로 Crop을 추가하는 변경이 아니다.

## 완료와 미완료

- VERIFIED: 모든 기존 증거 대조, 최신 수동 승인·43장 반영 확인, 151,050행 최종 재구성, 별도 자동 비교 CSV, 후보 손실 감사, 좌표·그룹·원본 존재 검사.
- VERIFIED: 기존 2,550장 특징/1,350장 YOLO 결과 재사용, 신규 특징 10장과 resume smoke.
- NOT_COMPUTED: 나머지 148,490장 신규 Gate 특징 추출.
- UNVERIFIED: 미검수 전체의 제품 보존, 기존 정책을 넘어서는 전체 적응형 확대의 안전성.
- NOT_EXECUTED: 전체 자동 Crop 이미지 생성, 모델 학습, 기존 ZIP/Manifest 교체, Git Commit/Push.

## 최종 검증 요약

신규 회귀 및 기존 Crop 기하 테스트 29 passed / 0 failed. 재구성 최종 CSV 실제 34장, 자동 후보 CSV 실제 39장을 로딩하여 원본 지문·Crop 크기를 확인했다. 보호 입력 해시 재검사 불일치 0건이다. 전체 pytest는 이번 CSV 재구성 작업에서 재실행하지 않았다. 출력 CSV별 SHA256은 SHA256SUMS와 final_delivery_validation.json에 기록했다.
