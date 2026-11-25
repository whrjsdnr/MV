# Real-IAD 팀원용 공통 학습 실행 도구 v1

**이 ZIP만으로 RT-DETRv2·UniAD·HVQ-Trans를 학습할 수 없습니다.**
공통 실행기·설정·점검·재개 계약을 전달하는 패키지이며 실제 학습 Backend는 미구현입니다.
GPU 학습 완료나 실제 모델 최종 보고서 생성을 검증한 자료가 아닙니다.

|항목|배포 상태|
|---|---|
|Common Runner|VERIFIED|
|Data v2 Integration|VERIFIED|
|Synthetic Smoke Test|VERIFIED|
|RT-DETRv2 Training|NOT_IMPLEMENTED|
|UniAD Training|NOT_IMPLEMENTED|
|HVQ-Trans Training|NOT_IMPLEMENTED|
|GPU Training|NOT_VERIFIED|
|Automatic Final Report|NOT_VERIFIED|

검증 범위/실제 실행 결과는 `package.json`과 `VALIDATION_SUMMARY.json`을 확인합니다.
합성 Recorder 보고서 생성과 실제 모델 학습 종료 후의 자동 최종 보고서는 다른 기능입니다.

## 1. 패키지 방식과 필요한 파일

**Git Clone 위에 적용하는 Overlay**입니다. 단독 프로젝트/가상환경이 아닙니다.
기준 Git Commit은 `{{BASE_COMMIT}}`이며, 설치기는 기존 공통 모듈·환경 파일의
해시를 확인합니다. 더 최신 Commit이어도 필수 공통 파일의 내용이 같으면 설치할 수
있습니다. 내용이 다르면 담당자에게 검토를 요청하고 임의 덮어쓰기를 하지 않습니다.

- `files/`: Clone에 추가할 실행기·설정·테스트·안내문. 파일별 목록은 `FILE_LIST.md`.
- `package.json`: 기존 Clone에서 재사용하는 파일의 SHA와 새 파일의 SHA, 상태.
- `install_tools.py`: Python 표준 라이브러리만 사용하는 설치기.
- `SHA256SUMS`: 자기 자신을 제외한 ZIP 내부 모든 파일의 해시.
- `VALIDATION_SUMMARY.json`: 배포 검사 근거. GPU 실험 결과가 아닙니다.

GitHub에 이미 있는 공통 데이터/평가 모듈과 `pyproject.toml`, `uv.lock`은 중복으로
넣지 않습니다. 설치 시 해시를 검사하고 재사용합니다. owner 설정 3개도 공통 프로필
및 기존 테스트에 필요하므로 작은 JSON만 포함합니다. 불필요한 모델 소스, 원본
JPG/PNG, 가중치, 승인 Ledger, 기존 실험 결과는 포함하지 않습니다.

별도로 필요한 파일:

- 실제 데이터 점검: `MV_TEAM_DATA_RELEASE_v2.zip` + 관리자가 전달한 SHA256.
- 원본 Real-IAD: 각자 보관한 로컬 원본. Git/이 도구 ZIP에 들어 있지 않습니다.
- 기존 `MV_TEAM_DATA_TOOLS_v2.zip`: 보관하되 최신 기준 Clone에 반드시 다시 설치할
  필요는 없습니다. 이 Overlay는 아직 Git에 없는 v2 Smoke/테스트를 함께 제공합니다.
  예전 도구가 적용돼 있어도 동일한 파일은 유지하고 다른 파일은 충돌로 중단합니다.

## 2. Fork와 최신 코드 준비

WSL2 Ubuntu 터미널에서 실행합니다. 처음에는 프로젝트를 둘 상위 폴더에서 Clone합니다.
`<내-GitHub-ID>`를 실제 ID로 바꿉니다. 이미 Clone했다면 그 MV 폴더로 이동합니다.

```bash
git clone https://github.com/<내-GitHub-ID>/MV.git
cd MV
git status
git remote -v
```

`git status`에 수정 파일이 있으면 먼저 Commit하거나 별도 보관합니다. Clone/동기화는
원본 데이터셋을 내려받는 명령이 아닙니다. upstream이 없는 경우에만 등록합니다.

```bash
git remote add upstream https://github.com/whrjsdnr/MV.git
git fetch upstream
git switch main
git merge --ff-only upstream/main
git rev-parse HEAD
```

`upstream already exists`면 `git remote -v`로 URL을 확인하고 중복 등록하지 않습니다.
`--ff-only`가 실패하면 강제 Reset/Push를 하지 말고 팀 관리자에게 상태를 공유합니다.
최신 코드가 아직 기준 Commit에 도달하지 않았다면 설치기의 BASE_MISMATCH를 해결한
후 진행합니다. 이 패키지는 Git Commit/Push/Merge를 대신 실행하지 않습니다.

## 3. Ubuntu·Python·uv 조건

MV 루트에서 아래 명령으로 OS/도구를 확인합니다.

```bash
cat /etc/os-release
uname -a
git --version
uv --version
uv python install 3.12
uv sync --locked
uv run --locked python --version
```

공통 환경은 Python 3.12와 기존 `uv.lock`을 사용합니다. uv가 없으면 Clone의
`docs/INSTALL_LINUX.md`에 있는 설치 절차를 먼저 따릅니다. `uv sync --locked`는
패키지 환경 설치이며 데이터/모델 가중치 다운로드가 아닙니다. 실패하면 설치 오류와
OS 정보를 공유하고 `uv.lock`을 삭제하거나 임의 재생성하지 않습니다.
GPU 모델별 환경은 나중에 별도로 설치해야 하며 공통 `.venv`에 섞지 않습니다.

## 4. 안전한 ZIP 설치

Discord에서 ZIP, 외부 `install_tools.py`, `SHA256SUMS_DELIVERY`를 같은 폴더에 받습니다.
외부 설치기는 ZIP 내부 설치기와 동일하며, 압축을 안전하게 풀기 위한 도구입니다.
관리자가 별도로 안내한 해시와도 대조합니다. SHA는 서명이 아닙니다.

받은 파일 폴더에서 실행합니다.

```bash
sha256sum -c SHA256SUMS_DELIVERY
```

모두 `OK`여야 합니다. 이어서 **자신의 MV 루트**로 이동하고 경로를 바꿔 실행합니다.
`<ZIP-SHA256>`는 관리자가 전달한 64자리 해시입니다. 추출 폴더는 아직 없는 곳을 지정합니다.

```bash
python3 /받은경로/install_tools.py \
  --archive /받은경로/MV_TEAMMATE_TRAINING_TOOLS_v1.zip \
  --expected-sha256 <ZIP-SHA256> \
  --extract-to /tmp/mv-training-tools-v1 \
  --workspace "$PWD" --dry-run
```

ZIP 크기/CRC/SHA, 경로 탈출·링크·중복 파일, 압축 해제 파일 SHA, 기존 Clone 공통 코드,
설치 대상 충돌을 검사합니다. Dry Run은 추출 폴더만 만들며 Clone을 변경하지 않습니다.
성공 시 `DRY_RUN_PASSED`와 추가할 파일 목록이 출력됩니다. 이미 추출했다면 다시
압축을 풀지 말고 다음 설치기에 `--dry-run`만 지정하여 재검사할 수 있습니다.

```bash
python3 /tmp/mv-training-tools-v1/MV_TEAMMATE_TRAINING_TOOLS_v1/install_tools.py \
  --workspace "$PWD" --apply
```

`INSTALLED_VERIFIED`가 정상입니다. 기존 파일과 동일하면 유지하고, 다르면 **어떤 파일도
추가하기 전에 충돌로 중단**합니다. 기존 설정/Checkpoint/결과를 삭제하지 않습니다.
중간 I/O 오류가 발생하면 추가한 파일 목록을 출력하고 그대로 보존합니다. 해결 후
재실행하면 동일 파일은 건너뜁니다. 다른 Clone 폴더에서 설치하지 않았는지 확인합니다.

## 5. 원본 데이터와 v2 ZIP 연결

MV 루트에서 실행하며 경로를 본인 환경에 맞게 바꿉니다.

```bash
export REALIAD_DATA_ROOT="/본인/Real-IAD/원본루트"
uv run --locked python scripts/team_data_release.py verify \
  --zip /받은경로/MV_TEAM_DATA_RELEASE_v2.zip \
  --sha256 39acd673b0042e5b626a8e84fa25f0d1190db02b56f6f1dded4b5c8886dada43 \
  --extract-to outputs/team_data_received_v2
export MV_DATA_RELEASE="$PWD/outputs/team_data_received_v2/MV_TEAM_DATA_RELEASE_v2"
```

해제 대상은 새 폴더여야 합니다. 이미 검증·해제했다면 그 경로를 MV_DATA_RELEASE에
지정합니다. 위 SHA는 현재 v2 ZIP에만 해당합니다. 다른 배포 파일의 해시를 대신
사용하지 않습니다. `VERIFIED`가 출력돼야 하며 오류가 있으면 원본 CSV를 수정하지
말고 공유합니다. UniAD/HVQ-Trans는 승인 Crop, RT-DETRv2는 원본 전체 D1 계약입니다.

## 6. 환경 점검과 합성 Smoke

```bash
uv run --locked python scripts/validate_environment.py --dummy
uv run --locked python scripts/experiments/run_weekend.py --profile teammate --dry-run
uv run --locked python scripts/experiments/run_weekend.py --profile teammate --smoke
uv run --locked pytest -q
```

Dummy는 공통 환경 검사입니다. Dry Run은 v2 파일 전체 계약과 품목별 파일 존재 표본,
모델별 환경/소스/로컬 가중치를 점검합니다. 현재는 `TRAIN_BACKEND_NOT_IMPLEMENTED`
등으로 **BLOCKED, 종료 코드 2**가 정상적으로 예상됩니다. 오류를 무시하고 학습
가능하다고 판단하지 않습니다. 원본 이미지 전수 디코딩 검사는 아닙니다.

Smoke는 RT-DETRv2 → UniAD → HVQ-Trans 순서로 별도 프로세스에서 실행기 계약을
검사합니다. 모델 환경이 없으면 공통 Python을 사용하는 **CPU SYNTHETIC 검사**이며
공식 모델을 로드하거나 학습하지 않습니다. 세 작업 `SMOKE_PASSED`, 종료 코드 0이
기대 결과입니다. 실제 데이터 ZIP이 없어도 환경변수를 설정하지 않은 상태에서
Smoke를 실행할 수 있습니다. `--smoke --device cuda`는 지원하지 않습니다.

## 7. CUDA/GPU와 독립 환경

```bash
nvidia-smi
uv run --locked python -c "import torch; print(torch.__version__, torch.version.cuda, torch.cuda.is_available())"
```

첫 명령은 WSL에 노출된 NVIDIA GPU를 확인합니다. 실패하면 Windows 드라이버/WSL
설정을 점검합니다. 공통 uv.lock은 CPU PyTorch이므로 두 번째 명령의 CUDA False만으로
GPU 고장이라고 판단하지 않습니다. 실제 모델 GPU 환경은 아직 설치·검증되지 않았습니다.

향후 독립 환경이 준비되면 MV_PYTHON_RTDETRV2, MV_PYTHON_UNIAD,
MV_PYTHON_HVQ_TRANS에 각 `bin/python` 경로를 지정합니다. 설치 후
`environments/README.md`의 계약을 따릅니다. 실행기는 모델 환경 안에서 실제 torch
import와 CUDA 가용성을 확인하며 지정한 CUDA가 없으면 CPU로 조용히 바꾸지 않습니다.
공식 소스 스냅샷/모델 가중치는 이 ZIP에 없으므로 Dry Run의 누락 이유를 확인합니다.

## 8. 실제 학습은 다음 개발 단계

아래 명령의 **CLI는 존재하지만 현재 학습 Backend가 없어서 BLOCKED됩니다.**
모델별 환경·공식 구현·학습·검증·Checkpoint 연결 이후 사용할 목표 명령입니다.

```bash
uv run --locked python scripts/experiments/run_weekend.py --profile teammate --device cuda
```

다음 개발 순서는 고정 공식 소스/API·라이선스 확인 → 독립 환경 → v2 로더 연결 →
소량 실제 forward/backward → Checkpoint/Resume → Validation/Test → Benchmark와
실제 보고서입니다. 지금은 가중치 다운로드나 장시간 학습을 시작하지 않습니다.

## 9. 재개와 결과 확인

```bash
uv run --locked python scripts/experiments/run_weekend.py \
  --resume outputs/weekend_runs/실제_Run_폴더 --max-hours 1 --continue-on-error
```

실제 출력된 폴더명으로 바꿉니다. 완료 작업은 건너뛰고 새 attempt에 실패/재개 기록을
남깁니다. `--profile`, `--smoke`, 변경 Config를 다시 붙이지 않습니다. 코드·데이터·환경
지문이 달라지면 같은 Run의 재개를 거부합니다. 현재 Checkpoint 검증은 합성 상태/참조
계약까지이며 실제 학습 optimizer/RNG 복구는 아직 없습니다.

출력은 `outputs/weekend_runs/weekend_<UTC>_<UUID>/`입니다.

- `plan.json`, `state.json`, `events.jsonl`: 설정·상태·오류.
- `<모델>/attempt_<UUID>/preflight.json`, `worker.log`, `response.json`: 점검 및 worker 결과.
- `<모델>/recorder/run_<...>/report.md`: 현재는 SYNTHETIC 보고서만 생성.
- `checkpoint_*.json`: 불변 설정/데이터/환경/파일 해시 참조.

원본 이미지·제품 GT·Crop 승인 Ledger·Split을 수정하거나 다시 생성하지 않습니다.

## 10. 문제 발생 시 공유 자료

명령어, `git rev-parse HEAD`, Ubuntu/Python/uv 버전, 오류 마지막 부분,
`state.json`·`events.jsonl`·해당 attempt의 `preflight.json`/`worker.log`를 팀 내부에
공유합니다. 개인 절대 경로·사용자 이름·토큰 등은 지운 복사본으로 공유합니다.
원본 데이터, 가중치, `.env`, 인증 정보는 공유 로그에 넣지 않습니다.

|문제|안전한 대응|
|---|---|
|BASE_MISMATCH|필수 공통 코드 버전이 다름. Fork/upstream과 변경 내역을 확인하고 관리자에게 전달|
|PRESERVE_EXISTING|수정한 파일을 보존. 다른 깨끗한 Clone을 사용하거나 변경 diff를 리뷰|
|Use a new extraction directory|이미 해제했다면 내부 설치기로 점검. 기존 폴더를 삭제하지 않음|
|ZIP/파일 SHA 불일치|전달받은 ZIP/해시를 다시 확인. 검사 우회 금지|
|Data root missing|Git 문제가 아니라 로컬 데이터 경로 문제. 환경변수와 실제 경로 확인|
|Independent Python missing|모델별 환경 미설치. 합성 Smoke 성공과 GPU 환경 준비를 구분|
|TRAIN_BACKEND_NOT_IMPLEMENTED|현재 명시된 미완료 상태. 모델별 실제 구현이 필요|
|Resume hash mismatch|동일 Run 설정 변경 금지. 새로운 Run에서 진행하고 기존 결과 보존|

설치 후 상세 안내는 Clone의 `docs/experiments/TRAINING_RUNNER_GUIDE.md`를 확인합니다.
진행 현황 문서의 `outputs/` 링크는 제작자의 로컬 실행 이력이며 ZIP에 포함되지 않습니다.
원본 저장소: https://github.com/whrjsdnr/MV
