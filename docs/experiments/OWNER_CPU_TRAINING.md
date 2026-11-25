# Owner CPU 학습 실행

현재 사용자 설정은 **EfficientAD-S → RetinaNet → YOLO11, CPU, 각 50 epoch, batch size 1**이다.
명령은 `/home/geonug/MV` 프로젝트 루트에서 실행한다. 모델별 실제 코드는 `models/`에 있다.

```bash
uv run --offline python scripts/experiments/run_owner_cpu.py
```

이 명령은 실제 장시간 학습을 시작한다. 이번 개발 검증에서는 전체 50 epoch 학습을 실행하지 않았다.
EfficientAD는 정상 기준을 품목별로 분리하므로 **30개 품목 각각 50 epoch**를 수행한 다음
RetinaNet 50 epoch, YOLO11 50 epoch를 순서대로 수행한다. GPU가 있어도 이 명령은 CPU를 사용한다.
원본과 v2 데이터는 현재 로컬의 `dataset/`, `outputs/team_data_release_v2/MV_TEAM_DATA_RELEASE_v2/`를 읽는다.
다른 PC에서는 `REALIAD_DATA_ROOT`, `MV_DATA_RELEASE` 또는 `--data-root`, `--release-dir`를 지정한다.

## 시작 전 확인 및 복구

```bash
# 데이터·소스·가중치·독립 Python 검사만 수행한다.
uv run --offline python scripts/experiments/run_owner_cpu.py --dry-run

# 공통 실행기만 합성 검증한다. 모델 학습을 대신 검증하지 않는다.
uv run --offline python scripts/experiments/run_owner_cpu.py --smoke

# 터미널에 표시된 Run 디렉터리로 중단 실행을 재개한다.
uv run --offline python scripts/experiments/run_owner_cpu.py --resume outputs/owner_cpu_training/<run_id>
```

`--max-hours 8`을 추가하면 실행 시간 예산을 제한할 수 있다. 완료 전 종료는 INTERRUPTED/PARTIAL이다.
재개 시 설정·데이터·코드·환경 해시가 달라지면 실패한다. 기존 기록을 고쳐 우회하지 말고 새 Run을 만든다.
한 모델의 실패는 로그에 남기고 다음 모델로 진행한다. 실패 모델을 성공으로 표시하지 않는다.
원본, 승인 Ledger, v1/v2 ZIP, 기존 Split에는 쓰지 않는다. Checkpoint와 학습 결과는 Git에 올리지 않는다.

## 구현 위치

|모델|폴더|학습 입력|
|---|---|---|
|EfficientAD-S|`models/anomaly/efficientad_s/`|승인 Crop, 품목별 OK Train, RGB/PIL Resize256/ImageNet Normalize|
|RetinaNet|`models/detection/retinanet/`|원본 D1, RGB float01, 공식 내부 Resize800/Normalize|
|YOLO11|`models/detection/yolo11/`|원본 D1, symlink 이미지/YOLO TXT, 공식 LetterBox640|

각 폴더의 `preprocessing.py`, `dataloader.py`, `backend.py`, `train.py`, `evaluate.py`,
`visualize.py`가 해당 책임을 가진다. 공통 실행 접착 코드는 `models/_shared/`, 순차 실행과
설정·사전검사는 `mv_analysis/training/`에 있다. 공통 데이터·평가기를 복제하지 않는다.

OK의 결함 Target은 빈 목록이다. NG 미주석/빈 마스크는 D1 적격 표에서 제외하며 정상으로 바꾸지 않는다.
TorchVision Target은 canonical 결함 ID에 +1, 평가 예측은 -1을 적용한다. 미사용 0번 슬롯은 결함이 아니다.
YOLO는 canonical 0-based ID를 유지한다. 예측 박스는 원본 XYXY로 평가한다.

## 소스·가중치·학습 조건

소스는 `outputs/owner_sources_v1/`의 별도 Git Clone이다. 설정의 고정 커밋을 변경하지 않았다.

|모델|저장소/고정 Commit|가중치|
|---|---|---|
|EfficientAD-S|nelson1425/EfficientAD `fcab5146f84ae17597044ad5ddf1656ccf805401`|같은 저장소 `models/teacher_small.pth`|
|RetinaNet|pytorch/vision `4260301135e34180d865426765487113f84e7707`|**랜덤 초기화**. 기본 설정은 사전학습을 사용하지 않음|
|YOLO11|ultralytics/ultralytics `d2b7876e79ad2e02fd77221622774b511a8f0cb3`|기존 `outputs/yolo11_dynamic_crop_v1/weights/yolo11n.pt`|

EfficientAD 선택 저장소는 README에 **Unofficial implementation**이라고 명시되어 있다.
Teacher/Student/AE 구조와 손실식을 고정 소스에서 연결했지만 논문 저자 공식 구현이라고 부르지 않는다.
ImageNet penalty 보조 데이터는 이번 조건에서 사용하지 않는다. 소스의 기본 `none` 동작을 따르며,
논문 재현(보조 ImageNet 포함)과 다른 조건이다. Teacher는 고정하고 정상 Train만으로 정규화 통계를 계산한다.
Validation OK의 q90/q99.5를 맵 정규화에 사용하고, OK/NG Threshold 역시 Validation에서 고정한다.

50 epoch는 원본 EfficientAD의 70,000 update 기준과 다르다. StepLR는 전체 예정 update의 95% 지점에서 감소한다.
RetinaNet은 SGD lr0.01, YOLO11도 명시적 SGD lr0.01이다. 자세한 수치는 `configs/training/` JSON을 따른다.
OOM 때 batch를 자동 변경하지 않는다. AMP는 CPU 기본 조건에서 비활성이다.

RetinaNet 실제 런타임은 설치된 TorchVision 0.29.2+cpu이다. 수집한 고정 Git 소스와 설치 wheel의
빌드 커밋은 다르므로 **고정 소스와 런타임의 비트 단위 일치도는 UNVERIFIED**이다.
YOLO11은 수집한 소스로 빌드한 8.4.211을 독립 환경에 설치했다.

## 독립 CPU 환경

각 Python은 `environments/<model_key>/.venv/bin/python`이다. 공통 `.venv`/`uv.lock`은 유지한다.
현재 PC에서는 세 환경을 설치했다. 새 PC에서는 프로젝트 루트에서 다음과 같이 설치한다.

```bash
UV_PROJECT_ENVIRONMENT=environments/efficientad_s/.venv uv sync --locked
UV_PROJECT_ENVIRONMENT=environments/retinanet/.venv uv sync --locked
UV_PROJECT_ENVIRONMENT=environments/yolo11/.venv uv sync --locked
uv pip install --python environments/yolo11/.venv/bin/python --no-deps ./outputs/owner_sources_v1/yolo11
uv pip install --python environments/yolo11/.venv/bin/python --no-deps -r environments/yolo11/extra-requirements.txt
uv pip check --python environments/yolo11/.venv/bin/python
```

소스 폴더가 없다면 먼저 아래 고정 저장소를 받는다. 이미 존재하는 폴더에서 다시 clone하지 않는다.

```bash
git clone https://github.com/nelson1425/EfficientAD.git outputs/owner_sources_v1/efficientad_s
git -C outputs/owner_sources_v1/efficientad_s checkout --detach fcab5146f84ae17597044ad5ddf1656ccf805401
git clone https://github.com/pytorch/vision.git outputs/owner_sources_v1/retinanet
git -C outputs/owner_sources_v1/retinanet checkout --detach 4260301135e34180d865426765487113f84e7707
git clone https://github.com/ultralytics/ultralytics.git outputs/owner_sources_v1/yolo11
git -C outputs/owner_sources_v1/yolo11 checkout --detach d2b7876e79ad2e02fd77221622774b511a8f0cb3
```

기존 YOLO 가중치는 팀 내부로 별도 전달하고 SHA를 확인한다. 모델 코드는 가중치를 자동 다운로드하지 않는다.
RetinaNet 사전학습을 쓰려면 새 Run에서 `initialization=local_checkpoint`와 검증한 로컬
TorchVision RetinaNet state_dict 경로를 지정한다. 분류 마지막 층만 새 8개 결함 공간에 맞게 초기화한다.

## 결과와 확인할 로그

`outputs/owner_cpu_training/<run_id>/state.json`에 모델별 상태가 저장된다.
각 모델의 `attempt_*/worker.log`, `preflight.json`, `response.json`으로 실패 원인을 확인한다.
Torch 모델은 품목 또는 D1 폴더의 `runs/run_*/report.md`, YOLO는 `runs/run_*/report.md`에 보고서를 쓴다.
Loss CSV, Validation/Test metric JSON, 원본 좌표 예측, 실제 예측 PNG, Benchmark, Checkpoint 해시를 함께 기록한다.
CPU 시간은 모델별 실제 실행 범위를 함께 읽는다. RetinaNet 측정에는 내부 Resize/NMS가 포함되며,
YOLO는 network와 LetterBox/NMS를 나누어 측정한다. GPU 비교 결과로 사용하지 않는다.

전체 50 epoch, 전체 품목의 장시간 안정성, 다중 시점 모델 결합, 모델 간 성능 우열은 이번 점검 범위가 아니다.
기존 정책 개발에 사용된 사람 GT의 독립 평가 한계도 그대로 유지한다.
