# HVQ-Trans 모델별 종합 보고서
> **최신 상태는 18:03 KST 최종 재확인 절을 우선한다.** 최초 snapshot 이후 INP 14품목 완료, RT-DETRv2·YOLOS·ViTDet 활성화 등 변화가 있다.


확인 시점: 2026-11-19T08:15:59.013736+00:00 (UTC). 원격 학습 상태는 이후 계속 변한다. 이 보고서가 학습이나 Test 평가를 새로 실행한 것은 아니다.

## 현재 상태

**TRAINING_OR_END_OF_TRAINING_RETRY** — 최신48/50 재시작 로그,22,801/23,950iter. 이전50/50 로그는 최종 완료 증거가 아님. 이전 exit -11과 watchdog 재시작 반복 이력, 완료 평가 미확인.

## 학습·데이터 조건

원격 주 실험 코호트는 30,000장 /6,000 선언 제품 /30품목이며 Train21,045·Validation4,400·Test4,555이다. 전체151,050장 전수 학습 결과가 아니다. v1/v2는 같은 코호트 경로를 사용해도 Crop/클래스 계약이 다를 수 있다.

정확한 Run 설정 일부는 미확보다. 기존 체크포인트의 파일명만으로 학습 epoch나 공식 입력 설정을 추측하지 않는다.

## 확보된 평가 수치

**N/A — 현재 계약에 맞는 최종 평가 원본을 확보하지 못했다.** 진행 중/중단/영수증만 있는 모델에 성능0이나 성공 판정을 채우지 않는다. 이전 class-error 탐지 수치는 현재 모델 성능에서 제외한다.

## 체크포인트 및 로컬 수신

[전체 체크포인트 대조 CSV](CHECKPOINT_SYNC_STATUS.csv), [로컬 컨테이너 검사](LOCAL_CHECKPOINT_CONTAINER_STATUS.csv)를 참고한다. ZIP 구조 검사는 tensor 값의 유한성이나 full CRC 검사를 뜻하지 않는다. SHA 검증 파일 수는 전체 점검 보고서에 별도 기록한다.

전용 체크포인트 참조를 이번 snapshot에서 확보하지 못했거나 이미 offload되어 원본 참조가 남아 있지 않다. 해당 상태를 가중치 부재로 단정하지 않는다.

## 실제 추론 시연

NOT_EXECUTED — 이 모델의 실제 추론 예시는 이번 작업에서 실행하지 않았다. 공통 CLI의 모델 이름 지원과 실제 런타임 검증은 다르다.

## 다음 학습·평가 작업

50 epoch 종료 지점의 signal11/저장/평가 전환을 진단하고 가장 최근 유효 checkpoint로 평가부터 검증한다. 50 epoch 전체 반복을 자동 성공으로 세지 않는다.

## 근거 및 한계

- [원격 초기 snapshot](../../outputs/remote_training_audit_20261119_v1/remote_snapshot.json) / [원격 후속 점검](../../outputs/remote_training_audit_20261119_v1/remote_final.json) / [설정·평가 수집](../../outputs/remote_training_audit_20261119_v1/report_inputs.json)
- [품목별 수치 CSV](MODEL_METRICS.csv) / [시점별 원본 집계](VIEW_METRICS.csv)
- 기존 체크포인트/학습/원본/승인 기록은 변경하지 않았다. GPU benchmark와 전체 재평가는 NOT_EXECUTED다.

## 최종 재확인 — 2026-11-19 18:03 KST

최초 17:10~17:16 점검 이후에도 학습·수신 상태가 변했다. 아래 상태가 앞선 snapshot 설명보다 우선한다. [최신 원격 원본](../../outputs/remote_training_audit_20261119_v1/remote_refresh.json).

- 18:02 KST: A6000 GPU 99%, VRAM 45,517/49,140 MiB, 디스크 여유 약54GB. 추가 학습 worker가 기존 자동 실행기에 의해 시작됐다. 이 점검에서 시작한 작업이 아니다.
- INP-Former 완료 영수증 **14/30품목**. toy_brick·porcelain_doll도 완료했으며 현재 transistor1·regulator를 학습 중이다. 나머지16품목에는 현재 진행 중2품목이 포함된다. 로컬에서 확보한 품목별 평가 수치는 이보다 앞선 **13품목**이다.
- YOLO11 v2 저장 checkpoint **11 epoch,57,882step**. Faster R-CNN v2 **완료 epoch2,14,200step(3번째 epoch 진행)**. RetinaNet v2 **완료 epoch1,6,900step(2번째 epoch 진행)**. 진행 중 step과 완료 epoch는 구분한다.
- RT-DETRv2·YOLOS·ViTDet worker가 새로 활성화됐다. 실행 request가 snapshot 코드와 job 경로를 사용하므로 이전 v1과 동일한 클래스인지, 수정 계약인지 추가 확인 전 **클래스 계약 UNVERIFIED**다. 단순히 모두 v2로 바뀌었다고 해석하지 않는다.
- HVQ-Trans는 재시작 후 **48/50,22,801/23,950iter** 로그다. 앞서50/50로그가 있어도 최종 완료 영수증/평가가 없으며 반복 재실행 이력이 있다.
- 최초 점검 이후 로컬 INP toy_brick metrics가17:35에 추가 수신된 것도 확인했다. 따라서 최초 수신 시각16:48/프로세스 부재만으로 현재 동기화가 계속 멈췄다고 단정할 수 없다. 다만 export/offload큐에 포함되지 않은 활성 checkpoint의 자동 보존은 여전히 보장되지 않는다.

### 확인한 SHA256 범위

참조·export manifest 기반 **55건 / 고유 파일55개 / 불일치0건**이다. 이 범위의 해시는 일치한다. 별도 구조 검사에서 확인한 손상3개 파일은 이 검증 집합 밖에 있으며, 전체416개가 모두 정상이라는 뜻이 아니다.
