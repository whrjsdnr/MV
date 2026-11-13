# MV 팀 내부 데이터 배포 v1

이 파일은 배포 생성 시 `README_DATA.md`로 복사됩니다. 배포 디렉터리의 `release.json`과 `validation/validation.json`이 실제 수치·검증 근거입니다. 원본 영상·마스크·가중치·사람 승인 원장은 포함하지 않습니다. 4인 팀 내부 전송용이며 외부 공개 권한은 미확인입니다. GitHub에 이 ZIP이나 CSV 원본을 올리지 않습니다.

Canonical SHA-256: `{{CANONICAL_SHA256}}`

## 1. 설치와 원본 연결

MV 프로젝트 루트에서 실행합니다. Python 3.12와 uv를 먼저 준비합니다. 이번 배포 도구는 아직 Commit/Push하지 않았으므로 기존 GitHub 코드만으로는 새 CLI가 없을 수 있습니다. 관리자가 함께 전달하는 `MV_TEAM_DATA_TOOLS_v1.zip`의 설명에 따라 새 코드만 설치하거나, 이후 검토된 소스 변경을 받습니다. 기존 코드·환경은 교체하지 않습니다.

```bash
uv sync --locked
uv run --locked python scripts/team_data_release.py --help
export REALIAD_DATA_ROOT="/본인/Real-IAD/루트"
```

도움말에 build/verify/smoke/export-targets가 나와야 합니다. 경로는 `audiojack/NG/...` 등의 품목 디렉터리가 바로 아래에 있는 루트입니다. Git Clone으로 데이터는 내려오지 않습니다. 각 팀원이 사용 허가된 동일 원본 JPG/PNG를 별도 준비합니다. 파일명이나 데이터 내용은 수정하지 않습니다.

## 2. 해시와 압축 해제

관리자에게 ZIP과 **별도 채널의 SHA-256 값**을 받습니다. 프로젝트 루트에서 `<받은-ZIP-SHA256>`을 실제 값으로 바꿉니다. 출력 폴더는 아직 존재하지 않아야 합니다.

```bash
uv run --locked python scripts/team_data_release.py verify \
  --zip /수령경로/MV_TEAM_DATA_RELEASE_v1.zip \
  --sha256 <받은-ZIP-SHA256> \
  --extract-to outputs/team_data_received_v1 \
  --result outputs/team_data_received_v1_check.json
export MV_DATA_RELEASE="$PWD/outputs/team_data_received_v1/MV_TEAM_DATA_RELEASE_v1"
sha256sum "$MV_DATA_RELEASE/manifests/canonical.csv"
uv run --locked python scripts/team_data_release.py smoke \
  --release "$MV_DATA_RELEASE" \
  --result outputs/team_data_received_v1_smoke.json
```

verify는 CRC·파일별 SHA256·151,050행 식별자·좌표·클래스·5시점·Split·적격성 계약을 검사합니다. smoke는 실제 원본 표본을 디코딩하고 콘텐츠 SHA를 확인합니다. 성공은 `VERIFIED`입니다. 잘못된 경로/해시/이미지는 명시적으로 실패합니다. 실패한 파일을 자동 보정하거나 NG를 OK로 바꾸지 않습니다. 실패 시 원본과 ZIP의 버전을 확인하고 관리자에게 오류를 전달합니다. 재실행 결과 경로는 새 이름을 사용합니다.

`checksums/SHA256SUMS`는 배포 내용의 체크섬입니다. 체크섬 파일 자체는 자기 목록에 포함하지 않으며, ZIP의 외부 해시로 보호합니다. 체크섬은 전자 서명이 아닙니다.

## 3. ZIP의 각 파일

|경로|용도|
|---|---|
|manifests/canonical.csv|최종 Crop, 이미지/제품/시점/Split, 클래스, 마스크 상태, 콘텐츠 SHA 통합|
|manifests/eligibility.csv|이상탐지/검출의 Split별 적격성과 제외 사유|
|annotations/defect_boxes.csv|원본 연결 성분 BBox와 Crop 원점 이동·Clip 결과, 보존 여부|
|annotations/product_boxes.csv|사람 검수 제품 GT, 자동 제안, Crop 근사 박스의 구분|
|schemas/class_mapping.json|기존 클래스 ID를 그대로 보존한 YOLO/COCO 매핑|
|schemas/annotation_schema.json|컬럼 타입·좌표·마스크·라벨 규칙|
|validation/validation.json|실행 범위·승인 대조·전수 좌표/타깃 검증 결과|
|validation/*eligibility.csv|Split·카테고리·시점별 적격 수|
|validation/re_review_43.csv|43장 변경 좌표와 양성 픽셀 보존 재검증|
|validation/filename_class_resolution.csv|파일명 기준 10장 클래스 충돌 처리|
|validation/evaluation_independence_risks.csv|정답 참조 검수의 평가 독립성 위험 목록|

## 4. 좌표와 라벨 계약

Crop은 원본 기준 `[x0,y0,x1,y1]`, 끝 좌표 exclusive입니다. NumPy `image[y0:y1, x0:x1]`와 같습니다. 승인된 직사각형 Crop도 그대로 유지합니다. Crop을 새로 계산하거나 추가 CenterCrop하지 않습니다. 모델별 Resize/Normalize는 저장 Crop 적용 **이후 한 번만** 실행합니다.

제품 카테고리 30개, 이미지 상태 OK/NG, 객체 결함 클래스 8개는 서로 다른 라벨입니다. 클래스 ID는 AK=0, BX=1, CH=2, HS=3, PS=4, QS=5, YW=6, ZW=7입니다. COCO/TorchVision의 객체 label은 +1이며 0은 모델 배경 용도입니다. 정상 상태 OK는 기본 객체 클래스가 아닙니다. 파일명 QS와 폴더 HS가 충돌한 10장의 QS 처리와 일치합니다.

마스크는 기존 검증된 `grayscale > 0`, 8방향 연결 성분, 최소 면적 필터 없음입니다. 작은 성분도 제거하지 않습니다. 한 NG 이미지의 모든 성분에는 그 이미지의 동일 결함 종류가 붙습니다. 한 이미지 안에 다른 종류가 공존한다는 주석은 제공되지 않았습니다.

|상태|객체탐지|이상탐지|
|---|---|---|
|OK|정당한 빈 BBox Negative|Train 정상 기준; Val/Test 이미지 평가|
|NG + 양성 마스크 + 유효 BBox + 손실 없음|SUPERVISED_VALID|Val/Test 이미지 및 위치 평가|
|NG + 마스크 없음|MISSING_ANNOTATION, 기본 검출 제외|NG 이미지 평가 유지; 위치 평가 제외|
|NG + 제공된 빈 마스크|EMPTY_NG_REVIEW, 검출 제외|NG 이미지 평가 유지; 위치 평가 제외|
|손상·잘못된 좌표·Crop 주석 손실|별도 제외 사유, 기본 검출 제외|파일/좌표 오류는 로딩 금지; 손실된 위치 정답은 기본 위치 평가 제외|

NG 마스크 없음과 빈 마스크는 다릅니다. 없는 마스크를 만들지 않습니다. OK의 mask도 기본 로더에서 None일 수 있습니다. OK 음성 픽셀 평가가 필요한 평가기는 명시적인 OK 정책 아래 영상 크기의 정상 정답을 취급하며, 이를 NG에 적용하면 안 됩니다.

## 5. Single-view/Five-view 로딩

MV 루트의 Python 코드에서 다음을 사용합니다. 데이터 경로는 환경변수이므로 소스 수정이 필요 없습니다.

```python
import os
from mv_analysis.data.team_release import TeamRelease
from mv_analysis.data.datasets import FiveViewDataset
from mv_analysis.data.adapters import get_adapter
from mv_analysis.data.collate import single_view_collate, five_view_collate
from torch.utils.data import DataLoader

release = TeamRelease(os.environ['MV_DATA_RELEASE'], os.environ['REALIAD_DATA_ROOT'])
train = release.dataset(split='train', task='anomaly', eligible_only=True,
                        adapter=get_adapter('EfficientAD-S'))
batch = next(iter(DataLoader(train, batch_size=2, num_workers=0,
                            collate_fn=single_view_collate)))
# 정상 학습용 5시점은 같은 선언 제품의 C1~C5를 묶는다.
five = FiveViewDataset(train)
group_batch = next(iter(DataLoader(five, batch_size=2, num_workers=0,
                                  collate_fn=five_view_collate)))
assert group_batch['images'].shape == (2, 5, 3, 256, 256)
```

처음에는 `num_workers=0`으로 확인합니다.

각 원본은 첫 사용 시 source/mask SHA256을 대조합니다. PC 간 복사로 달라진 mtime은 불일치 근거로 쓰지 않고 콘텐츠를 검증한 뒤 메모리 내부 식별값만 연결합니다. 배포 CSV는 변경하지 않습니다. 같은 프로세스에서 이미 검증한 파일은 크기/mtime이 같을 때 캐시를 재사용하므로 데이터는 실행 중 읽기 전용이어야 합니다.

Five-view는 선언 제품 그룹 기준이며 실제 물리적 동일성의 독립 검증을 뜻하지 않습니다. 각 시점의 마스크/박스는 targets에 따로 있습니다. 검출 적격 이미지만 고르면 NG 제품의 일부 시점이 빠질 수 있습니다. 그런 집합으로 FiveViewDataset을 만들면 기본적으로 오류가 납니다. 5시점 검출은 `task='all', eligible_only=False`로 완전한 그룹을 유지하고 시점별 `detection_trainable`에 따라 담당자가 Loss/평가 제외를 명시해야 합니다. NG 미주석 시점을 빈 Negative로 처리하지 않습니다.

## 6. 객체탐지 Target 변환

```python
from mv_analysis.data.team_release import torchvision_target
from mv_analysis.data.collate import detection_collate

det = release.dataset(split='train', task='detection', eligible_only=True,
                      adapter=get_adapter('Faster R-CNN'))
sample = det[0]
images, targets = detection_collate([sample])
# 원본 Crop 픽셀 좌표 Target만 필요한 경우. labels는 이미 +1이다.
target = torchvision_target(release, sample['image_id'])
```

`torchvision_target`과 모델 Adapter를 중복 적용하여 label을 두 번 +1 하지 않습니다. Faster R-CNN/RetinaNet 내부 Resize/Normalize와 외부 전처리도 중복하지 않습니다. 나머지 모델도 기존 Adapter의 `adapter_spec`과 개별 모델 계약을 확인합니다. 12개 Adapter의 독립 변환은 검증 대상이지만 공식 모델 런타임 통합/학습은 미검증입니다.

YOLO TXT 또는 COCO JSON은 실제 구현한 CLI로 생성합니다. 출력 경로는 새 폴더여야 합니다.

```bash
uv run --locked python scripts/team_data_release.py export-targets \
  --release "$MV_DATA_RELEASE" --split train --format yolo \
  --output outputs/team_yolo_train_v1
uv run --locked python scripts/team_data_release.py export-targets \
  --release "$MV_DATA_RELEASE" --split validation --format coco \
  --output outputs/team_coco_validation_v1
```

YOLO: Crop 기준 정규화 `class_id cx cy w h`, OK 빈 TXT, NG 미주석/빈마스크/주석손실 제외. COCO: Crop 기준 XYWH, categories는 +1, OK annotation 0개. `export.json`에 수와 제외 수, `excluded.csv`에 제외 사유를 남깁니다. **두 출력은 주석만 만들며 Crop 이미지는 만들지 않습니다.** COCO file_name의 virtual_crops는 원본 JPG 경로가 아닙니다. 원본 전체 영상을 Crop 좌표 주석과 바로 연결하면 좌표가 틀립니다. 반드시 공통 Crop 로더에서 영상과 주석을 함께 적용하거나 담당자가 별도 가상 영상 어댑터를 연결합니다.

## 7. 정상 제품 BBox 확장 실험

기본 검출은 결함 8개 클래스만 사용합니다. product_boxes는 사람이 승인한 600개 GT, 자동 제안 600개 PROPOSAL, 전체 영상의 Crop 근사치를 출처별로 분리합니다. 자동 제안과 Crop은 제품 전체 정답이 아닙니다. 어떤 행도 기본 결함 Target에 넣지 않습니다. reviewer 이름과 자유 서술 notes는 배포하지 않습니다.

별도 실험에서는 OK/NG 모두 같은 방식의 제품 영역 주석을 사용하고, image status와 PRODUCT_REGION/DEFECT 유형을 분리해야 합니다. Crop 전체에 normal 클래스를 붙이는 것은 `EXPERIMENTAL_CROP_AS_NORMAL_BOX`라는 별도 실험이며 정답 제품 영역을 뜻하지 않습니다. 정상에만 큰 박스를 추가하는 정책은 기본값이 아닙니다. 상태 Head와 Loss는 담당자가 별도 설계·검증해야 하며 이번 도구에는 구현하지 않았습니다.

## 8. 추론 입력과 평가 독립성

이상탐지는 품목별 정상 기준을 기본으로 하고 품목/시점 메타데이터를 검사 시 제공할 수 있습니다. OK/NG 및 결함 종류/마스크는 추론 입력이 아닙니다. 검출은 품목을 필수 입력으로 요구하지 않고 결함 클래스·BBox를 예측합니다. 결함 미검출은 정상 **후보**이며 정상임을 보장하지 않습니다.

기존 Split은 재생성하지 않습니다. 검수 때 GT 마스크/BBox를 참고한 흔적은 `manual_annotation_assisted`, `requires_evaluation_leakage_review`와 별도 위험 목록에 남깁니다. Test의 정답을 참고해 Crop을 수정한 이미지는 독립 최종 성능을 보장할 수 없습니다. 이 ZIP은 버전·주석 일관성을 확정하는 자료이며 평가 독립성 문제를 소급해서 해결하지 않습니다. 품질 기준/학습 실험 조건은 팀에서 결정하고 공통 Recorder에 canonical SHA와 배포 버전을 기록합니다.

## 9. 관리자 재현

기존 내부 승인·분석 파일이 있는 관리자 PC만 build할 수 있습니다. 일반 팀원은 build가 아니라 verify/smoke를 실행합니다.

```bash
uv run --locked python scripts/team_data_release.py build \
  --data-root "$REALIAD_DATA_ROOT" --workers 2 \
  --output outputs/team_data_release_new_run
```

원본 JPEG 전수 디코딩 기록은 source ID·기존 SHA·현재 크기/mtime 일치 조건으로 재사용합니다. 승인된 영상은 콘텐츠 SHA를 다시 확인하고, 제공 PNG는 최종 v2 Crop에 맞춰 전수 디코딩·8연결 BBox 대조합니다. JPEG 전체 바이트를 새로 읽은 검증과 캐시 재사용을 구별합니다. 1,000장 단위 체크포인트가 있으며 소스/설정이 일치할 때만 재개합니다. 기존 ZIP/패키지 폴더를 덮어쓰지 않습니다.
