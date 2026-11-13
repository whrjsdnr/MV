# MV 팀 데이터 배포 v2 — 작업별 입력 계약

**이상탐지: 승인 Crop. 객체탐지: 원본 전체. D1: 결함만. D2: 제품+결함.**

Canonical SHA-256: `{{CANONICAL_SHA256}}`

v1 ZIP은 과거 Crop 공통 계약으로 보존한다. 이 v2는 v1의 검증된 마스크/BBox·승인 좌표·Split을 재사용하며 원본을 다시 분석하거나 좌표를 바꾸지 않는다. 4인 팀 내부 전송 전용이다. 공개 재배포 권한은 미확인이다. 원본 JPG/PNG·가중치·승인 Ledger·개인 경로·검수자 이름은 포함하지 않는다.

## 1. 설치·해제·실제 로딩

관리자에게 DATA v2 ZIP, TOOLS v2 ZIP, 각 SHA-256을 별도 채널로 받는다. 이번 도구는 Commit/Push하지 않았으므로 기존 Fork 동기화만으로 설치되지 않는다. TOOLS ZIP README의 해시 점검과 설치기를 먼저 실행한다. 기존 수정 파일을 덮어쓰지 않으므로 충돌 시 별도 깨끗한 MV 코드 복사본에 설치하거나 관리자와 diff를 검토한다.

이후 **MV 루트**에서 실행한다. 경로/ZIP 해시를 수령값으로 바꾸고 새 출력 폴더를 사용한다.

```bash
uv sync --locked
uv run --locked pytest -q tests/test_team_data_release.py tests/test_team_data_release_v2.py
export REALIAD_DATA_ROOT="/본인/Real-IAD/루트"
uv run --locked python scripts/team_data_release.py verify \
  --zip /받은경로/MV_TEAM_DATA_RELEASE_v2.zip \
  --sha256 <받은-v2-ZIP-SHA256> \
  --extract-to outputs/team_data_received_v2
export MV_DATA_RELEASE="$PWD/outputs/team_data_received_v2/MV_TEAM_DATA_RELEASE_v2"
uv run --locked python scripts/team_data_release.py smoke \
  --release "$MV_DATA_RELEASE" --result outputs/team_data_v2_smoke.json
```

환경 설치→합성 검사→개인 원본 루트→ZIP CRC/해시/계약 검증→실제 원본 표본 로딩 순서다. `VERIFIED`와 예외 없음으로 성공을 확인한다. Real-IAD는 별도 준비하며 데이터 루트 바로 아래에 audiojack 등 품목 폴더가 있어야 한다. Git Clone에는 데이터가 없다. 해시/파일/좌표가 틀리면 중단하고 관리자에게 image_id/오류를 전달한다. 자동 수정·Split 재생성·NG 정상 재분류는 하지 않는다.

첫 사용 시 원본 콘텐츠 SHA를 확인한다. PC 간 복사로 달라진 mtime은 콘텐츠 일치 후 메모리에서만 처리하고 CSV는 수정하지 않는다. 원본은 실행 중 읽기 전용이어야 한다. SHA256SUMS는 서명이 아니므로 ZIP의 신뢰할 수 있는 외부 해시도 확인한다.

## 2. 파일 구조

|경로|역할|
|---|---|
|release.json|v2, 출처 v1 hash, 작업별 정책|
|manifests/canonical.csv|이미지/제품/시점/Split/상태/마스크/승인 Crop/입력 정책/제품 주석 출처|
|manifests/eligibility.csv|이상탐지·D1·제품 학습·D2 통합 학습·진단/독립 평가 적격성|
|annotations/defect_boxes.csv|원본 마스크 8연결 성분 BBox, 기존 Crop 변환은 감사용 보조 필드|
|annotations/product_boxes.csv|GT/자동/Crop 근사 원본 BBox, selected_for_d2, 출처/검증 상태|
|schemas/class_mapping.json|기존 결함 ID, 제품 ID, D1/D2별 모델 Target ID|
|schemas/annotation_schema.json|dtype, 좌표계, 정책, 컬럼|
|validation/validation.json|v1 검증 재사용 근거와 v2 참조/정책 검증|
|validation/*eligibility.csv|Split·품목·시점별 적격 수|
|validation/re_review_43.csv|기존 43장 재검수 좌표/마스크 보존 근거|
|validation/evaluation_independence_risks.csv|정답 참조 Test Crop 위험|
|checksums/SHA256SUMS|개별 배포 파일 해시|

## 3. 이상탐지 6종

원본→승인 Crop→모델별 Resize/Normalize→이상점수/히트맵이다. 품목은 모델/정상 기준 선택에 사용하며 필요하면 C1~C5도 제공한다. OK/NG나 결함 마스크/종류는 모델 추론 입력이 아니다. Train은 OK, Validation에서 Threshold 고정, Test 재조정 금지다. 위치 정답 없는 NG는 영상 평가를 유지하고 픽셀 평가에서는 제외한다.

```python
import os
from mv_analysis.data.team_release_v2 import TeamReleaseV2
from mv_analysis.data.adapters import get_adapter
from mv_analysis.data.datasets import FiveViewDataset
from mv_analysis.data.collate import five_view_collate
from torch.utils.data import DataLoader

release = TeamReleaseV2(os.environ['MV_DATA_RELEASE'], os.environ['REALIAD_DATA_ROOT'])
anomaly = release.dataset(task='anomaly', image_policy='approved_crop',
                          split='train', eligible_only=True,
                          adapter=get_adapter('EfficientAD-S'))
five = FiveViewDataset(anomaly)
batch = next(iter(DataLoader(five, batch_size=2, num_workers=0,
                            collate_fn=five_view_collate)))
assert batch['images'].shape == (2, 5, 3, 256, 256)
```

원본 기준 Crop은 `[x0,y0,x1,y1]` 끝 좌표 exclusive다. 이미지와 마스크에 같은 Crop을 적용하고 범주 마스크 Resize는 NEAREST다. 히트맵 복원은 기존 restore_map/restore_anomaly_prediction을 사용하며 Crop 밖은 미관측 영역이다. 이를 정상 픽셀로 확정하지 않는다. 기존 Adapter는 보존 정책상 추가 CenterCrop을 비활성화한다. 공식 구현의 추가 CenterCrop과 완전히 같은 조건이 아니므로 해당 3종의 공식 기준선은 별도 조건으로 보고하고 몰래 다시 Crop하지 않는다. 모델 런타임의 실제 보간/Normalize 일치는 담당자가 확인한다.

## 4. 객체탐지 D1 — 결함 기준선

원본의 실제 H/W를 사용하고 승인 Crop은 입력에 적용하지 않는다. 원본 결함 BBox와 마스크→공식 모델 Resize/LetterBox/Normalize 순서다. OK는 결함 0개, NG 미주석/빈 마스크는 기본 검출 제외다. 정상 판정은 결함 미검출에 따른 정상 후보이며 보장이 아니다.

```python
from mv_analysis.data.collate import detection_collate

d1 = release.dataset(task='detection', image_policy='original_full',
                     annotation_policy='defect_only', split='train', eligible_only=True,
                     adapter=get_adapter('YOLO11'))
images, targets = detection_collate([d1[0]])
```

모델명은 Faster R-CNN, RetinaNet, YOLO11, RT-DETRv2, YOLOS, ViTDet 중 지정한다. TorchVision 내부 Resize/Normalize와 외부 Adapter의 중복을 피한다. 기존 독립 Adapter는 실제 학습 모델 통합까지 검증된 것이 아니다.

## 5. 객체탐지 D2 — 제품+결함 확장

D1과 동일한 원본 전체 입력에 제품 주석을 추가한다. 제품 source는 **사람 GT 우선→자동 제안→Crop 근사**로 고정하고 GT 결함 위치로 선택하지 않는다. 모든 출처는 product_boxes에 남고 이미지당 selected_for_d2 1행을 선택한다.

```python
d2 = release.dataset(task='detection', image_policy='original_full',
                     annotation_policy='product_and_defect', split='train', eligible_only=True,
                     allow_pseudo_products=True, adapter=get_adapter('YOLO11'))
sample = d2[0]
print(sample['annotation_types'])
print(sample['metadata']['product_bbox_source'])
```

OK: 제품 박스 + 결함 빈 목록. NG 양성: 제품 + 실제 결함 박스. NG 미주석: 제품은 존재 가능하지만 결함은 UNKNOWN이다. Tensor에 결함 행이 없는 경우에도 `defect_boxes_known=False`, `detection_trainable=False`, MISSING_ANNOTATION을 유지한다. 일반 D2 Loss에 넣으면 미주석 결함을 배경으로 학습할 수 있으므로 기본 통합 학습에서는 제외한다. 제품만 부분 감독하려면 별도 미주석 영역 무시 Loss를 구현·검증해야 한다. 이번에는 구현하지 않는다.

제품 Pseudo-label은 자동/Crop 근사이며 검증된 GT가 아니다. Crop 근사는 제품 주변 배경 여백을 포함할 수 있다. `allow_pseudo_products=False`면 사람 GT가 있는 이미지로 제한한다. 사람 GT 600개도 기존 Crop 개발에 사용됐으므로 독립 최종 제품 평가 적격성은 False다. 개발 GT 진단만 필요하면 `evaluation_mode='diagnostic'`를 명시한다. D2 제품 mAP와 결함 mAP를 하나로 합쳐 모델 품질을 주장하지 않는다. 제품 카테고리 정확도·제품 위치 성능·결함 성능·OK/NG를 따로 기록한다.

## 6. 클래스와 적격성

기존 결함 AK/BX/CH/HS/PS/QS/YW/ZW = 0..7을 유지한다. D1의 defect_*도 같은 ID다. D2는 defect_* 0..7 + product_* 8..37이며 새 제품 순서는 canonical의 30품목 사전순이다. 제품 전용 0..29 매핑도 별도 저장한다. 클래스 0은 YOLO 결함 AK이며 TorchVision/COCO에서는 모든 객체 ID에 +1한다. 이미지 OK/NG와 background 0은 객체 normal 클래스가 아니다. label을 두 번 +1하지 않는다.

|항목|의미|
|---|---|
|anomaly_train_eligible|Train 유효 OK 승인 Crop|
|anomaly_image_eval_eligible|Val/Test 유효 OK/NG|
|anomaly_pixel_eval_eligible|Val/Test 위치 평가 가능, Crop 주석 손실 제외|
|detection_defect_train/eval_eligible|D1 원본 결함 주석 유효 + Split|
|detection_product_train_eligible|제품 주석/근사 존재 Train, 미주석 NG 포함 가능. 일반 D2 통합 학습과 같지 않음|
|detection_product_eval_eligible|독립 제품 GT 부족으로 False|
|detection_joint_train_eligible|D2 제품 존재 + D1 결함 감독 가능 Train|
|detection_joint_eval_eligible|독립 제품 GT 부족으로 False|
|product_gt_diagnostic_eligible|Val/Test의 기존 사람 GT, 개발 진단 전용|
|detection_joint_diagnostic_eligible|개발 GT 진단 + D1 결함 감독 가능|

5시점 적격 이미지만 필터하면 일부 NG 시점이 빠질 수 있다. 전체 그룹 조회에는 `eligible_only=False`를 사용하고 미주석/부적격 시점 Loss를 명시적으로 제외한다. 기본 FiveViewDataset은 시점 누락 오류를 발생시키며 임의 합치기·Split 변경은 하지 않는다. 물리 제품 동일성이 독립 검증된 것은 아니다.

## 7. 원본 좌표 주석 export와 복원

```bash
uv run --locked python scripts/team_data_release.py export-targets \
  --release "$MV_DATA_RELEASE" --split train --format yolo \
  --annotation-policy defect_only --output outputs/d1_yolo_train_v2
uv run --locked python scripts/team_data_release.py export-targets \
  --release "$MV_DATA_RELEASE" --split train --format coco \
  --annotation-policy product_and_defect --output outputs/d2_coco_train_v2
```

v2 YOLO는 **원본 실제 H/W 기준** normalized CXCYWH, COCO는 원본 XYWH 및 실제 원본 상대 file_name이다. D1 OK TXT는 빈 파일, D2 OK TXT는 제품 행이 있다. annotation_provenance.jsonl은 승인 원장이 아니라 내보낸 Target의 출처/품질 sidecar다. 원본 이미지 파일은 생성하지 않는다. export.json에 입력 정책/좌표계/제외 수를 기록한다. D2 Val/Test 기본 독립 평가 export는 적격 0행이며, 개발 GT 진단 export만 `--evaluation-mode diagnostic`로 명시한다.

학습 중 박스는 Adapter가 Resize/LetterBox에 맞춰 변환한다. 예측은 restore_detection_prediction에 실제 출력 형식/정규화/offset을 명시하여 원본 좌표로 복원한다. D2 class_ids는 `release.classes['D2']['yolo'].values()`를 사용한다. 기존 ground_truth_records(index)는 결함 전용 D1 GT이므로 D2 제품 평가 GT라고 사용하지 않는다. D2 제품 GT는 human_verified와 개발/독립 구분을 적용한 별도 평가 집합에서만 사용한다.

## 8. 한계와 관리자 재현

Test 189장의 주석 참조 Crop 위험을 보존한다. v2 검출은 Crop을 실행하지 않지만 기존 데이터 탐색·제품 GT 개발 이력이 사라지는 것은 아니다. 이상탐지 Crop 평가의 독립성을 보장하지 않는다. 최종 정책/모델 선택은 Validation에서 수행하고 독립 평가 계획은 팀에서 정한다. PENDING 1건은 원본 전체 좌표로 남으며 자동 승인하지 않는다.

관리자는 다음으로 기존 v1 검증 결과만 재사용하여 새 패키지를 만든다. 원본 재처리·모델 학습은 없다.

```bash
uv run --locked python scripts/team_data_release.py build-v2 \
  --source-release outputs/team_data_release_v1/MV_TEAM_DATA_RELEASE_v1 \
  --output outputs/team_data_release_new_v2
```

JPG 검증은 이전 전수 디코딩/SHA와 stat 일치 캐시, PNG는 v1 제작 시 최종 Crop 기준 전수 재검증 결과를 이어받는다. 이번 v2를 JPEG/PNG 전수 재분석이라고 보고하지 않는다. 팀원별 실제 원본 로딩은 SHA 검사와 smoke로 추가 확인한다. 코드/Adapter·좌표 계약의 성공과 모델 학습 성능은 별개이며 실제 학습/GPU 검증은 수행하지 않는다.
