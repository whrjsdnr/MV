# MV — Real-IAD 5시점 제조 외관검사

WSL2 Ubuntu, Python 3.12, uv, CPU PyTorch를 기본으로 메타데이터·밝기·불량 위치·객체 라벨·원본 JPG 해상도 손실을 분석한다. 원본은 읽기 전용으로 사용하고 결과는 실행별 outputs 폴더에 보관한다. 이 분석 경로는 모델 학습을 수행하지 않는다. 모델 실험 준비 절차는 아래 별도 가이드를 따른다.

## 처음 읽는 팀원 안내

- **[현재 진행 상태와 다음 작업](docs/team/PROJECT_STATUS.md)**: 분석·재검수·로더가 어디까지 완료됐는지, 지금 남은 검증과 담당 작업.
- **[팀 데이터 ZIP 수령·계약·검증](#팀-데이터-zip-수령과-공통-계약)**: 최종 검수 v2와 클래스 보정이 합쳐진 동일 데이터로 실험 시작.
- **[팀원 시작하기 — GitHub Fork 사용자](#팀원-시작하기--github-fork-사용자)**: 아래 빠른 시작.
- [Fork 상세 실습](docs/team/GITHUB_FORK_WORKFLOW.md) · [설치/로더 체크리스트](docs/team/ONBOARDING_CHECKLIST.md) · [기여 규칙](docs/team/CONTRIBUTING.md)
- **[공통 실험·평가 규약](docs/experiments/EXPERIMENT_PROTOCOL.md)** · [모델별 담당 TODO](models/README.md)
- **[모델 실험 시작 절차](docs/team/MODEL_EXPERIMENT_WORKFLOW.md)**: 공식 소스 Clone·커밋 고정 → 독립 환경 → 공통 로더 연결 → 입력 Smoke → 학습/평가 → PR.
- [오류 복구](docs/team/TROUBLESHOOTING.md) · [관리자 PR/Canonical 배포](docs/team/MAINTAINER_GUIDE.md)

현재 공통 Single/Five-view 로더와 12개 독립 입력 Adapter가 구현됐다. 12개 모델 학습 통합/성능 비교는 아직 실행하지 않았다. `models/`에는 이번에 모델별 계약·TODO 인터페이스를 추가했으며 실제 학습 코드는 아직 없다. 공통 실험 인프라는 `mv_analysis/experiments/`에 있다.

## 팀 데이터 ZIP 수령과 공통 계약

**최신 v2: 이상탐지는 승인 Crop, 객체탐지는 원본 전체 이미지를 사용합니다.**

|실험|입력|Target|
|---|---|---|
|이상탐지 6종|원본 → 승인 Crop → 모델 Resize/Normalize|Train OK, 이상 점수/히트맵. 품목/시점으로 정상 기준 선택|
|D1 결함 탐지 기준선|원본 실제 H/W 전체 → 모델 Resize/LetterBox/Normalize|결함 8클래스만. OK는 빈 결함 객체|
|D2 제품+결함 확장|원본 실제 H/W 전체 → 모델 Resize/LetterBox/Normalize|제품 30클래스 + 결함 8클래스. 제품 출처/품질 구분|

D1/D2는 별도 experiment_id·클래스 매핑·평가 결과를 사용합니다. 제품 mAP와 결함 mAP를 섞지 않습니다. OK/NG는 이미지 상태이고 `normal` 객체 클래스를 추가하지 않습니다. NG 미주석은 결함 UNKNOWN이며 D2 제품 박스가 있어도 일반 통합 학습의 빈 Negative로 넣지 않습니다.

관리자에게 **MV_TEAM_DATA_RELEASE_v2.zip + MV_TEAM_DATA_TOOLS_v2.zip + SHA-256**을 팀 내부 채널로 받습니다. v1 ZIP은 보존합니다. 이번 새 도구는 Commit/Push하지 않았으므로 Fork 동기화만으로 설치되지 않습니다. TOOLS ZIP 설치기는 기존 공통 코드 해시를 확인하고 새 파일만 설치합니다. v1 도구가 이미 수정된 폴더이면 덮어쓰지 않고 거부하므로 별도 깨끗한 코드 복사본 또는 검토된 diff로 통합합니다.

MV 루트에서 실행합니다. ZIP 경로를 바꾸고 새 출력 폴더를 사용합니다.

```bash
uv sync --locked
uv run --locked pytest -q tests/test_team_data_release.py tests/test_team_data_release_v2.py
export REALIAD_DATA_ROOT="/본인/Real-IAD/루트"
uv run --locked python scripts/team_data_release.py verify \
  --zip /받은경로/MV_TEAM_DATA_RELEASE_v2.zip \
  --sha256 39acd673b0042e5b626a8e84fa25f0d1190db02b56f6f1dded4b5c8886dada43 \
  --extract-to outputs/team_data_received_v2
export MV_DATA_RELEASE="$PWD/outputs/team_data_received_v2/MV_TEAM_DATA_RELEASE_v2"
uv run --locked python scripts/team_data_release.py smoke --release "$MV_DATA_RELEASE"
```

고정 환경→합성 검사→원본 루트→ZIP 해제/계약 검사→실제 표본 로딩입니다. `VERIFIED`와 오류 없음으로 확인합니다. 데이터/해시/좌표가 틀리면 중단하고 관리자에게 전달하며 자동 보정하지 않습니다. 원본 데이터는 Git Clone에 포함되지 않습니다.

- [v2 배포 README](docs/data/README_DATA_TEMPLATE.md): TeamReleaseV2의 anomaly/D1/D2 실행 예제, YOLO/COCO export, 정상/미주석 처리.
- [스키마](docs/data/MANIFEST_SCHEMA.md) · [로더 연결](docs/data/DATA_LOADER_GUIDE.md) · [실제 검증 결과와 한계](reports/TEAM_DATA_RELEASE_VALIDATION.md).
- v2 Canonical SHA-256: `98cd47086afc939fc960b92e32ee70f38a13cfde54df71b7a54b5d68aa0222ed`.
- 전체 151,050장 / 30,210 선언 제품 / 결함 BBox60,636개. 43장 재검수와 기존 Split·승인 좌표는 보존했습니다.
- Train 적격: 이상탐지 50,930장, D1 87,077장, D2 통합 87,077장. 제품만 감독 가능한 105,735장과 D2 통합 적격 수는 다릅니다.
- 사람 제품 GT600개는 모두 Val/Test의 개발 자료입니다. Train 제품 주석은 모두 Crop 근사이며, 독립 제품 평가 적격은 0입니다. Pseudo를 실제 GT로 평가하지 않습니다.
- 원본 JPG/PNG·가중치·승인 Ledger·개인 경로는 ZIP/GitHub에 넣지 않습니다. 큰 Manifest와 ZIP은 내부 전달합니다. Test 주석 참조 Crop189건과 PENDING1건은 별도 기록합니다.

## 공통 실험·평가·Markdown 보고 시스템

**팀원 결과 제출 공지: GitHub에는 추론/모델 연결 코드·실행 설정·Markdown 결과보고서·공유 가능한 그래프를 올립니다. 모델 가중치·체크포인트·메모리 뱅크·검색 인덱스는 올리지 않습니다.** 가중치는 팀 내 별도 채널로 받고, 보고서에는 파일명·크기·SHA-256·수령 방법만 남깁니다. 비밀 URL/토큰/개인 경로는 공개하지 않습니다.

- [공통 실험 규약](docs/experiments/EXPERIMENT_PROTOCOL.md): Recorder, 이상탐지/검출 평가, 원본 좌표 복원, Validation Threshold, Benchmark와 비교 조건
- [구현 검증·합성 보고서 예제](reports/experiments/INFRASTRUCTURE_VALIDATION.md): 실제 모델 성능과 구분한 검사 결과
- [4명 모델 배분·완료 기준](docs/team/MODEL_EXPERIMENT_ASSIGNMENT_GUIDE.md)
- [모델별 작업 영역](models/README.md): 12개 모델의 전처리·학습·평가 계약과 명시적 미구현 TODO

GPU 학습은 담당 팀원의 독립 환경에서 수행합니다. 공통 코드는 CPU 합성 자료로 검증할 수 있으며 실제 12개 모델 학습을 대신하지 않습니다. 기존 로더·승인 Crop·Split은 그대로 사용합니다.

```bash
# MV 루트: 데이터/가중치 없이 합성 Recorder·지표·그래프·보고 검증
uv run --locked python scripts/experiments/smoke_test_reporting.py
# 저장된 Run의 Loss/ROC/PR/시점·latency 그래프와 새 Markdown 버전
uv run --locked python scripts/experiments/generate_report.py --run-dir outputs/experiments/실제run_id
# 기본은 REAL·COMPLETED이며 동일 데이터/평가 계약끼리 비교
uv run --locked python scripts/experiments/compare_models.py --runs-root outputs/experiments/
```

Run은 `outputs/experiments/<run_id>/`에 설정·환경·Loss CSV·예측·지표·Benchmark·그림·report.md를 남깁니다. 미측정은 N/A, 합성은 SYNTHETIC/PARTIAL로 표시합니다. Loss가 없는 모델에는 가짜 Loss를 만들지 않습니다. Pixel AUROC/AP/AUPRO의 고정 히스토그램 근사와 누락 주석 제외를 보고합니다. 다른 GPU의 속도나 서로 다른 Manifest 결과를 하나의 순위로 합치지 않습니다. 모델별 Train 명령은 담당자가 실제로 연결·검증하기 전까지 제공하지 않습니다. 공유는 기존 Fork → 기능 Branch → PR 절차를 따릅니다.

GitHub에는 [이상탐지 합성 예제](reports/experiments/release_examples/SYNTHETIC_ANOMALY.md)와 [객체탐지 합성 예제](reports/experiments/release_examples/SYNTHETIC_DETECTION.md), 대표 그래프 6개만 배포합니다. 전체 합성 Run·예측 배열·중간 결과는 위 Smoke 명령으로 로컬에서 생성합니다. 배포 범위와 검증 기록은 [공통 실험 배포 검증](reports/experiments/RELEASE_VALIDATION.md)을 참고하세요.

## 팀원 시작하기 — GitHub Fork 사용자

```text
                   원본 whrjsdnr/MV
                          │ Fork
              ┌───────────┼───────────┐
              ▼           ▼           ▼
            팀원 A       팀원 B       팀원 C
            개인 Fork    개인 Fork    개인 Fork
              │ Clone     │ Clone     │ Clone
              ▼           ▼           ▼
            로컬 PC      로컬 PC      로컬 PC
              └── Push → 각자의 Fork 기능 브랜치
                          │ Pull Request
                          ▼
                 리뷰·관리자 Merge → 원본 main
```

Fork는 **GitHub 안의 개인 복사본**, Clone은 **내 PC로 복제**다. 팀원은 `origin=개인 Fork`, `upstream=원본 MV`로 사용한다. Branch는 기능 작업 공간, Commit은 로컬 변경 이력, Push는 원격 업로드, Fetch는 원격 이력 조회·갱신, Pull은 가져오기와 통합, PR은 원본 반영 요청, Merge는 변경 통합이다. Conflict는 자동 통합이 안 되는 충돌이다. 자세한 용어/성공 출력/실패 대응은 [Fork 가이드](docs/team/GITHUB_FORK_WORKFLOW.md)에 있다.

### 1. 개인 Fork Clone과 upstream

WSL2 Ubuntu에서 실행한다. `<내-GitHub-ID>`는 **실제 본인 계정으로 바꾼 후** 사용한다.

```bash
# MV를 둘 상위 폴더에서
git clone https://github.com/<내-GitHub-ID>/MV.git
cd MV
git remote -v
# upstream이 없을 때만 추가
git remote add upstream https://github.com/whrjsdnr/MV.git
git remote -v
```

Clone은 새 MV 폴더를 만들고 cd는 그 프로젝트로 이동한다. origin의 fetch/push는 개인 Fork, upstream은 원본 URL이어야 한다. 이미 등록됐으면 add를 반복하지 않는다. upstream push URL 표시가 직접 Push하라는 뜻은 아니다. **팀원은 upstream 직접 Push 금지**. Git 설치·작성자 설정과 GitHub CLI/GCM 인증, Clone 오류는 [상세 가이드 1~2절](docs/team/GITHUB_FORK_WORKFLOW.md)을 따른다. 비밀번호/토큰은 코드에 저장하지 않는다.

### 2. 환경과 데이터 로더

이후 명령은 Clone한 MV 루트에서 실행한다. uv가 없으면 [Ubuntu 설치](docs/INSTALL_LINUX.md)를 먼저 따른다.

```bash
uv python install 3.12
uv sync --locked
uv run --locked python --version
uv run --locked python scripts/validate_environment.py --dummy
uv run --locked pytest -q
uv run --locked python scripts/smoke_test_shared_data.py --synthetic
export REALIAD_DATA_ROOT="/본인/Real-IAD/루트"
```

순서대로 Python 확보→lock 고정 환경 설치→3.12 확인→CPU dummy 검증→테스트→현재 터미널의 로컬 데이터 경로 설정이다. 성공은 Python3.12, failed=[], pytest passed다. 설치 실패 시 lock을 재생성하지 말고 [오류 해결](docs/team/TROUBLESHOOTING.md)을 따른다.

합성 Smoke는 외부 데이터 없이 Single/Five-view·마스크 상태·12개 입력 변환을 확인한다. [코드 배포·Canonical 수령 안내](docs/team/CODE_RELEASE.md)를 참고한다.

**데이터와 전체 Crop CSV는 Clone으로 내려오지 않는다.** 위 v2 팀 데이터 ZIP을 별도로 수령하고 hash를 대조한다. 최신 배포 canonical은 reviewed_v2 좌표와 파일명 클래스 보정에 이상탐지 Crop/검출 원본 정책 및 새 eligibility를 고정했다. [배포 로더 가이드](docs/data/DATA_LOADER_GUIDE.md)를 따라 개인 data_root로 로드한다. 과거 crop-only v1/v2 파일의 SHA와 새 통합 canonical SHA를 구분한다.

### 3. 매일 동기화 → 새 브랜치

미커밋 변경이 있으면 먼저 기능 브랜치에 Commit하거나 안전하게 보관한다. clean 상태의 MV 루트:

```bash
git status
git fetch upstream
git switch main
git merge --ff-only upstream/main
git log --oneline --left-right main...upstream/main
git push origin main
git switch -c feature/anomaly-patchcore
```

Fetch는 작업 파일을 합치지 않으며 ff-only는 이력이 갈라지지 않았을 때만 main을 갱신한다. log로 차이를 확인한 뒤 개인 Fork main을 갱신한다. 실패하면 강제로 Reset/Push하지 않는다. 새 브랜치는 작업 내용에 맞춰 이름을 바꾼다. [안전한 복구](docs/team/TROUBLESHOOTING.md)를 참고한다.

### 4. 파일 수정 → Stage → Commit → 개인 Fork Push

실제 존재하는 공통 Adapter 수정 예시다. 파일을 편집기로 저장한 뒤 MV 루트:

```bash
git status
uv run --locked pytest -q
git add mv_analysis/data/adapters.py tests/test_data_loading.py
git diff --cached
git commit -m "feat: improve PatchCore input adapter"
git push -u origin feature/anomaly-patchcore
```

add는 지정 파일을 다음 Commit 대상으로 Stage하고, commit은 로컬 이력을 저장한다. push는 개인 Fork 브랜치에 올린다. Commit만으로 공유되지 않고 Push만으로 원본에 반영되지 않는다. cached diff에서 데이터/개인 설정이 섞이지 않았는지 확인한다. `git add .`를 무조건 사용하지 않는다. 모델 학습 코드를 추가하려면 [공식 코드 Clone 이후 단계](docs/team/MODEL_EXPERIMENT_WORKFLOW.md)를 먼저 따른다.

### 5. PR과 Merge된 코드 받기

개인 Fork 웹 → Compare & pull request → **base whrjsdnr/MV:main**, **head 본인Fork:기능브랜치** 확인 → 변경/실제 테스트 결과 작성 → Create pull request → 팀 리뷰 → 관리자 Merge. [PR 템플릿](.github/PULL_REQUEST_TEMPLATE.md)을 사용한다. 권한/화면별 상세 절차는 [Fork 가이드 6절](docs/team/GITHUB_FORK_WORKFLOW.md)에 있다.

Merge 뒤에는 3절의 status/fetch/switch/ff-only/push 순서로 main을 갱신하고 새 기능 브랜치를 만든다. 계속 진행 중인 기능 브랜치는 clean 상태에서 `git fetch upstream` 후 **기능 브랜치에서** `git merge upstream/main`으로 통합하고 테스트한다. [충돌 해결](docs/team/GITHUB_FORK_WORKFLOW.md)을 먼저 읽는다.

### 매일 쓰는 Git 명령 요약

장소는 모두 MV 루트이며 변경 전에 status를 읽는다.

| 명령 | 목적 / 성공 확인 | 실패 시 참고 |
|---|---|---|
| git status | 현재 브랜치·변경·Stage 상태 | [복구 A/B](docs/team/TROUBLESHOOTING.md) |
| git fetch upstream | 원본 원격 이력 갱신, 오류 없이 종료 | 인증/URL 확인 |
| git switch main | main 전환 | 변경을 먼저 보존 |
| git merge --ff-only upstream/main | main을 원본 최신으로, Fast-forward/Already up to date | 분기 이력 확인, 강제 금지 |
| git switch -c 기능브랜치 | 새 브랜치 생성/이동 | 기존 이름 확인 |
| git add 지정경로 | 필요한 파일만 Stage | 경로/ignore 확인 |
| git diff --cached | 다음 Commit의 실제 변경 검토 | 불필요 파일은 Stage 취소 |
| git commit -m "설명" | 로컬 이력 저장, hash 출력 | 작성자/Stage 확인 |
| git push -u origin 기능브랜치 | 개인 Fork 업로드 | [Push 거절 복구](docs/team/TROUBLESHOOTING.md) |
| git merge upstream/main | 작업 브랜치에 원본 변경 통합 | 충돌은 협의 후 편집·Stage·Commit |

초보 실습은 [문서 한 장으로 PR 흐름 익히기](docs/team/GITHUB_FORK_WORKFLOW.md)를 따른다. 연습 PR은 합의 없이 원본에 Merge하지 않는다.

## Git 공유 범위

코드·모델 Config·테스트·README·팀 문서·pyproject.toml·uv.lock은 검토 후 공유한다. 소형 합성 Manifest/스키마는 권한과 내용 확인 후 후보가 될 수 있다. 원본 JPG/PNG·대형 가중치·.venv·.env·개인 경로 설정·캐시·대형 학습 로그·API 키는 올리지 않는다. **전체 Manifest와 사람 승인 기록은 자동 공개하지 않는다.** `.gitignore`는 이미 추적한 파일의 공개를 취소하지 않는다. [기여 규칙](docs/team/CONTRIBUTING.md)과 [관리자 배포 가이드](docs/team/MAINTAINER_GUIDE.md)를 따른다.

## 기존 분석 실행 및 보존 기록

아래는 기존 분석 사용법과 결과 링크다. 최신 검수·로더 상태 판단은 위 [현재 진행 상태](docs/team/PROJECT_STATUS.md)를 우선한다. 기존 해상도 전수 계산이나 Crop 연구를 팀 설치 과정에서 반복할 필요는 없다.

```bash
# WSL2 Ubuntu 터미널, clone한 MV 루트
bash scripts/setup.sh
export REALIAD_DATA_ROOT="/실제/데이터셋"
uv run --locked python -m mv_analysis.cli --split-policy windows-project-v1 validate-data
uv run --locked python -m mv_analysis.cli --split-policy windows-project-v1 metadata --limit 20
uv run --locked python -m mv_analysis.cli --split-policy windows-project-v1 run-all --limit 100
```

설치와 독립적인 파일 구조 검사:

```bash
python3 scripts/inventory_dataset.py --data-root "$REALIAD_DATA_ROOT"
```

실제 대상은 JPG 151,050장(OK 72,840 / NG 78,210), PNG 51,329장이다. NG 26,881장에 위치 마스크가 없다는 사실은 오류가 아니다. 전체 NG를 영상 분석에 사용하고 has_mask=True인 NG만 위치 분석에 사용한다. 미주석 NG의 빈 마스크/빈 YOLO 라벨을 만들지 않는다. PNG 회색조는 threshold 민감도와 overlay를 확인한 후 정책을 정하며, 정책 미확정 시 위치 분석만 보류한다. 최신 완료/실행 중/미검증 상태는 [최종 보고서](reports/REAL_IAD_FINAL_ANALYSIS.md)와 [실행 로그](reports/ANALYSIS_EXECUTION_LOG.md)를 확인한다.

- [Ubuntu 설치](docs/INSTALL_LINUX.md), [Ubuntu 검증](docs/ENVIRONMENT_VALIDATION.md), [이전 감사](docs/MIGRATION_AUDIT.md)
- [데이터 경로·검증](docs/DATASET_SETUP.md), [CLI·산출물·Notebook](docs/ANALYSIS_PIPELINE.md)
- [Git/GitHub 초보 실습](docs/GIT_GITHUB_BEGINNER_GUIDE.md), [4명 협업 규칙](docs/TEAM_GIT_WORKFLOW.md), [팀원 설치 실습](docs/TEAM_ONBOARDING.md)
- [마스크 임계값 검증](reports/MASK_THRESHOLD_VALIDATION.md), [환경 이전 보고서](reports/ENVIRONMENT_MIGRATION_REPORT.md)

단계별 실행은 같은 `--output`에 `--resume`으로 이어간다. CLI 전역 옵션은 단계 이름 앞에 둔다. 새 출력 디렉터리와 원본 디렉터리는 서로 포함할 수 없다. 설정·lock·소스가 다른 실행은 그대로 재사용하지 않는다. 전체 실행은 환경/합성 테스트/실제 표본 preflight 및 복사 완료 확인이 필요하다. 상세 명령은 분석 가이드를 따른다.

기존 루트 Windows 검증 문서와 docs/archive 설정은 역사 기록으로 보존했다. 추가 조사에서 마운트된 Windows 원본 소스/Notebook 60개를 legacy/windows_snapshot에 보존했다. 기존 split은 151,050장 모두 동일하게 재현했고, 실제 Windows JPG/PNG 경로 집합도 현재와 일치한다. 같은 방법의 밝기150장/해상도50장 재실행 비교는 reports/WINDOWS_RESULT_COMPARISON.md를 참조한다. 데이터·가중치·.env·대용량 결과·Notebook 출력은 GitHub에 올리지 않는다. 최신 지시에 따라 GitHub에는 코드·문서만 업로드 후보로 검수하며 Push는 수행하지 않는다. 원본 데이터/가중치는 포함하지 않는다. 팀원 4명의 개별 설치/PR 실습은 각자 실행하기 전까지 미검증이다.


추가 내용 감사에서 전검정 JPG 2장의 동일 바이트 중복을 확인했다. 초기 hash 탐색 분할에서는 Train/Test에 나뉘지만 보존한 Windows 분할에서는 두 장 모두 Train이며, 이 분할의 정확한 바이트 교차 중복은0이다. 선언된 제품 키의 분할 검사와 실제 물리 제품 identity 확인은 구분한다. NG 쪽은 전영역 마스크로 특정 위치 집계에 큰 영향을 준다. 원본 전체 분석을 보존하고 quality_review에 모델 입력 보류 후보와 위치 선행분포 대조를 남겼다. 검수 전 모델 학습 준비 완료로 판단하지 않는다.


배경·제품·결함 국소 밝기 확장: [실행 가이드](docs/BACKGROUND_BRIGHTNESS.md), [근거 보고서](reports/BACKGROUND_AWARE_BRIGHTNESS_ANALYSIS.md). 전체 실행 상태는 보고서 상단을 확인한다.


해상도 전수 결과의 재집계: [상세 Markdown](reports/RESOLUTION_DETAILED_ANALYSIS.md), [파일 목록·한계·회의 결정 사항](reports/RESOLUTION_DELIVERY_GUIDE.md). 회의용 최종 PDF `reports/RESOLUTION_TEAM_MEETING_FINAL.pdf`는 Git 배포 대상이 아니므로 관리자에게 별도로 수령한다. 기존 151,050장 결과를 재사용했으며 전체 해상도 계산을 반복하지 않았다. 그래프·집계 CSV는 Git에서 제외된 outputs/resolution_detail_20261111_v2/에 있다.
