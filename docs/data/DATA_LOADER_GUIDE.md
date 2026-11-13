# 팀 ZIP과 기존 공통 로더 연결 — v2

**v2는 TeamReleaseV2를 사용한다.** v1의 TeamRelease로 v2를 열면 오류가 나므로 기존 Crop 계약이 Detection에 조용히 적용되지 않는다. 이전 v1 ZIP과 TeamRelease 사용은 계속 가능하다.

```python
import os
from mv_analysis.data.team_release_v2 import TeamReleaseV2
from mv_analysis.data.adapters import get_adapter

r = TeamReleaseV2(os.environ['MV_DATA_RELEASE'], os.environ['REALIAD_DATA_ROOT'])
anomaly = r.dataset(task='anomaly', image_policy='approved_crop', split='train',
                    eligible_only=True, adapter=get_adapter('EfficientAD-S'))
d1 = r.dataset(task='detection', image_policy='original_full', annotation_policy='defect_only',
               split='train', eligible_only=True, adapter=get_adapter('YOLO11'))
d2 = r.dataset(task='detection', image_policy='original_full', annotation_policy='product_and_defect',
               split='train', eligible_only=True, allow_pseudo_products=True, adapter=get_adapter('YOLO11'))
```

Detection은 실제 원본 H/W 전체를 읽는다. `sample.crop_xyxy`는 실제 입력 영역인 전체 원본이고, 승인 Crop은 `metadata.approved_crop_xyxy`에 별도 보존된다. 따라서 공통 restore_detection_prediction은 Crop 원점 이동 없이 Padding/Scale만 되돌린다. D2 제품 BBox는 모델 Adapter 이전에 추가하므로 모든 객체에 같은 기하 변환이 적용된다. sample.annotation_types로 PRODUCT/DEFECT를 구분한다.

NG 미주석 D2의 제품 박스가 있더라도 defect_boxes_known=False, detection_trainable=False다. 일반 검출 Loss에 빈 결함 Negative로 넣으면 안 된다. D2 OK는 제품 객체가 있으므로 joint detection_status는 SUPERVISED_VALID이며 image status는 OK 그대로이고 detection_defect_status는 OK_NEGATIVE다.

제품 Pseudo를 학습에 허용하는 설정과 독립 제품 평가를 구분한다. 기존 제품 GT는 개발 자료이므로 독립 eval 적격은 없다. `evaluation_mode='diagnostic'`는 기존 사람 GT의 개발 진단용이다. 기존 ground_truth_records(index)는 D1 결함 GT만 생성하므로 D2 제품 GT로 사용하지 않는다. [최신 배포 README](README_DATA_TEMPLATE.md)의 D1/D2 export, 클래스 매핑, 평가 분리 예제를 따른다.

## v1 호환 사용 참고

아래 예제는 **보존된 v1 ZIP**을 사용할 때만 적용한다. 새 v2 Detection에는 적용하지 않는다.

[배포 README](README_DATA_TEMPLATE.md)의 설치/검증/로딩 예제를 따른다. 실제 패키지 안의 README_DATA.md에는 canonical SHA가 채워져 있다. ZIP 수령 후 verify → 실제 원본 경로 설정 → smoke 순서다. 관리자 전체 build를 팀원이 반복하지 않는다.

`mv_analysis/data/team_release.py`의 TeamRelease는 기존 ManifestIndex/SingleViewDataset/FiveViewDataset을 재사용한다. 기존 로더와 승인 CSV를 수정하지 않는다. 통합 canonical을 geometry/label 두 입력으로 분리하여 status 등의 merge 충돌을 피하고, 원본 파일 SHA를 확인한 후 PC별 mtime 차이를 메모리에서만 처리한다.

```python
import os
from mv_analysis.data.team_release import TeamRelease
from mv_analysis.data.adapters import get_adapter

release = TeamRelease(os.environ['MV_DATA_RELEASE'], os.environ['REALIAD_DATA_ROOT'])
dataset = release.dataset(split='train', task='detection', eligible_only=True,
                          adapter=get_adapter('YOLO11'))
sample = dataset[0]
assert sample['metadata']['canonical_manifest_sha256'] == release.sha256
```

이미지는 RGB Float32, 원본→저장 Crop→모델 Adapter 순서다. 마스크는 같은 Crop/NEAREST, BBox는 원점 이동→Clip→Resize/Pad 좌표 변환을 따른다. YOLO는 normalized CXCYWH 0기반 label, TorchVision은 XYXY 1기반 label이다. 원본 좌표 복원에는 sample metadata의 기하 변환 정보를 유지한다. 모델 내부 Resize/Normalize와 외부 Adapter를 중복하지 않는다.

None mask는 정상 마스크와 같지 않다. 특히 NG 미주석은 `detection_trainable=False`이며 detection_collate 기본 strict 검사에서 거부한다. `torchvision_target`은 독립 Crop 좌표 Target만 반환하는 대안이고 이미 Adapter가 바꾼 label에 다시 적용하지 않는다.

## 5시점과 필터

정상 학습에서는 완전한 OK 제품 그룹을 사용할 수 있다. 검출 적격성으로 개별 시점을 걸러 5개가 남지 않으면 FiveViewDataset은 기본적으로 오류를 발생시킨다. NG 제품을 임의로 정상 처리하거나 미주석 시점에 가짜 마스크를 만들지 않는다. `release.dataset(task='all', eligible_only=False, adapter=...)`로 그룹을 유지하고 시점별 타깃 적격성을 Loss 및 평가에서 반영한다. 여러 크기의 원본 Crop은 고정 출력 크기 Adapter 또는 명시적 저장용 Padding이 필요하다.

## 실험 기록

Recorder의 `manifest_sha256`은 `release.sha256`을 사용한다. 기존 crop-only CSV의 SHA와 새 통합 canonical SHA는 서로 다르다. `crop_policy_version`, `model_adapter_version`, class-map, split, 평가 제외 목록도 함께 기록한다. Test 주석을 참조한 수동 Crop의 독립성 위험은 배포 validation 목록으로 보고한다.

## 오류 처리

- ZIP checksum 오류: 수령한 ZIP 해시와 발신자 값을 확인하고 재전송. 내용 직접 수정 금지.
- Dataset SHA 오류: 다른 데이터 버전, 파일 내용 변경 여부 확인. mtime 변경만으로 실패하지 않음.
- 좌표/라벨 오류: 샘플 자동 보정 없이 중단하고 관리자에게 image_id와 오류 전달.
- MISSING_ANNOTATION: 의도된 주석 미제공 상태. 검출 학습에서 제외, 이미지 NG는 유지.
- five-view incomplete: image-level eligibility 필터로 시점이 빠졌는지 확인. Split을 새로 만들지 않음.
- 모델 입력 오류: 공통 독립 Adapter 성공과 실제 모델 런타임 성공은 다름. 담당자가 모델별 계약을 연결·검증.

코드만 있는 Git Clone에서는 원본 데이터와 ZIP이 없으므로 실제 smoke는 불가능하다. 합성 테스트 `uv run --locked pytest -q tests/test_team_data_release.py`는 사설 데이터 없이 실행된다.
