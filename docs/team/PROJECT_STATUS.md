# MV 현재 진행 상태와 다음 작업

확인일: **2026-11-13 (KST)**. 새 팀원은 이 문서 → [Fork 협업](GITHUB_FORK_WORKFLOW.md) → [설치·로더 확인](ONBOARDING_CHECKLIST.md) → [모델 실험 시작 절차](MODEL_EXPERIMENT_WORKFLOW.md) 순서로 읽는다. 이 문서는 로컬 작업 공간에서 확인한 상태다. 공통 소스·검증 코드·테스트는 이번 배포 Commit에 포함했다. 비공개 분석 결과까지 모두 GitHub에 포함되는 것은 아니며 원격 반영은 GitHub main의 Commit으로 확인한다.

상태 용어: **VERIFIED**=명시한 범위 실제 확인, **UNVERIFIED**=구현/자료는 있으나 해당 검증 미완료, **NOT_IMPLEMENTED/NOT_RUN**=아직 구현/실행 안 함. 과거 보고서는 해당 시점의 증거로 보존하고 최신 사항은 아래를 따른다.

## 최신 팀 데이터 배포 v2

- **이상탐지 승인 Crop / 객체탐지 원본 전체**로 분리했다. D1 결함 기준선과 D2 제품+결함 확장은 별도 클래스·실험·평가 계약이다.
- 기존 v1 ZIP 보존. v2 ZIP 24,040,260bytes, 151,050행/30,210그룹/30품목, 결함 BBox60,636개. 전수 원본 재분석 없이 검증된 v1 테이블을 재사용했다.
- Train 적격: 이상탐지50,930 / D1 87,077 / D2 통합87,077. 제품만 감독 가능한105,735와 구분한다.
- D2 선택 제품 출처: 사람GT600 / Crop근사150,450. 자동 제안600개도 기록에는 남지만 같은 영상의 사람GT가 우선되어 선택은0개다. Train의 제품 박스는 모두 Pseudo다.
- 기존 사람GT600은 Val290/Test310이고 모두 개발 이력이 있으므로 독립 제품 평가 적격0. 진단용 제품GT600, 결함도 유효한 통합 진단499다.
- v2 canonical SHA: `98cd47086afc939fc960b92e32ee70f38a13cfde54df71b7a54b5d68aa0222ed`. v1 또는 crop-only v2 SHA와 혼동하지 않는다.
- 실제30품목/108제품/540장으로 D1/D2 원본 전체 로딩, 정상 Train 필터를 적용한 이상탐지280장 Crop 로딩 및 5시점 배치를 검증했다. 내부 좌표 그림4장을 점검했다.
- 전체pytest223개가 로컬과 최종 도구를 설치한 별도 Git Clone에서 통과했다. 데이터/TOOLS v2 ZIP은 로컬 생성이며 Commit/Push하지 않았다. 실제 모델 학습/GPU/4명 개인 설치는 미검증이다.
- 설치·명령은 [최신 데이터 README](../data/README_DATA_TEMPLATE.md), 실제 표본 로딩/좌표 점검 결과는 [배포 검증 보고서](../../reports/TEAM_DATA_RELEASE_VALIDATION.md)를 따른다.

아래 v1 관련 내용은 이전 진행 이력이며 위 v2 정책이 최신이다.

## 지금 어디까지 완료됐나

| 영역 | 실제 완료 범위 | 상태 및 남은 일 | 근거 |
|---|---|---|---|
| Ubuntu/Python/uv | WSL2, Python3.12.14, uv0.12.8, CPU torch2.15.0, locked sync 및 dummy CPU 검사 | VERIFIED: 이번 실행 failed=[]; 다른 팀원 설치는 미검증 | scripts/validate_environment.py, outputs/environment/20261113T004142213231Z/validation.json |
| 전체 데이터 | JPG151,050, OK72,840/NG78,210, 마스크51,329, 30품목, 선언제품30,210 | 이전 v1 기준 JPG/PNG 전수 실제 디코딩 오류0. 물리 제품 동일성은 독립 검증 아님 | reports/FINAL_PREPROCESSING_VALIDATION.md |
| 분석 | 메타데이터·밝기·배경/제품밝기·해상도·마스크/BBox·Crop 비교 | 기존 결과 보존. 자동 제품 분할 품질 조건/선택편향 등 한계를 보고서와 함께 읽음 | reports/DATA_ANALYSIS_MASTER_REPORT.md, reports/ANALYSIS_EVIDENCE_INDEX.md |
| 제품 GT | 사람 승인 제품 BBox600개 | Crop 승인과 별개, 자동 제안의 GT 승격 없음 | outputs/object_aware_crop_v1/review/human_approved_gt.jsonl |
| Crop 좌표 | 전체151,050행 생성 및 수동 승인 반영 v1/v2 | 원본 Crop 이미지 전수 생성은 하지 않음 | outputs/adaptive_crop_full_v1/ |
| 이번 43장 재검수 | 검수 진행43/43, v2에서 좌표43개 변경, 최신 승인1,594건 모두 좌표 일치 | VERIFIED: 이번 변경 43장 마스크 픽셀 보존100%, 좌표 오류0, 중복ID0 | outputs/team_collaboration_docs_20261113_v1/reviewed_v2_documentation_check.json |
| 클래스 충돌 | 폴더HS/파일명QS 충돌10장 → 사용자 지시로QS | 마스크7장 BBox 복구/실제 로더 통과, 마스크없는3장 MISSING 유지 | reports/FILENAME_CLASS_RESOLUTION.md |
| 공통 로더 | Single/Five-view, 좌표/마스크/BBox 변환, 결측/검출 적격 계약, collate | 기존 검증에 더해 새 팀 배포 v1에서 v2 전체 타깃/eligibility를 별도 고정 | reports/TEAM_DATA_RELEASE_VALIDATION.md |
| 12모델 Adapter | 독립 입력 변환 구현 | 모델 실제 forward/학습통합은 UNVERIFIED. 이중CenterCrop/Normalize 주의 | mv_analysis/data/adapters.py, reports/MODEL_INPUT_REQUIREMENTS.md |
| 모델 학습 | 공식 소스 조사·커밋·입력 근거 수집 | NOT_RUN: 12모델 비교 학습/평가/선정 미실시. 과거 YOLO Crop 추론 실험과 구분 | MODEL_EXPERIMENT_WORKFLOW.md |
| 저장소 표준화 | 분석/로더 실제 패키지는 mv_analysis/, scripts/, tests/ | models/에는 계약·TODO만 추가됨. 실제 학습train.py와 src/는 없음. 기존 코드는 이동하지 않음 | 실제 디렉터리 확인 |
| Fork 공유 | README/팀 문서/PR 템플릿 추가 | 로컬 문서 VERIFIED. 각 팀원의 인증/Push/PR 실습과 관리자 보호설정은 UNVERIFIED | 이 문서 묶음 |

### 현재 Crop v2 식별자

```text
outputs/adaptive_crop_full_v1/preprocessing_metadata_reviewed_v2.csv
SHA-256 d1c13cae3fc352f457cb22f9955280e0ce140827a449465d5e05519fd6c9073d
151,050행 / 30,210 선언 제품 그룹 / 좌표 변경43행
정책 C(원본 전체):149,463 / HUMAN_CROP:1,587
최신 사람 Crop 승인:1,594 (원본 전체 승인 포함)
```

v1의 상세 전수 디코딩 결과는 내부 보고서 `reports/FINAL_PREPROCESSING_VALIDATION.md`에 있다. **최신 팀 배포 작업**에서는 이전 JPEG 디코딩/SHA를 현재 파일 stat 및 원본 식별자 대조로 재사용하고, 제공 PNG51,329장을 v2 좌표로 다시 디코딩·연결 성분·BBox 변환 검증했다. 전체 JPEG를 새로 디코딩한 검증은 아니다. 새 canonical/eligibility를 별도 배포 v1으로 고정했으며 이전 v1 적격성 표를 v2 결과로 사용하지 않았다. 상세 범위와 원본 표본 재로딩은 [팀 배포 검증](../../reports/TEAM_DATA_RELEASE_VALIDATION.md)에 기록한다.

클래스 파생 파일은 `outputs/filename_class_resolution_v1/`다. 7장 클래스 오류를 해결한 v1 기반 전체 계약은 SUPERVISED_VALID51,295 / OK_NEGATIVE72,840 / MISSING_ANNOTATION26,881 / EMPTY_NG_REVIEW34다. 클래스 충돌 해결과 Crop v2 검증 버전은 서로 다른 버전 축이다.

## 팀원이 지금 할 수 있는 작업

1. Fork 동기화, CPU 환경 설치, 합성 테스트와 공통 로더 이해.
2. 관리자에게 승인된 데이터/Manifest/클래스 파일 묶음을 받고 로컬경로 매핑 Smoke Test.
3. 담당 모델 공식 소스와 고정 커밋/라이선스/환경 조사, 별도 환경 구축.
4. 실제 모델 Dataset/Trainer와 공통 로더의 연결 코드를 기능 브랜치에서 개발하고 PR 리뷰 요청.

[모델 실험 단계별 가이드](MODEL_EXPERIMENT_WORKFLOW.md)에 Clone→환경→로더→forward Smoke→Train→Validation→Test→결과 공유 조건을 적었다. 현재 없는 학습 명령을 이미 실행 가능한 것으로 취급하지 않는다.

## 학습 전 우선 해결/팀 결정

1. **Canonical 배포**: 로컬 팀 ZIP 생성 완료. 팀 제한 저장 위치와 수령 담당자를 정하고 두 ZIP/해시를 전달한다. Git Clone만으로 데이터나 아직 미커밋인 새 도구를 얻을 수 없다.
2. **v2 계약 확정**: 새 통합 canonical SHA와 eligibility 고정 완료. 팀원은 ZIP verify/smoke 후 같은 버전으로 실험한다. 이전 파일 보존.
3. **평가 독립성**: v1 기록에 Test의 주석 참조 수동Crop189건이 있었다. v2에서도 Test를 포함한 수정이 있으므로 평가 독립성을 자동 보장하지 않는다. 변경 근거/사용된 정답/평가 보고 방식을 팀이 결정한다.
4. **모델 통합**: 학습 엔트리포인트 경로 표준화, 모델별 격리환경, 실제 모델 forward, 손실/평가 라벨 계약 검증.
5. **전처리 실험 조건**: 공식추가CenterCrop을 끈 공통 입력 조건과 공식 baseline을 분리. 실제 성능 확인 전 최적 정책 확정 금지.
6. **협업 확인**: 4명 각자 설치·데이터 수령·로더 Smoke·Fork PR 실습 기록. 관리자 main 보호/리뷰 권한 설정은 수동으로 검토.

## 이번 문서 작업의 실행 검증

아래 143개 테스트 기록은 이전 문서 개편 시점이다. 최신 데이터 배포 검증은 별도 보고서와 다음 절을 따른다.

- `uv sync --locked`: 성공, lock 변경 없음.
- Python3.12.14, dummy CPU/OpenCV/import: 성공, failed=[].
- 전체pytest: **143 passed, 1 warning**. 제한 샌드박스에서 로컬소켓 테스트가 차단된 뒤, 로컬HTTP 허용 환경에서 다시 통과했다. 경고는 기존 NumPy timedelta 사용 중단 경고.
- 저장소 URL과 공개 GitHub 화면 기본 main 확인. 로컬 main도 확인했으나 origin/HEAD 캐시는 미설정. 팀원 개별 Fork 주소/권한은 추측하지 않았다.
- GitHub 인증/Clone/Push/PR/Merge, 새 Python 설치, 모델 Clone/설치/학습 명령은 이번 작업에서 실행하지 않았다.
- 원본 데이터/승인Ledger/기존Manifest/uv.lock은 문서 작업에서 수정하지 않았다.

기존 전체 진행 보고서는 내부 자료 `reports/DATA_ANALYSIS_MASTER_REPORT.md`, `reports/DATA_LOADER_IMPLEMENTATION.md`, `reports/FILENAME_CLASS_RESOLUTION.md`를 관리자에게 별도로 수령한다. 이 내부 자료와 대형 근거 파일·PDF는 이번 Git 배포에 포함하지 않는다.

이번 README/협업 문서의 명령·링크·실제 로더 검증 범위는 [문서 검증 기록](DOCUMENTATION_VALIDATION.md)을 참고한다.

## 공통 코드 배포 업데이트

- 프로젝트 자체 소스133개에 한글 설명을 보강하고 신규/변경 코드를 목적별로 Commit했다.
- 별도 로컬 Clone의 새 가상환경에서 고정 의존성170개 설치, dummy 검증, 합성 Smoke, 전체145개 테스트를 통과했다. 기존 캐시 기반이며 인터넷 cold install과 팀원 개별 설치는 미검증이다.
- 새 명령: `uv run --locked python scripts/smoke_test_shared_data.py --synthetic`. 비공개 데이터가 없어도 실행할 수 있다.
- 전체 Canonical CSV/승인 Ledger/이미지/가중치는 Git 배포 대상에서 제외했다. [배포 검증 기록](../../reports/CODE_RELEASE_PREPARATION.md)과 [수령 안내](CODE_RELEASE.md)를 따른다.
- 사용자가 Push를 승인했다. 실제 원격 반영 여부는 GitHub main Commit을 확인한다.

## 공통 실험 인프라 추가 작업

공통 Recorder·이상탐지/검출 평가·Benchmark·시각화·Markdown/모델 비교 코드를 `mv_analysis/experiments/`에 추가했다. `models/`의 12개 모델별 계약과 TODO는 실제 모델 학습 구현이 아니다. 상세 검증 범위는 [실험 규약](../experiments/EXPERIMENT_PROTOCOL.md)과 [인프라 구현 검증](../../reports/experiments/INFRASTRUCTURE_VALIDATION.md)에 기록한다. 구현 단계에서는 Commit/Push를 수행하지 않았으며, 이후 사용자 승인에 따른 코드 배포 범위는 [배포 검증 기록](../../reports/experiments/RELEASE_VALIDATION.md)을 따른다.

최종 공통 인프라 검사: 기존145개+새40개=185개 pytest 통과, 합성12Run/실제입력10장계약검사 통과. 실제모델학습·GPU측정은미실행이며 [검증 기록과 예제](../../reports/experiments/INFRASTRUCTURE_VALIDATION.md)를참고한다. GitHub에는추론/연결코드·설정·보고서를공유하고weights는별도수령한다.
