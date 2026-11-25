# Dinomaly 모델별 종합 보고서
> **최신 상태는 18:03 KST 최종 재확인 절을 우선한다.** 최초 snapshot 이후 INP 14품목 완료, RT-DETRv2·YOLOS·ViTDet 활성화 등 변화가 있다.


확인 시점: 2026-11-19T08:15:59.013736+00:00 (UTC). 원격 학습 상태는 이후 계속 변한다. 이 보고서가 학습이나 Test 평가를 새로 실행한 것은 아니다.

## 현재 상태

**COMPLETION_RECEIPT_ARTIFACTS_INCOMPLETE** — 완료 영수증 47,850 step과 로컬 best 가중치는 있으나 영수증이 가리키는 원격 보고서/가중치 경로가 없어짐. 평가 수치 원본도 이번 조사에서 확보 못함.

## 학습·데이터 조건

원격 주 실험 코호트는 30,000장 /6,000 선언 제품 /30품목이며 Train21,045·Validation4,400·Test4,555이다. 전체151,050장 전수 학습 결과가 아니다. v1/v2는 같은 코호트 경로를 사용해도 Crop/클래스 계약이 다를 수 있다.

정확한 Run 설정 일부는 미확보다. 기존 체크포인트의 파일명만으로 학습 epoch나 공식 입력 설정을 추측하지 않는다.

## 확보된 평가 수치

**N/A — 현재 계약에 맞는 최종 평가 원본을 확보하지 못했다.** 진행 중/중단/영수증만 있는 모델에 성능0이나 성공 판정을 채우지 않는다. 이전 class-error 탐지 수치는 현재 모델 성능에서 제외한다.

## 체크포인트 및 로컬 수신

[전체 체크포인트 대조 CSV](CHECKPOINT_SYNC_STATUS.csv), [로컬 컨테이너 검사](LOCAL_CHECKPOINT_CONTAINER_STATUS.csv)를 참고한다. ZIP 구조 검사는 tensor 값의 유한성이나 full CRC 검사를 뜻하지 않는다. SHA 검증 파일 수는 전체 점검 보고서에 별도 기록한다.

|원격 파일|완료 epoch|step|원격 존재|로컬 동일 이름/크기|
|---|---:|---:|---|---|
|`/workspace/real-iad/outputs/remaining_models_recovery_20261117/job/dinomaly/state_a6b91c11f9f648e8bab22431af754df1.pt`|3|15786|False|False|
|`/workspace/real-iad/outputs/remaining_models_recovery_20261117/job/dinomaly/unified/state_2c7fbb10cebf450691c8614eb24e3b19.pt`|50|47850|False|True|

## 실제 추론 시연

NOT_EXECUTED — 이 모델의 실제 추론 예시는 이번 작업에서 실행하지 않았다. 공통 CLI의 모델 이름 지원과 실제 런타임 검증은 다르다.

## 다음 학습·평가 작업

로컬 가중치와 정확한 설정을 먼저 묶고 평가·보고서를 재생성한다. 원본 경로 부재를 학습 실패나 모델 손상으로 단정하지 않는다.

## 근거 및 한계

- [원격 초기 snapshot](../../outputs/remote_training_audit_20261119_v1/remote_snapshot.json) / [원격 후속 점검](../../outputs/remote_training_audit_20261119_v1/remote_final.json) / [설정·평가 수집](../../outputs/remote_training_audit_20261119_v1/report_inputs.json)
- [품목별 수치 CSV](MODEL_METRICS.csv) / [시점별 원본 집계](VIEW_METRICS.csv)
- 기존 체크포인트/학습/원본/승인 기록은 변경하지 않았다. GPU benchmark와 전체 재평가는 NOT_EXECUTED다.