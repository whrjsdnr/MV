# 공통 순차 실행기 사용법 — 학습 연결 전 단계

## Owner CPU 학습 Backend (2026-11-13)

Owner 모델은 `models/`에 구현했다. CPU, 50 epoch, batch 1 설정과 실행 명령은
[OWNER_CPU_TRAINING.md](OWNER_CPU_TRAINING.md)를 따른다.
아래 기존 기록의 «Backend 미구현»은 이전 실행기-only 단계 기록이다.
Teammate 3개 Backend는 여전히 미구현이다. 전체 50 epoch 학습은 이번 개발에서 실행하지 않았다.

현재 구현 범위는 설정·사전 점검·하위 프로세스·상태·재개 계약이다.
**실제 6개 모델의 학습 백엔드는 아직 없다.** `--smoke`는 공식 모델을 만들거나
학습하지 않는다. [진행 현황](TRAINING_IMPLEMENTATION_PROGRESS.md)을 먼저 확인한다.

## 담당자와 설정

|프로필|순차 실행 순서|입력 계약|
|---|---|---|
|owner|efficientad_s → retinanet → yolo11|이상탐지 승인 Crop / 탐지 원본 전체 D1|
|teammate|rtdetrv2 → uniad → hvq_trans|탐지 원본 전체 D1 / 이상탐지 승인 Crop|

설정은 `configs/training/<모델키>.json`에서 읽는다. 기존 초안 값을 보존했으며
실제 GPU 학습으로 검증된 권장 설정은 아니다. 프로필을 복사해 수정할 필요 없이
`--models retinanet yolo11`처럼 일부 모델을 명시할 수 있다. 중복 모델과
프로필/목록의 동시 지정은 거부한다.

수정할 설정만 별도 JSON에 작성하고 `--config /경로/settings.json`을 전달한다.
다음 예시는 RetinaNet만 선택할 때 사용한다. 명시하지 않은 필드는 기본 JSON을 따른다.

```json
{"retinanet": {"batch_size": 2, "epochs": 26}}
```

알 수 없는 필드·중복 JSON 키·NaN/Infinity·잘못된 자료형·음수 수치를 거부한다.
이상탐지는 `approved_crop`, 탐지는 `original_full`로 고정된다. D1은 기본
`annotation_policy=defect_only`, D2는 명시적 `product_and_defect` 설정이며
실제 D1/D2 학습은 모두 다음 단계에서 연결해야 한다.

## CPU에서 실행기 점검

모든 명령은 MV 저장소 루트에서 실행한다. 현재 설치된 공통 환경을 사용한다.

```bash
uv run --offline python scripts/experiments/run_weekend.py --help
uv run --offline python scripts/experiments/run_weekend.py --profile owner --smoke
uv run --offline python scripts/experiments/run_weekend.py --profile teammate --smoke
uv run --offline pytest -q tests/test_training_runner.py
```

`--help`는 실제 지원 옵션을 보여준다. `--smoke`는 프로필 순서대로 별도 Python
프로세스를 띄워 CPU 텐서 연산, Recorder, 합성 Checkpoint 등록·검증, Markdown
보고서를 확인한다. 모델별 Python 경로가 없으면 **합성 검사에 한해** 현재 공통
Python을 사용하고 `SHARED_ENV_SYNTHETIC_ONLY`를 plan에 기록한다.
사용자가 `MV_PYTHON_*`를 명시했는데 경로가 틀리면 자동 대체하지 않는다.

성공 시 `SMOKE_PASSED`, 종료 코드 0을 표시한다. Recorder는 `SYNTHETIC`,
`PARTIAL`, `training_executed=false`를 유지한다. 이 결과는 공식 모델 forward,
backward, 학습, GPU 검증을 의미하지 않는다. Smoke는 CPU 전용이며 CUDA 지정은 거부한다.
실패 시 출력된 Run 경로의 상태·시도별 로그를 확인한다. 패키지를 자동 설치하지 않는다.

## v2 데이터와 실행 환경 사전 점검

팀 내부에서 받은 v2 ZIP을 이미 해제했다면 디렉터리를 사용한다.

```bash
export REALIAD_DATA_ROOT="/본인/Real-IAD/루트"
export MV_DATA_RELEASE="/본인/MV_TEAM_DATA_RELEASE_v2"
uv run --offline python scripts/experiments/run_weekend.py --profile teammate --dry-run
```

환경변수 대신 `--data-root`, `--release-dir`로 지정할 수 있다. ZIP도 직접 검사한다.

```bash
uv run --offline python scripts/experiments/run_weekend.py \
  --profile teammate --dry-run \
  --release-dir /받은경로/MV_TEAM_DATA_RELEASE_v2.zip \
  --release-sha256 39acd673b0042e5b626a8e84fa25f0d1190db02b56f6f1dded4b5c8886dada43 \
  --data-root /본인/Real-IAD/루트
```

위 SHA는 현재 프로젝트의 v2 ZIP이다. 다른 ZIP은 관리자가 별도로 전달한 SHA와
대조해야 한다. 해시는 서명이 아니다. ZIP은 안전 검사 후 임시 폴더에서만 해제하며
기존 배포 폴더를 수정하지 않는다. v1 ZIP은 거부한다.

검사 범위:

- ZIP CRC, 모든 배포 파일 SHA, 정확한 파일 집합, 경로 탈출 방지.
- 기존 v2 검증기를 통한 전수 Manifest·적격 표·클래스·참조·좌표·Split·5시점 계약.
- 원본 루트에서 **품목별 한 장의 파일 존재/읽기 권한** 검사.
- 모델별 Python 실행, 실제 torch import/CPU 연산, 설치 버전, CUDA 가용성, CPU/RAM, 디스크.
- 고정 공식 소스 Commit/스냅샷 해시, 지정한 로컬 가중치 존재/해시.

이 사전 점검은 원본 이미지의 전수 디코딩을 다시 하지 않는다. 파일 존재 검사와
디코딩 검증을 혼동하지 않는다. 모델별 Python 환경은
[환경 인터페이스](../../environments/README.md)를 따른다.

현재 `--dry-run`은 세 모델 모두 점검한 뒤 `TRAIN_BACKEND_NOT_IMPLEMENTED`로
`BLOCKED`(종료 코드 2)를 반환한다. 모델 환경이나 가중치도 없으면 각각의 이유가
함께 기록된다. 이것은 학습 준비 완료가 아니라 **미구현 부분을 탐지한 결과**다.
`--device auto`는 선택한 모델 Python에서 CUDA를 조사한다. CUDA를 명시했는데
없으면 CPU로 조용히 변경하지 않는다.

## 결과와 오류 찾기

기본 저장 위치는 `outputs/weekend_runs/weekend_<UTC>_<UUID>/`이다.
같은 명령을 반복해도 다른 Run을 만든다. `--output-root`로 변경할 수 있지만
원본 데이터/배포 폴더 안에는 생성할 수 없다.

```text
plan.json                       # 프로필·모델 설정·Python 경로·코드 지문, 불변
state.json                      # 현재 상태, 모델별 시도, 데이터/환경 지문
events.jsonl                    # 시작·중단·실패·재개 사건을 추가 기록
release_check_<UUID>.json        # 실제 v2 검증 결과, 이전 점검도 보존
retinanet/
  attempt_<UUID>/
    preflight.json
    request.json                # worker 호출 시 생성
    command.json
    worker.log
    worker_lease.json            # 살아 있는 이전 worker 확인용
    response.json               # 응답 자체가 없으면 FAILED
    error.json                  # 예외가 발생한 경우
  checkpoint_<UUID>.json         # 파일 SHA + 재개 계약
  checkpoint_latest.json         # 마지막 원자 저장 참조
  recorder/run_<...>/report.md   # 현재 Smoke에서는 SYNTHETIC 전용
```

|상태|의미|
|---|---|
|CREATED / RUNNING|생성 / 실행 중|
|SMOKE_PASSED|공통 실행기 합성 검증만 성공|
|BLOCKED|설정 경로·환경·가중치·학습 구현 등의 필수 조건 미충족|
|FAILED|계약 위반, 손상, 하위 프로세스 오류|
|INTERRUPTED|사용자 중단 또는 실행 중 시간 제한|
|PARTIAL|미실행 작업이 남거나 시간 예산이 소진됨|
|COMPLETED|향후 실제 학습 근거 검증 후 사용할 상태. 현재 worker는 반환 불가|

일반 오류는 다음 모델 실행을 중단한다. `--continue-on-error`는 실패 기록을
보존하면서 다음 모델로 진행한다. Dry Run은 전체 장애물을 보기 위해 모두 점검한다.

## Checkpoint와 Resume 계약

```bash
uv run --offline python scripts/experiments/run_weekend.py \
  --resume outputs/weekend_runs/실제_Run_폴더 \
  --max-hours 1 --continue-on-error
```

실제 출력된 폴더명으로 바꾼다. 완료 작업은 건너뛰고 실패/중단 작업은 새 attempt에
기록한다. `--profile`, `--models`, `--config`, `--smoke`를 다시 붙이지 않는다.
원래 모드·설정·데이터/코드 지문을 사용한다. 설정 또는 코드가 달라졌다면 새 Run을
생성한다. 같은 모델 이름만으로 이전 Checkpoint를 재사용하지 않는다.

Checkpoint 참조에는 모델 키, SYNTHETIC/REAL, 설정·데이터·환경·실행 코드 SHA,
완료 epoch/update 수, 파일 크기/SHA가 들어간다. 경로 이탈·심볼릭 링크·손상을
거부하며 가중치를 역직렬화하지 않는다. 향후 실제 학습 Checkpoint는 model,
optimizer, scheduler, RNG, sampler, scaler, best_validation, progress를 저장해야 한다.
**이 필드의 실제 모델 상태 저장·복구는 아직 미구현**이다. 현재 Smoke는 합성 JSON만
등록·복구하여 계약을 검증한다. 원자 저장을 끝낸 뒤에만 참조를 등록해야 한다.

Run 잠금으로 동시 재개를 막고, 부모가 종료돼도 이전 worker가 살아 있으면 재개를
거부한다. 이때 기존 프로세스를 자동 종료하지 않는다. 시간 제한/사용자 중단은
현재 실행기가 띄운 worker 그룹만 종료한다. `--max-hours`는 이번 세션의 예산이며
원자적인 데이터 검증/사전 점검 단계가 끝난 후 또는 worker 실행 중에 반영한다.
재개 시 별도로 지정하지 않으면 원래 세션 예산을 다시 사용한다.

## 다음 세션 연결 지점

`training_worker.py`는 `--request JSON --response JSON` 인터페이스다.
`mv_analysis/training/worker.py`의 `train` 분기는 의도적으로 BLOCKED다.
다음 구현에서는 모델별 실제 backend registry, 엄격한 완료 근거 검증, 실제
Checkpoint 저장/복원, Validation/Test/Benchmark/보고서를 연결해야 한다.
현재 설정 JSON을 공식 baseline이라고 선언하거나 상태만 COMPLETED로 바꾸지 않는다.

이 단계에서는 Git Commit/Push와 장시간 학습을 수행하지 않았다.
