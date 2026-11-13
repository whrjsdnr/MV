# 공식 모델 소스 Clone 이후 학습·평가를 시작하는 절차

이 문서는 팀원이 **앞으로 수행할 실험 절차**다. 이번 문서 작업에서는 모델 Clone·의존성 추가·가중치 다운로드·학습·Fine-tuning·성능 비교를 실행하지 않았다. 현재 MV의 12개 Adapter는 독립 입력 변환 단계만 검증됐으며 실제 모델과의 연결은 UNVERIFIED다. [진행 상태](PROJECT_STATUS.md), [모델별 공식 소스/커밋/입력 근거](../../reports/MODEL_INPUT_REQUIREMENTS.md)를 먼저 읽는다.

## 단계별 완료 조건

**최신 확정 입력 전략(v2)**: 이상탐지는 승인 Crop 후 모델별 Resize/Normalize, 객체탐지는 실제 원본 전체 H/W 후 모델별 Resize/LetterBox/Normalize다. D1 결함 기준선과 D2 제품+결함 확장은 서로 다른 experiment_id와 클래스 매핑을 쓴다. D2 제품/결함 mAP는 분리하며 Pseudo 제품 박스를 독립 GT로 평가하지 않는다. [v2 데이터 README](../data/README_DATA_TEMPLATE.md)와 TeamReleaseV2를 따른다. 아래 v1 hash/설명은 이전 배포 이력으로, 새 실험은 v2 release.json의 canonical_sha256을 Recorder에 기록한다.

데이터 준비는 새 [팀 ZIP 계약](../data/MANIFEST_SCHEMA.md)과 [로더 연결](../data/DATA_LOADER_GUIDE.md)을 우선한다. `MV_TEAM_DATA_RELEASE_v1.zip`과 새 도구 ZIP을 내부 수령하고 verify/smoke를 통과한 뒤 시작한다. 기존 v1 적격성 표를 재사용하지 않는다. 공통 Recorder의 manifest_sha256에는 통합 canonical SHA `a4e0c603539b7e9146c9d12abc2af5f551dda32e63b7bd45a763ddb19cc41833`을 기록한다. 기본 검출에서 OK는 빈 결함 BBox, NG 미주석/빈 마스크는 제외다. 제품 GT와 Crop 근사 박스는 별도 확장 실험에만 사용한다. 주석을 참고한 Test Crop 189건의 독립성 한계를 결과에 명시한다. 이번 변경은 모델 학습 구현을 추가하지 않는다.

| 단계 | 담당자가 하는 일 | 다음 단계로 가는 조건/남길 증거 |
|---|---|---|
| 0. 공통 데이터 고정 | 관리자 승인 Canonical Manifest/라벨/class-map 수령 | 파일별 SHA-256, 정책/클래스 버전, v2 검증 범위 기록 |
| 1. 작업 브랜치 | MV에서 기능 브랜치 생성 | 담당 파일과 모델 인터페이스 합의 |
| 2. 공식 소스 확보 | MV 밖에 저장소 Clone, 근거 커밋 고정 | URL·commit·라이선스·서브모듈 기록 |
| 3. 독립 모델 환경 | 공식 요구조건과 Python3.12/CPU 호환성 조사 | 환경 설치/import 확인, 버전·명령·실패 이유 |
| 4. Real-IAD 연결 | 공통 로더를 공식 모델 Dataset/Trainer 계약에 연결 | 이미지/마스크/BBox와 class ID, split, NG 결측 처리 확인 |
| 5. 입력 Smoke | 소수의 Train/Validation 제품으로 배치/모델 forward 점검 | shape/dtype/범위/손실 입력/좌표, 가중치 출처 기록 |
| 6. 학습 실행 | 확정 config/seed/데이터 버전으로 학습 | 실행 명령·장치·로그·체크포인트. Test로 정책 조정 금지 |
| 7. Validation 선택 | 미리 정한 지표로 임계값/체크포인트 선택 | 선택 규칙과 Validation 결과 기록 |
| 8. Test 평가 | 고정 모델·임계값으로 최종 평가 | 영상/픽셀/검출 지표의 유효 표본 수, 제외 사유, 제품 단위 결과 |
| 9. PR 공유 | 코드·소형 config·문서·테스트만 Fork PR | 대용량 결과/데이터/비밀 제외, 미검증 항목 명시 |

## 1. MV 작업 브랜치 생성

Clone한 **MV 루트**에서 [Fork 일상 절차](GITHUB_FORK_WORKFLOW.md)로 최신 main을 받은 뒤:

```bash
git switch -c feature/anomaly-patchcore
```

새 브랜치로 이동했다는 메시지가 성공이다. 이미 있으면 새로 생성하지 말고 기존 브랜치를 확인한다. 현재 `models/`에는 계약·미구현 TODO가 있고 `mv_analysis/experiments/`에는 공통 기록·평가·보고 코드가 있다. 실제 모델 학습 엔트리포인트는 없으므로 `uv run models/.../train.py` 같은 명령은 아직 실행할 수 없다. 첫 통합 PR에서 관리자와 경로를 합의한다. 구조 표준화 PR이 먼저 Merge되면 그 경로를 따른다. 예를 들어 `experiments/patchcore/`를 제안할 수 있지만 **현재 존재하는 폴더로 간주하지 않는다**.

## 2. 공식 저장소를 MV 밖에 Clone하고 커밋 고정

기존 `outputs/model_sources_20261112_v1/`는 전처리 근거 수집용 소스 스냅샷이다. 완전한 학습용 Clone/설치 환경과 같다고 가정하지 않는다. 기존에 완전한 Clone이 있으면 URL·커밋을 확인해 재사용한다. MV 안에 다른 .git을 중첩해 통째로 Stage하지 않는다.

PatchCore의 근거 커밋 예시다. **WSL2 Ubuntu의 어느 디렉터리에서나** 다음 명령을 실행하되, 대상이 이미 있으면 Clone을 생략하고 내용을 먼저 확인한다.

```bash
mkdir -p ~/mv-model-sources
cd ~/mv-model-sources
git clone https://github.com/amazon-science/patchcore-inspection.git
cd patchcore-inspection
git status
git checkout --detach fcaa92f124fb1ad74a7acf56726decd4b27cbcad
git rev-parse HEAD
git remote -v
```

| 명령 | 목적/변경 | 확인/실패 대응 |
|---|---|---|
| mkdir/cd | 외부 모델 소스를 둘 위치 준비/이동 | 경로 확인, MV 내부가 아니어야 함 |
| clone | 공개 공식 소스만 복제 | 새 디렉터리, 실패 시 URL/네트워크/권한 확인 |
| status | 기존 작업 유무 확인 | 수정이 있다면 detach 전 보존, 덮어쓰지 않음 |
| checkout --detach hash | 근거 버전으로 읽기/실험용 고정 | HEAD hash 일치, 커밋 없으면 소스 근거 확인 |
| rev-parse HEAD | 실제 실행 소스 commit 읽기 | 전체 hash를 실험 설정에 기록 |
| remote -v | 출처 확인 | 공식 URL인지 확인 |

detached HEAD는 공식 코드를 그 버전에서 참조하기 위한 상태다. 수정이 필요하면 해당 외부 Clone에 별도 작업 브랜치를 만들고, MV PR에는 허용된 연결 코드/패치와 출처를 공유한다. 외부 코드를 그대로 재배포하기 전 라이선스를 확인한다. Git LFS나 서브모듈에 가중치/데이터가 포함되는 구현은 다운로드 대상을 사전 점검한다.

다른 모델은 다음 출처와 근거 보고서의 **해당 커밋**을 사용한다. master/main 최신 HEAD가 검증된 버전과 같다고 가정하지 않는다.

| 모델 | 소스 | 고정 커밋 |
|---|---|---|
| PatchCore | https://github.com/amazon-science/patchcore-inspection | `fcaa92f124fb1ad74a7acf56726decd4b27cbcad` |
| EfficientAD-S | https://github.com/nelson1425/EfficientAD | `fcab5146f84ae17597044ad5ddf1656ccf805401` |
| UniAD | https://github.com/zhiyuanyou/UniAD | `a5b9d9d20c2aae680fa00fe5088616b611e05f3c` |
| HVQ-Trans | https://github.com/RuiyingLu/HVQ-Trans | `12fbfa96b906d1462cbfc1787e47e2fc17468134` |
| Dinomaly | https://github.com/guojiajeremy/Dinomaly | `1f252be03a918789b19848f0ca37166e7c28dada` |
| INP-Former | https://github.com/luow23/INP-Former | `17d265381d9b323a2ef6e05aab0665a85edebe84` |
| Faster R-CNN | https://github.com/pytorch/vision | `4260301135e34180d865426765487113f84e7707` |
| RetinaNet | https://github.com/pytorch/vision | `4260301135e34180d865426765487113f84e7707` |
| YOLO11 | https://github.com/ultralytics/ultralytics | `d2b7876e79ad2e02fd77221622774b511a8f0cb3` |
| RT-DETRv2 | https://github.com/lyuwenyu/RT-DETR | `df2a96c8c3a098567a1149bf0248da6efe6d495d` |
| YOLOS | https://github.com/hustvl/YOLOS | `5717fc29d727dab84ad585c56457b4de1225eddc` |
| ViTDet | https://github.com/facebookresearch/detectron2 | `247691a1c292654867deb35cabb27f18d75a1363` |

Faster R-CNN/RetinaNet은 torchvision 구현을 선택한 것이므로 동일 저장소를 두 번 Clone할 필요가 없다. ViTDet은 detectron2의 프로젝트 설정, RT-DETRv2는 RT-DETR 저장소의 해당 하위 구현을 확인한다. 표의 선택 출처와 모델 저자 여부를 혼동하지 않는다. 모델마다 실제 train/eval 명령은 고정한 소스 README와 설정 함수에 따라 다르다.

## 3. 환경을 기존 MV 환경과 분리

외부 모델 Clone에서 먼저 README, pyproject/setup/requirements, CUDA/CPU 연산 의존성을 읽는다. Python3.12 호환 여부를 확인하기 전에 MV의 `uv.lock`에 모델 의존성을 한꺼번에 추가하지 않는다. torchvision/detectron2 같은 컴파일·장치 요구가 맞지 않으면 CPU 설치만 성공했다고 학습 가능으로 판단하지 않는다.

독립 환경 생성 예시(WSL 어느 폴더):

```bash
mkdir -p ~/mv-model-envs/patchcore
uv venv --python 3.12 ~/mv-model-envs/patchcore/.venv
```

mkdir는 환경 보관 폴더를 만들고 uv venv는 새 격리 Python을 만든다. 생성된 Python 경로가 출력되면 성공이다. 기존 환경이 있으면 덮어쓰지 말고 버전을 확인한다. 패키지 설치는 **공식 파일이 실제 있을 때에만** 해당 외부 소스 루트에서 수행한다. requirements가 있는 구현의 형식 예:

```bash
uv pip install --python "$HOME/mv-model-envs/patchcore/.venv/bin/python" -r requirements.txt
```

이 명령은 모델 환경에만 설치한다. 파일 부재/설치 실패라면 작성자 설치 방식을 확인하며 버전을 임의로 최신화하지 않는다. 모든 모델에 requirements.txt가 있다는 뜻이 아니다. 설치 성공 후 해당 환경의 Python으로 torch/모델 모듈 import와 CPU/GPU 사용 가능 여부를 실제 확인한다. 공식 구현이 Python3.12를 지원하지 않으면 별도 지원 버전 환경과 비교 조건을 관리자와 합의하고 호환성 미완료로 기록한다. 격리 환경에서도 다운로드되는 pretrained weights의 출처·라이선스·용량·SHA는 별도로 관리한다.

## 4. 공통 로더를 모델 코드에 연결

MV는 `tool.uv.package=false`이며 현재 설치용 배포 패키지로 구성되지 않았다. 모델 환경에서 MV를 가져오려면 실제 Clone 위치를 지정한다. 예시는 MV가 `~/projects/MV`인 경우다. `~/MV`에 Clone했다면 값을 바꾼다.

```bash
export MV_PROJECT_ROOT="$HOME/projects/MV"
export PYTHONPATH="$MV_PROJECT_ROOT${PYTHONPATH:+:$PYTHONPATH}"
```

이는 **현재 터미널의 import 경로**만 바꾸고 Git 파일을 변경하지 않는다. 해당 모델 환경 Python으로 `import mv_analysis.data`가 성공해야 한다. 실패하면 프로젝트 경로와 모델 환경의 torch/opencv/pandas 등 공통 로더 의존성 호환을 확인한다. 가상환경을 분리했다고 상호 의존성 검증을 생략할 수 없다.

[온보딩 로더 예제](ONBOARDING_CHECKLIST.md)를 먼저 실행하고 모델 담당 연결 코드에서 다음 계약을 구현한다.

- `ManifestIndex(..., data_root=로컬루트)`에 관리자 승인 CSV/라벨/BBox/classes를 명시한다. CSV를 수정하거나 로더에서Crop을 다시 계산하지 않는다.
- 이상탐지 Train은 `SingleViewDataset(index, split='train', task='anomaly')`를 기본으로 사용해 OK만 선택한다. Validation/Test NG를 OK로 바꾸지 않는다.
- 검출은 OK negative와 유효 주석 NG만 Train에 사용한다. `detection_valid_only=True`에는 **동일 Manifest 해시로 검증된 eligibility 테이블**을 전달한다. 오래된 v1 계약으로 수정된 v2를 필터링하지 않는다. 현재 v2 전체 eligibility 확정은 별도 검증 단계다.
- NG+MISSING, NG+EMPTY, INVALID_TARGET을 빈 정상 Negative로 보내지 않는다. 검출 collate는 명시적 부적격 타깃을 거부한다.
- 기본 단일 시점부터 연결하고, 5시점은 각 모델이 지원하는 명시적 전략으로 연결한다. 기본 `(B,5,3,H,W)`를 지원하지 않는 모델에 그대로 넣지 않는다. 시점별 라벨은 별도 유지한다.
- 저장 좌표는 원본 XYXY exclusive. Crop 원점 이동→Clip→모델 Resize/Pad→필요한 normalized CXCYWH/클래스 offset 순서다. 마스크는 같은 기하변환과 NEAREST를 사용한다.
- YOLO/RT-DETR의 공식 데이터 경로를 쓴다면 원본/별도Crop 이미지 파일을 공식 Trainer가 직접 다시 읽으며 공통 로더를 우회하는지 점검한다. 단순 data.yaml 경로 변경만으로 저장 Crop 적용을 보장할 수 없다. custom Dataset/Trainer 또는 검증된 변환 어댑터를 연결해야 한다.
- Faster R-CNN/RetinaNet은 모델 내부 Resize/Normalize가 있으므로 독립 Adapter와 중복 적용하지 않는다. YOLOS/ViTDet도 공식 processor/mapper와 계약을 대조한다.
- PatchCore/Dinomaly/INP-Former는 공식 추가CenterCrop이 결함을 다시 자를 수 있다. 현재 manifest-preserving Adapter는 이를 껐다. **공식 baseline과 다른 실험 조건**으로 기록하며 공식 재현이라고 부르지 않는다.

## 5. 학습 전 Smoke Test

공식 모델에 연결하기 전과 연결한 후를 구분한다.

1. 합성 및 실제 소수 제품의 Single/Five-view 로딩, RGB/shape/dtype/값 범위 확인.
2. 이미지 위 BBox/마스크 좌표 정합 확인. 클래스0..7와 torchvision1..8 offset을 대조.
3. 미주석 NG/빈 마스크/작은 결함이 올바르게 제외/평가 처리되는지 확인.
4. 모델 instance 생성/import 후 실제 **forward 한 배치**를 수행하고 반환 shape/손실 입력을 확인. 이 단계부터 모델별 weights/장치/외부 코드 실행 조건을 따로 기록한다.
5. 필요하면 작은 Train/Validation 범위의 학습 루프 실행 가능성을 확인하되, 결과를 본 실험 성능으로 제시하지 않는다. PatchCore는 일반적인 신경망 역전파 학습과 달리 특징 memory bank 구축이 중심임을 구분한다.
6. 통과 후 config를 고정하고 정식 실행한다. 공식 entrypoint가 프로젝트에 연결되기 전에는 임의의 공통 `train.py` 명령을 제시하지 않는다.

## 6. 모델 담당 PR에 반드시 남길 실행법

모델 통합 완료 PR은 아래 칸을 **실제로 확인한 명령**으로 채운다. 이 문서의 빈칸을 그대로 실행하지 않는다.

| 항목 | 기록할 내용 |
|---|---|
| 코드/라이선스 | 원격URL, commit, 변경 patch, 승인된 외부 코드 배포 범위 |
| 실행 위치 | MV인지 외부 모델 소스 루트인지 |
| 환경 | Python, uv/pip/torch/torchvision, CPU/GPU, 모델별 lock 또는 버전 목록 |
| 데이터 | Manifest/annotation/eligibility/class map hash, split, mask 정책 |
| 입력 조건 | crop 버전, 모델 resize/normalize/crop 담당 위치, dtype, AMP |
| weights | 필요한 초기 가중치/라이선스/공식 출처/SHA, download 여부 |
| Smoke 명령 | 실제 entrypoint + 소수 Train/Val config + seed |
| 학습 명령 | 실제 train/fit/memory-bank 생성 명령 + 전체 config |
| 평가 명령 | Validation선택/Test고정 평가 명령 + checkpoint 지정 |
| 산출물 | 로그·체크포인트·metrics 위치 및 재개 명령 |
| 검증 상태 | 실행 완료/실패/UNVERIFIED와 처리 수 |

학습 로그와 체크포인트는 Git 제외 경로에 둔다. 이상탐지 영상/픽셀 지표와 검출mAP를 혼용하지 않는다. 마스크 없는 NG는 영상 평가에는 포함될 수 있지만 위치 평가의 정답으로 쓰지 않는다. 그룹별 split을 유지하고 제품 단위 결과도 남긴다. 추후 12개 모델 비교 시 공통 데이터 버전과 개별 공식 전처리 차이를 함께 공개한다.

## 7. 공유 및 관리자 확인

코드/소형설정/테스트/README를 개인 Fork 브랜치에 Stage→Commit→Push하고 PR로 요청한다. 모델별 새 엔트리포인트가 생기면 이 문서와 [진행 상태](PROJECT_STATUS.md)에 실제 경로와 검증된 명령을 추가한다. 관리자 승인 전 공통 로더 계약, Canonical Manifest, uv.lock을 임의로 바꾸지 않는다. 모델학습/성능검증이 끝나기 전 최적 해상도나 전처리 성능 향상을 확정하지 않는다.

## 공통 실험 인프라와 결과 제출

[실험 규약](../experiments/EXPERIMENT_PROTOCOL.md), [12모델 작업 영역](../../models/README.md), [분담·완료 기준](MODEL_EXPERIMENT_ASSIGNMENT_GUIDE.md)을 따른다. GitHub 결과 제출은 추론/연결 코드·설정·Markdown 보고서와 공유 가능한 그래프이며, weights/checkpoint/memory bank/index는 별도 전달한다. 파일명·크기·SHA와 수령 방법을 남기고 비밀 URL/토큰은 제외한다.
