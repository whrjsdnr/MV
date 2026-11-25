# Real-IAD 공통 데이터 로더 구현

구현 위치는 기존 Python 패키지와 맞춘 mv_analysis/data/다. src/를 새로 만들지 않았으며 모델·Crop 추정·증강 코드를 호출하지 않는다. 최종 CSV의 저장된 좌표만 읽는다.

## 입력 파일과 버전

최종 전처리 CSV에는 좌표·경로·Split만 있고 학습 정답은 별도 canonical image_metadata_with_split.csv, 기존 defect_bboxes.csv 및classes.json에서image_path 기준으로 결합한다. 경로 문자열로 정답을 추정하지 않는다. 기존 단일 CSV Crop용 helper mv_analysis.crop_manifest는 유지했고, 학습용 Dataset은 주석 파일을 명시적으로 사용한다. source_relative_path/category/view/product_id/split이일치하지 않으면 실패한다.

최종 CSV와 모든 입력파일 해시는 outputs/data_loader_validation_v1/manifest_fingerprint.json에 고정했다. Dataset metadata에manifest_sha256·policy_version·policy_sha256을 반환한다. 좌표오류·중복·제품Split누수는 ManifestError로 막고 자동 수정하지 않는다. 미주석·비정상 탐지 타깃은 빈 정상으로 바꾸지 않는다.

## 기본 Single-view 예제

```python
from torch.utils.data import DataLoader
from mv_analysis.data import (ManifestIndex, SingleViewDataset, get_adapter,
                              single_view_collate)

index = ManifestIndex(
    "outputs/adaptive_crop_full_v1/preprocessing_metadata_reviewed_v1.csv",
    data_root="/home/geonug/MV/dataset", require_complete=True,
)
dataset = SingleViewDataset(index, split="train", task="anomaly",
                            adapter=get_adapter("PatchCore"))
loader = DataLoader(dataset, batch_size=4, num_workers=0,
                    collate_fn=single_view_collate)
batch = next(iter(loader))
# images: (B,3,224,224). Train anomaly defaults to OK only.
```

Dataset은image float32 CHW, ID·제품·품목·시점·Split·원본OK/NG, 원본(H,W), exclusive Crop XYXY, mask/None, mask_status, boxes/labels, detection_status, detection_trainable, localization_valid, metadata를 반환한다. Native 입력은RGB0..1이며 Adapter를 붙이면 모델별 값 범위·크기로 바뀐다. 정상·불량에 따른 픽셀 전처리 차이는 없다.

## 탐지 학습용 예제

```python
from mv_analysis.data import detection_collate

dataset = SingleViewDataset(
    index, split="train", task="detection",
    adapter=get_adapter("Faster R-CNN"), detection_valid_only=True,
    eligibility="outputs/data_loader_validation_v1/annotation_contract.csv",
)
loader = DataLoader(dataset, batch_size=2, num_workers=0,
                    collate_fn=detection_collate)
images, targets = next(iter(loader))
# RGB float0..1 image list; absolute XYXY and labels1..8.
# No model forward is performed here.
```

detection_collate 기본strict=True는MISSING_ANNOTATION/EMPTY_NG_REVIEW/INVALID_TARGET을 거부한다. detection_valid_only는 검증된 현재 Manifest의 eligibility표로 명시적으로 필터한다. 이는 Split재생성이 아니다. 추론·감사에서 미주석 NG도 로딩할 때는strict=False를명시하고 trainable플래그를 유지한다. Default PyTorch collate는None마스크·가변BBox에맞지 않으므로 제공한collate를 사용한다.

원본 defect class는0..7이며TorchvisionFasterR-CNN/RetinaNet에서만+1로1..8을사용한다. 해당모델의8개결함과background head는9classes구성이필요하다. YOLO/RT-DETR/YOLOS/ViTDet는0..7을유지한다. 원본 canonical_labels도보존한다. NG+MISSING은정상Negative가아니고, 빈NG마스크는별도검토상태다.

## Five-view 예제

```python
from mv_analysis.data import FiveViewDataset, five_view_collate

single = SingleViewDataset(index, split="validation", task="all",
                           adapter=get_adapter("EfficientAD-S"))
five = FiveViewDataset(single)  # partial views OFF
loader = DataLoader(five, batch_size=2, num_workers=0,
                    collate_fn=five_view_collate)
batch = next(iter(loader))
# images: (B,5,3,256,256), C1,C2,C3,C4,C5
# Each view retains its own target/mask/None.
```

선언제품은5시점완전성과한Split을검사한다. 시점누락·로딩실패는기본오류다. allow_partial=True는명시적으로요청할때만K개이미지와missing_or_failed_views를반환하며기본Fivecollate는이를거부한다. 같은제품마스크를합치지않는다.

## 가변 크기 모델의5시점 저장 Padding

```python
from functools import partial
from mv_analysis.data import flatten_five_view_batch

single = SingleViewDataset(index, split="test", task="all",
                           adapter=get_adapter("Faster R-CNN"))
five = FiveViewDataset(single, pad_storage=True)
loader = DataLoader(five, batch_size=2,
                    collate_fn=partial(five_view_collate, pad_storage=True))
batch = next(iter(loader))
# Inference/audit only: invalid per-view supervision remains flagged.
images, targets = flatten_five_view_batch(batch, strict_detection=False)
# Remove storage padding before passing images to a native model.
```

Padding은배치저장용으로만명시적허용하고BBox·마스크·정규화좌표는각시점의유효(H,W)에그대로둔다. flatten_five_view_batch가원래크기이미지를정확히복원한다. 기본strict_detection=True는미주석/무효시점이탐지훈련Negative로펼쳐지는것도차단한다. 정상모델native입력으로저장패딩을그대로보내면안된다. 이미학습가능시점만필터하면5시점이깨질수있으므로자동으로부분제품을허용하지않는다.

## 12개 입력 Adapter 계약

| model | resize | size | external_normalization | range | bbox | normalized_bbox | label_offset |
| --- | --- | --- | --- | --- | --- | --- | --- |
| PatchCore | square | 224 | imagenet | ImageNet-standardized | xyxy | False | 0 |
| EfficientAD-S | square | 256 | imagenet | ImageNet-standardized | xyxy | False | 0 |
| UniAD | square | 224 | imagenet | ImageNet-standardized | xyxy | False | 0 |
| HVQ-Trans | square | 224 | imagenet | ImageNet-standardized | xyxy | False | 0 |
| Dinomaly | square | 392 | imagenet | ImageNet-standardized | xyxy | False | 0 |
| INP-Former | square | 392 | imagenet | ImageNet-standardized | xyxy | False | 0 |
| Faster R-CNN | delegated | NA | none | 0..1 | xyxy | False | 1 |
| RetinaNet | delegated | NA | none | 0..1 | xyxy | False | 1 |
| YOLO11 | letterbox | 640 | none | 0..1 | cxcywh | True | 0 |
| RT-DETRv2 | square | 640 | none | 0..1 | cxcywh | True | 0 |
| YOLOS | short_side | 800 | imagenet | ImageNet-standardized | cxcywh | True | 0 |
| ViTDet | long_side_pad | 1024 | none | 0..255 | xyxy | False | 0 |

입력공통은RGBfloat32 CHW0..1이다. mask=None은유지하고유효마스크만NEAREST로같은기하변환을적용한다. Bilinear이미지보간은Tensor구현으로align_corners=False, YOLO외antialias=True이며저자PIL/다른버전과비트일치를주장하지않는다. YOLO는640 LetterBox/pad114, RT-DETR는640정사각, YOLOS는짧은변800/긴변1333상한, ViTDet는긴변1024후저장입력1024패딩이다.

FasterR-CNN/RetinaNet은native크기·RGB0..1·외부Normalize없음으로모델내부Resize800/1333및ImageNetNormalize에위임한다. ViTDet은RGB0..255 float32입력브리지이며내부mean/std수치·실제mapperdtype통합은UNVERIFIED다. RT-DETRbackbone내추가정규화도UNVERIFIED다. 12개모델실제통합을실행하지않았다.

PatchCore224, Dinomaly/INP-Former392는저장Crop을보존하기위해공식추가CenterCrop을끄고직접Resize하는실험조건이다. 공식기본256→224/448→392CenterCrop조건과같지않다. center_crop=True는이프로필에서거부한다. Adapter를다시적용하거나이미정규화된Tensor를넣으면거부해이중Normalize를막는다. 모델내부전처리와외부변환을둘다실행하지말아야한다.

소스repo/commit/파일은adapter_contracts.json과model_source_integrity.json에기록했다. 기존 [MODEL_INPUT_REQUIREMENTS.md](MODEL_INPUT_REQUIREMENTS.md)를근거로설정했다. 캐시텍스트와해시확인은실제modelforward검증과다르다. Ultralytics/Detectron2/각저자훈련기용최종batchdictionary연동은UNVERIFIED이며제공되는것은독립입력변환과공통Dataset타깃이다.

## 타깃 기하와 작은 결함

원본BBoxXYXY에서Crop원점을빼고범위Clip한뒤면적0을제거하고원래classID를같은keepmask로유지한다. 모델별Resize·LetterBoxPadding을동일하게적용하고CXCYWH·Normalized변환은마지막Adapter에서수행한다. 원본CSV좌표는변경하지않는다.

mask_status는원본제공상태를유지한다. Crop또는Resize로양성마스크가사라지면별도all_defects_cropped_out/resize_erased_all_positive_mask를기록한다. mask_status를MISSING이나정상으로바꾸지않고image-level NG도유지한다. NN다운샘플은작은결함소실을보장해막을수없으며합성1픽셀사례에서소실을정확히기록하는것을검증했다. 모델검출성능향상을의미하지않는다.

## 실행한 검증과 재현

전체pytest 142개통과, 실제315장이미지·63제품,12Adapter×30품목=360CPU입력변환,Single/Five배치,실제7개INVALID_TARGET차단을확인했다. 원본151050JPG·51329PNG는별도전수디코딩감사로확인했다. 실제정책A/B와손상마스크는현재최종CSV/데이터에없어실데이터검증완료로꾸미지않고합성테스트로분리했다.

```bash
uv run --offline pytest -q
# Completed evidence is protected from overwrite.
uv run --offline python scripts/validate_final_preprocessing_decode.py
```

최초단계는select_final_preprocessing.py → validate_final_preprocessing_decode.py --max-batches 1 → 같은명령에서--max-batches제거 → smoke_test_data_loaders.py → validate_known_loader_cases.py → finalize_data_loader_validation.py다. 완료선정·Smoke·최종보고서는보존하고새버전으로재실행한다. Checkpoint는입력·코드해시가같을때만재사용한다. runtime문제·클래스충돌을좌표수정이나정답추정으로덮지않는다.