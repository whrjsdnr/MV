# 실제 체크포인트 추론 사용법 및 시연

추론 코드는 `scripts/inference/run_checkpoint.py`다. 학습·calibration·다운로드 없이 저장된 checkpoint를 검증하고 추론한다. 출력 디렉터리는 새 경로만 허용한다.

## 실제 실행 결과

|모델|표본|관측 결과|
|---|---:|---|
|EfficientAD-S|Validation 2장|NG 탐지1, OK를 NG로 오탐1. Validation threshold 0.0539252795 사용|
|YOLO11|Validation 2장|NG는 결함 객체, OK는 정상 제품 객체가 표시됨|
|Faster R-CNN|Validation 2장|NG에서도 정상 제품 객체만 표시됨. 결함 미검출 사례|
|RetinaNet|Validation 2장|confidence0.25 이상 검출 없음. 정상으로 확정하지 않음|

시각 검수에서 YOLO의 audiojack NG에 `vcpill/AK`, OK에 `phone_battery/OK`가 표시되는 **제품/클래스 혼동**도 관찰했다. OK/NG 후보가 맞아도 클래스까지 정답인 것은 아니다.

이는 최종 평가나 모델 순위가 아니다. 학습 중 checkpoint와 완료 best가 섞여 있고 각2장만 관찰했다. 추론 시간에는 첫 호출 초기화 영향이 있어 정식 latency benchmark로 사용하지 않는다.

![실제 모델 추론 8장](../../outputs/remote_training_audit_20261119_v1/inference_preview/ACTUAL_INFERENCE_CONTACT_SHEET.jpg)

## 재현 명령

현재 실제 실행은 원격의 기존 GPU 가상환경에서 **CPU1thread**로 했다. 로컬에는 동일 remote snapshot과 모델 환경 전체가 설치되지 않아 동일 실행은 UNVERIFIED다. `--code-root`는 가중치를 만든 실제 소스를 가리켜야 한다. 12모델 이름을 지원하지만 실행 검증은 위4종만 완료했다.

```bash
cd /workspace/real-iad
.venv-gpu/bin/python outputs/inference_audit_20261119/run_checkpoint.py \
  --code-root outputs/efficientad_s_recovery_20261117/snapshot_v2 \
  --request outputs/remaining_models_recovery_20261117/job_v2/yolo11/requests/attempt_2.json \
  --checkpoint-reference outputs/remaining_models_recovery_20261117/job_v2/yolo11/checkpoint_latest.json \
  --output outputs/inference_audit_20261119/yolo11_cpu_new_run \
  --device cpu --threads 1 --split validation --samples 2
```

latest 참조는 시간이 지나면 바뀐다. 각 실행의 `config.json`에 고정된 파일 SHA256·실행 request·snapshot을 보존했다. 동일 시연 재현은 해당 checkpoint와 해시를 `--checkpoint` 및 `--checkpoint-sha256`으로 지정한다. checkpoint가 이동/삭제됐으면 정상적으로 실패하며 다른 가중치를 대신 쓰지 않는다.

탐지 모델은 `--image /path/image.jpg`로 새 이미지1장도 받을 수 있다. 이 경우에도 release의 클래스 매핑/모델 생성 정보가 필요하다. 이상탐지는 승인 Crop 메타데이터를 사용하므로 외부 이미지 단독 입력을 허용하지 않고 `--image-id`를 사용한다.

## 산출물과 해석

- `summary.json`: 이미지별 점수·표시 판정·추론 시간·실제 가중치 해시.
- `predictions.json`: 원본 좌표 XYXY·클래스 ID·confidence 또는 anomaly score/map 경로.
- `*_prediction.png`: 원본에 탐지 박스 또는 이상 heatmap overlay.
- 이상탐지 `*_score_map.npy`와 `*_observed.npy`: 원본 좌표 heatmap 및 유효 Crop 영역. 관측 밖은 평가에서 제외한다.
- `validation.json`: 실행 성공 여부. `COMPLETED_INFERENCE_ONLY`는 학습 완료가 아니다.
- 탐지0.25는 **표시 기준**이며 Validation에서 정한 최종 판정 기준이 아니다. 현재141클래스에는 `/OK` 객체가 있다. 무검출은 `NO_DETECTION_UNCERTAIN`이다.
- heatmap P01/P99 색상 확대는 시각화에만 사용하며 anomaly score/판정 threshold를 변경하지 않는다.

## 검증 범위

추론 유틸 회귀 테스트8개 통과. 실제4모델×2장=8장 추론 성공. 나머지8모델 실제 runtime·GPU 속도·대규모 최종 성능은 미검증이다. 기존 학습·원본·체크포인트·split은 수정하지 않았다.