# 다음 학습·평가 순서

현재 실행 중인 학습은 이 작업에서 중단하거나 재시작하지 않았다.

## PatchCore

현재: 30/30 품목 메모리뱅크 fit·평가 완료. Gradient 기반 50 epoch 모델이 아님.

다음: 새 학습보다 메모리뱅크·설정·평가 결과 묶음 보존 및 재현 추론을 우선한다.

## EfficientAD-S

현재: 30/30 품목 평가 있음. 20건 EVALUATION_COMPLETED, 10건 EVALUATION_RECOVERED. 모든 품목 50 epoch 완료를 뜻하지 않음.

다음: 회복 평가 10품목과 PCB처럼 짧은 회복 학습을 별도 표시하고 calibration 붕괴 원인을 해결한 뒤 필요한 품목만 새 실험/안전한 checkpoint에서 이어간다.

## UniAD

현재: 50 epoch /95,650 step 체크포인트 존재. EVAL_PAUSED 마커로 평가 중지.

다음: 재학습보다 저장된 가중치의 스트리밍 Validation/Test 평가를 먼저 복구한다. NPY 전체 누적으로 디스크가 다시 차지 않도록 한다.

## HVQ-Trans

현재: 최근 50/50 로그. 이전 exit -11과 watchdog 재시작 반복 이력, 완료 평가 미확인.

다음: 50 epoch 종료 지점의 signal11/저장/평가 전환을 진단하고 가장 최근 유효 checkpoint로 평가부터 검증한다. 50 epoch 전체 반복을 자동 성공으로 세지 않는다.

## Dinomaly

현재: 완료 영수증 47,850 step과 로컬 best 가중치는 있으나 영수증이 가리키는 원격 보고서/가중치 경로가 없어짐. 평가 수치 원본도 이번 조사에서 확보 못함.

다음: 로컬 가중치와 정확한 설정을 먼저 묶고 평가·보고서를 재생성한다. 원본 경로 부재를 학습 실패나 모델 손상으로 단정하지 않는다.

## INP-Former

현재: 확인 시점 완료 영수증 12/30 품목. toy_brick·porcelain_doll 학습 중.

다음: 현재 두 worker를 유지하고 남은 18품목(진행 중2 포함)을 이어간다. 완료 품목을 재학습하지 않고 각 best/설정/평가를 즉시 백업한다.

## Faster R-CNN

현재: v2 약 3번째 epoch /50, 최근 Loss0.0919. 디스크 부족으로 이전 attempt가 중단된 이력이 있음.

다음: 현재 v2 학습을 이어가고 새 체크포인트와 best를 안전하게 수신한다. 이전 v1 class-error 결과를 현재 결과와 섞지 않는다.

## RetinaNet

현재: v2 첫 epoch /50, 최근 Loss0.9505·gradient norm1.77. 재시도 학습 중.

다음: 현재 lr0.0025 설정을 유지한 채 Validation 추이를 관찰하고 원래 발산한 lr0.01 실험과 분리한다. 단기 유한 Loss를 최종 성능으로 해석하지 않는다.

## YOLO11

현재: v2 8~9번째 epoch /50. v1 50 epoch 결과는 class-error superseded로 별도 보존.

다음: 현재 v2 50 epoch를 이어가고 Validation으로 best를 고른다. v1 완료 수치를 최신 모델 최종 성능으로 보고하지 않는다.

## RT-DETRv2

현재: 과거 v1 약7번째 epoch에서 중단. 현재 활성 worker 미확인, v2 runner 대기 목록.

다음: 현재 실행 모델들의 GPU/메모리 여유가 생기면 고정된 v2 클래스/데이터 계약으로 새 실험을 시작한다. v1 가중치의 다른 head를 무조건 이어받지 않는다.

## YOLOS

현재: 과거 v1 약11번째 epoch에서 중단. 현재 활성 worker 미확인, v2 runner 대기 목록.

다음: 현재 v2 대기 순서대로 시작한다. class head가 바뀌는 초기화/재개 조건을 기록하고 v1 결과와 분리한다.

## ViTDet

현재: 과거 v1 약7번째 epoch에서 중단. 현재 활성 worker 미확인, v2 runner 대기 목록.

다음: GPU 여유와 공식 입력 제약을 확인한 뒤 v2 실행을 시작한다. 먼저 256 입력 설정이 공식 baseline과 다른 조건임을 기록한다.


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


최신 권고: 활성 worker가 늘어 VRAM 약44.45GiB를 사용하므로 추가 동시 학습을 시작하지 않는다. RT-DETRv2/YOLOS/ViTDet는 대기보다 **현재 실행 계약 확인**이 우선이다. INP는 완료14품목을 재학습하지 않는다.
