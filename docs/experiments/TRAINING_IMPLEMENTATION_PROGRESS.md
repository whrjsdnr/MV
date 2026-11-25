# 6개 모델 학습 시스템 구현 진행 현황

## Owner CPU 학습 Backend (2026-11-13)

Owner 모델은 `models/`에 구현했다. CPU, 50 epoch, batch 1 설정과 실행 명령은
[OWNER_CPU_TRAINING.md](OWNER_CPU_TRAINING.md)를 따른다.
아래 기존 기록의 «Backend 미구현»은 이전 실행기-only 단계 기록이다.
Teammate 3개 Backend는 여전히 미구현이다. 전체 50 epoch 학습은 이번 개발에서 실행하지 않았다.

## 복구 기준 — 2026-11-13

현재 HEAD는 `8d01cc9`이다. 이전 지시서의 HEAD와 달라도 되돌리지 않는다.
기존 미추적 v2 Smoke/Test, 내부 보고서, 배포 ZIP과 승인 자료는 보존한다.

중단 시점에 존재한 파일:

- `mv_analysis/training/__init__.py`, `settings.py`: 프로필·설정·소스/가중치 확인 초안.
- `configs/training/`: 6개 모델의 초안 JSON. 공식 학습 성공이 검증된 설정은 아니다.
- `scripts/experiments/collect_training_sources.py`: 고정 Commit 텍스트 소스 수집기.
- `outputs/training_sources_v1/`: 이미 받은 소스 스냅샷. 다시 다운로드하지 않는다.
- `environments/`: 빈 디렉터리. 모델별 환경 설치 완료로 취급하지 않는다.
- 기존 Recorder·평가기·보고서·v2 데이터 로더: 재사용 대상.

## 이번 세션 체크리스트

- [x] Git 상태와 기존 파일 조사
- [x] 작업 범위를 공통 실행기와 설정 시스템으로 제한
- [x] 엄격한 설정 검증 및 owner/teammate 순서 고정
- [x] 모델별 Python 하위 프로세스 인터페이스
- [x] v2 ZIP/폴더 해시·표·Split·좌표 계약 확인
- [x] 실행 전 환경·장치·디스크·소스 점검
- [x] 원자적 Run 상태 저장, 오류/시도 기록, 중복 실행 잠금
- [x] 설정/데이터/코드/Checkpoint 지문에 묶인 Resume 계약
- [x] Dry Run 및 공통 실행기 전용 SYNTHETIC Smoke
- [x] 단위 테스트와 기존 테스트 회귀
- [x] 실제 실행 결과와 다음 작업 기록

## 이번 세션에서 하지 않는 작업

6개 모델의 학습 루프, 가중치 다운로드, 독립 환경 설치, 실제 모델 학습,
GPU Benchmark, Git Commit/Push는 수행하지 않는다.
학습 백엔드가 연결되기 전에는 학습 실행을 `BLOCKED`로 종료한다.

## 실제 완료 결과

|항목|검증 결과|한계|
|---|---|---|
|전체 pytest|**270 passed, 1 warning**, 35.78초|기존 223 + 신규 실행기 47. 경고는 기존 NumPy timedelta 사용의 deprecation|
|owner 순차 Smoke|3/3 `SMOKE_PASSED`|공식 모델 미실행, 학습 미실행|
|teammate 순차 Smoke|3/3 `SMOKE_PASSED`|공식 모델 미실행, 학습 미실행|
|Recorder/보고서|SYNTHETIC Markdown 6개 생성, 이미지 링크 검사 통과|성능 수치는 NOT_MEASURED, 모델 성능 보고서 아님|
|v2 ZIP|CRC/SHA 및 기존 v2 전수 표 검증 VERIFIED|원본 JPG 전수 재디코딩 없음|
|데이터 규모|151,050 이미지 / 30,210 선언 제품 그룹 / 30품목 / 결함 BBox 60,636|기존 v2 파일을 읽어 검증, 새 주석 생성 없음|
|데이터 접근|품목별 1장, 30장 경로·읽기 가능 확인|존재 검사이며 디코딩/실제 모델 로딩 검사 아님|
|6개 모델 Dry Run|6/6 `BLOCKED`, 종료 코드 2|독립 환경·지정 가중치·학습 backend 미완성. 점검 기능은 정상 동작|
|Resume|완료 모델 건너뛰기, 실패 모델 새 attempt, 합성 Checkpoint 복구 테스트 통과|실제 모델/optimizer/RNG 복원은 아직 미구현|
|보존 확인|사전 해시를 저장한 20개 파일 모두 불변|v2 ZIP/배포 16개 파일, Crop Ledger 2개, uv.lock|

현재 Canonical SHA-256:
`98cd47086afc939fc960b92e32ee70f38a13cfde54df71b7a54b5d68aa0222ed`

v2 ZIP SHA-256:
`39acd673b0042e5b626a8e84fa25f0d1190db02b56f6f1dded4b5c8886dada43`

실행 근거는 로컬 [validation.json](../../outputs/training_recovery_checks/validation.json)에 모았다.
실제 결과 디렉터리:

- owner: `outputs/training_recovery_checks/final_runs/weekend_20261113T094308_298602e9d1d94bb3a9414360c8df341c/`
- teammate: `outputs/training_recovery_checks/final_runs/weekend_20261113T094220_025c67e8327548689127ac67cbdedadc/`
- 6개 모델 Dry Run: `outputs/training_recovery_checks/final_runs/weekend_20261113T094309_790f0ce1ec124dc58d5dbf316830827c/`

`outputs/`는 로컬 전용이다. Fork에 이 파일들이 포함된다고 가정하지 않는다.

## 변경 파일과 재사용 파일

이번 세션에서 수정/추가한 구현:

- `mv_analysis/training/settings.py`: 기존 초안을 엄격한 설정·프로필·소스 검증으로 보완.
- `mv_analysis/training/preflight.py`: v2 ZIP/폴더, 원본 경로 표본, 독립 Python/장치/자원 점검.
- `mv_analysis/training/state.py`: 불변 plan, 잠금, 사건 기록, Checkpoint 참조 계약.
- `mv_analysis/training/runner.py`: 순차 실행, Dry Run, 제한 시간, 오류 처리, 재개.
- `mv_analysis/training/worker.py`: 모델 환경에서 받는 요청/응답 계약, 합성 Smoke만 구현.
- `scripts/experiments/run_weekend.py`, `training_worker.py`: 실제 CLI 진입점.
- `tests/test_training_runner.py`: 47개 신규 검사.
- `README.md`, 이 문서, [사용법](TRAINING_RUNNER_GUIDE.md), [환경 인터페이스](../../environments/README.md).

이전 세션의 `configs/training/*.json` 6개, `collect_training_sources.py`, 기존 실험
모듈·데이터 로더·모델 TODO 파일은 다시 만들지 않았다. 모델 JSON 값은 변경하지
않았고 검증 코드를 추가했다. 이번 세션에는 설치/소스 다운로드도 수행하지 않았다.

## 미완료 항목 — 다음 세션에서 순서대로 수행

1. **모델별 환경 호환성 확인.** 이미 받은 고정 Commit 소스를 재사용한다.
   UniAD의 옛 torch/numpy 의존성과 직접 `.cuda()` 호출, HVQ-Trans 라이선스 미확인,
   고정 소스와 설치된 torchvision의 일치 여부를 해결한다. 공통 `.venv`는 보존한다.
2. **한 모델부터 실제 worker backend 연결.** 현재 train 분기는 명시적 BLOCKED다.
   공식 생성 API, 로컬 가중치 출처/SHA, v2 anomaly/D1 입력을 실제 확인한다.
3. **실제 Checkpoint 계약 구현.** 모델·optimizer·scheduler·RNG·sampler·scaler와
   완료 update, Validation best 상태를 원자 저장하고 중간 epoch 재개를 검증한다.
4. **Validation/Test/Benchmark/시각화 연결.** 기존 공통 평가기/Recorder를 재사용하고
   실제 결과와 합성 결과를 분리한다. Test로 threshold나 best 모델을 고르지 않는다.
5. **작은 실제 데이터 모델 Smoke 후 다른 5개 모델로 확장.** 이 단계가 끝나기 전
   GPU 학습 준비 완료 또는 공식 baseline 재현 완료라고 표시하지 않는다.

이번 세션은 여기서 종료한다. 장시간 학습, 가중치 다운로드, Commit, Push는 하지 않았다.

## Owner 최종 체크리스트

- [x] `models/` 아래 Owner 3개 Backend 연결
- [x] GitHub 고정 소스 3종 확보
- [x] 독립 CPU 환경 설치
- [x] 사용자 지정 50 epoch / batch 1 기본값
- [x] 실데이터 소량 학습·평가·시각화·보고서 3/3 통과
- [x] 전체 pytest 309개 통과
- [x] 단일 실행 명령 사전검사 3/3 통과
- [ ] 전체 50 epoch 학습 (사용자가 시작)
- [ ] 장시간 중단/재개 및 전 품목 안정성

[상세 검증 결과](../../reports/OWNER_BACKEND_VALIDATION.md)
