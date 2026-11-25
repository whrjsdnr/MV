# 최종 전처리 검증 결과

검증 대상은 수동 검수가 반영된 preprocessing_metadata_reviewed_v1.csv다. 원본 기준 preprocessing_metadata.csv 및 GT 기반 후보 CSV와 구분했다. 실제151050행이다. 구현·무결성·입력 변환은 검증했으나 데이터 타깃이 모두 깨끗한 상태나12모델 실제 통합 완료로 판정하지 않는다.

## 1. 최종 CSV 선정

선택: /home/geonug/MV/outputs/adaptive_crop_full_v1/preprocessing_metadata_reviewed_v1.csv. SHA-256 `4f70acd7948650979a2ec082176ea8b8bfd7ed0c10408b7a69079feadd873e31`. 수정 시각으로 고르지 않고 원본 기준 CSV 해시, 최신 유효 Crop 승인1594개, 좌표·버전·검수자·시각·정책 해시·원본 파일 식별자가 정확히 일치하는지 대조했다. 다른 유효한 반영본이 없었으며 불일치0이었다. 기준 CSV·승인 Ledger를 수정하거나 CSV를 자동 내보내지 않았다.

제품 GT 승인605개 이력/최신600개와 Crop 승인을 구분했다. Crop 원장은1597개 이력, 최신1595개 항목(승인1594·보류1)이다. 우선 검수 목록 중162개는 기록이 없고 보류1개와 함께 원본C로 유지됐다. 사용자 완료 보고를 전체1757개 Crop 승인으로 확대하지 않았다. 좌표가 바뀐 행1587개, 승인했지만 전체 원본을 유지한 행7개다. 제품 GT가 있다는 이유로 미승인 Crop을 반영하지 않았다.

[선정 근거](../outputs/data_loader_validation_v1/manifest_selection.json), [원본 지문](../outputs/data_loader_validation_v1/manifest_fingerprint.json), [승인 대조 오류](../outputs/data_loader_validation_v1/preprocessing_metadata_reviewed_v1_errors.csv).

## 2. 전체 파일·좌표 무결성

JPG151050개를 실제 픽셀로 디코딩하고 원본 SHA·파일 stat·실제 크기를 확인했다. 제공 PNG51329개도 실제로 읽고1024원본 크기와 대조했다. 존재·헤더 확인만 한 결과가 아니다. 경로·ID중복0, 이미지 디코딩 오류0, 마스크 파일 디코딩·크기 오류0, 유효하지 않은 Crop0이다. 원본좌표 XYXY 끝exclusive이며 자동 보정·반올림·좌표 변경은 하지 않았다.

151050행 중 수동 승인된 직사각형1585개는 UI에서 허용된 명시적 예외다. 기존 정사각형 알고리즘을 다시 적용해 좌표를 바꾸지 않았다. C149463개는 올바른 원본 전체 좌표이며 HUMAN_CROP1587개는 승인 좌표와 일치했다.

전수 디코딩은 CPU3스레드·1000행 Parquet152개 체크포인트를 사용했다. 먼저1000장 Smoke를 확인하고 나머지150050장을 이어서 처리했다. 전체 재개 실행에서 약943.85초가 걸렸으며 원본 이미지 배열 전체를 적재하지 않았다. 완료 파티션은 입력·코드·정책 해시가 같을 때 재사용한다.

## 3. 선언 제품 그룹과 Split

| split | images | declared_products | image_fraction |
| --- | --- | --- | --- |
| test | 22660 | 4532 | 0.1500166 |
| train | 105735 | 21147 | 0.7 |
| validation | 22655 | 4531 | 0.1499834 |

30개 품목, 선언 제품30210개, C1~C5 각각30210장이다. 모든 선언 제품에서5시점이 있고 중복 시점·그룹 Split 누수0이다. JPEG 바이트 해시가 같은 이미지의 Split 교차도0이다. 기존 product_id와Split을 그대로 사용했고 물리적 제품 동일성이 독립 검증됐다고 주장하지 않는다.

[품목·상태별 통계](../outputs/data_loader_validation_v1/category_status_summary.csv), [시점·마스크 제공](../outputs/data_loader_validation_v1/view_annotation_coverage.csv).

## 4. 주석 상태와 탐지 학습 계약

| contract | images |
| --- | --- |
| OK_NEGATIVE | 72840 |
| SUPERVISED_VALID | 51288 |
| MISSING_ANNOTATION | 26881 |
| EMPTY_NG_REVIEW | 34 |
| INVALID_TARGET | 7 |

탐지 학습에 사용할 수 있는 이미지는 124,128개(정상 Negative72,840 +유효 불량51,288)다. 나머지26,922개는 정상으로 재분류하지 않고 별도 상태로 반환한다. 마스크 미제공 전체99721개 중 정상72840개와NG26881개를 구분한다. PRESENT_EMPTY34개는 원본에 실제 파일이 제공됐지만 양성 픽셀이 없는NG이며 검토 대상이다.

NG+MISSING은 mask=None·MISSING_ANNOTATION, NG+PRESENT_EMPTY는 빈Tensor·EMPTY_NG_REVIEW다. INVALID는 손상·크기불일치 마스크 상태이며 실제0건, 합성 테스트에서 검증했다. Crop으로 결함이 전부 사라지면 원본 NG와PRESENT_POSITIVE를 유지하고 INVALID_TARGET·all_defects_cropped_out을 기록하도록 구현했다. 실제 전부 소실은0장이었다.

## 5. 실제 발견된7개 주석 문제

fire_hood의 HS 디렉터리에 QS 파일명이 들어간7개 이미지가 canonical defect_type=UNRESOLVED였다. 양성 마스크는 유효하지만 검증된 클래스 BBox가 없다. 마스크 손상이나 새로운 Crop 오류가 아니며 HS/QS 중 하나를 추측해 부여하거나 BBox를 새로 저장하지 않았다. Dataset은 INVALID_TARGET·detection_trainable=False로 반환하고 엄격한 detection collate가 학습 입력을 거부한다. 이진 NG 및 위치 마스크 평가 가능 여부와 다중클래스 탐지 타깃 사용 가능 여부를 구분한다.

[7개 원인 목록](../outputs/data_loader_validation_v1/unresolved_defect_class_conflicts.csv), [주석 오류](../outputs/data_loader_validation_v1/annotation_errors.csv), [실제7개 로딩 확인](../outputs/data_loader_validation_v1/target_quarantine_smoke.json).

## 6. Crop 후 결함·BBox 감사

승인된 기존 Crop에서 양성 마스크 일부 손실43장(Train29, Validation10, Test4)을 관측했다. 원래 검수 경고52건은 제품 BBox 손실까지 포함하므로 마스크 손실43과 같은 지표가 아니다. 결함 전부 소실0, BBox 일부Clip43개, 면적0으로 제거된BBox0개다. 클래스ID는 원본0..7을 유지하며60629개 원본 BBox의 defect_type 매핑 오류0이었다.

[43개 마스크 손실](../outputs/data_loader_validation_v1/crop_defect_losses.csv), [완전 소실 목록](../outputs/data_loader_validation_v1/all_defects_cropped_out.csv), [원본 클래스 검사](../outputs/data_loader_validation_v1/source_class_mapping_errors.csv). 좌표를 사후 변경하지 않았다. 일부 손실을 숨기거나 좋은 전처리로 확정하지 않는다.

## 7. 평가 독립성

Test189개 수동 Crop에서 제품 GT/마스크 참조가 기록돼 있다. 자동 Gate가 Test GT로 좌표를 재계산한 것은 아니지만 사람이 정답을 보조해 만든 전처리이므로 평가 독립성을 보장할 수 없다. 전체 수동 승인 중247개는 정답 참조가 기록되지 않았으나 외부에서 정답을 보지 않았다는 증명은 아니다. 기록 가능한 사실과 미확인 판단 근거를 구분했다.

[검수 근거 및 위험](../outputs/data_loader_validation_v1/manual_review_evaluation_risks.csv). Dataset은 manual_annotation_assisted·requires_evaluation_leakage_review를 반환하며 이 위험을 자동으로 숨기거나 Split을 바꾸지 않는다.

## 8. 실제 로딩과 입력 변환

| metric | value |
| --- | --- |
| images | 315 |
| products | 63 |
| categories | 30 |
| views | {'C1': 63, 'C2': 63, 'C3': 63, 'C4': 63, 'C5': 63} |
| splits | {'train': 220, 'test': 55, 'validation': 40} |
| statuses | {'NG': 165, 'OK': 150} |
| mask_states | {'MISSING': 194, 'PRESENT_POSITIVE': 120, 'PRESENT_EMPTY': 1} |
| policies | {'C': 303, 'HUMAN_CROP': 12} |
| models | 12 |
| adapter_cases | 360 |
| five_view_batch_shape | [2, 5, 3, 256, 256] |
| single_view_batch_shape | [2, 3, 256, 256] |

실제315장/63제품,30품목,5시점,3Split,정상150·불량165를 로딩했다. 마스크 MISSING194·PRESENT_POSITIVE120·PRESENT_EMPTY1을 포함했다. 실제 A/B 정책 행은 최종 CSV에 없어 NOT_PRESENT로 기록하고 좌표를 만들어 가장하지 않았다. C303장·HUMAN_CROP12장을 검증했다. A/B 라벨의 저장좌표 사용은 합성 데이터에서 확인했다.

12개 Adapter에서 품목별1장씩 총360개 입력 변환을 실제CPU로 실행했다. Single 배치(2,3,256,256), Five 배치(2,5,3,256,256)를 확인했다. Native 탐지 입력의 가변 크기는 명시적 storage padding 후 unpad하여 원래Tensor와타깃이 정확히 복원됨을 실제10시점에서도 확인했다.

## 9. 테스트와 구현 한계

전체 pytest 142 passed, failed0, NumPy 테스트 매개변수 deprecation warning1개다. 합성 정상·불량·누락/빈/잘못된 마스크, 좌표·Clip·Scale·CXCYWH·Normalized좌표·RGB·classID·5시점 순서·Split·Collate·승인 대조·중복·디코딩 실패·재현성을 검사했다. 모델별 입력 크기와 이중Normalize/CenterCrop 차단도 확인했다.

실제 Smoke에서 YOLO11/RT-DETRv2 Bilinear Tensor Resize가 최대1.000000119를 만들어 범위 검사가 실패했다. Resize의 부동소수점 경계 오차만0..1로 안정화했고 후속 정규화·255스케일을 적용했다. 원본 Crop 좌표를 바꾸지 않았으며 수정 후 실제 Smoke와회귀 테스트가 통과했다.

모델 실제 forward·가중치·학습·성능 비교·증강 정책 개발은 수행하지 않았다. 모델 통합은12개 모두UNVERIFIED다. PatchCore/Dinomaly/INP-Former의 추가CenterCrop은 기본으로 끄고 최종 입력 크기로 Resize하는 별도 manifest-preserving 실험 조건이다. 공식 baseline과 같은 조건이라고 부르지 않는다.

## 10. 결과 파일과 재현 명령

선택·전체실제디코드·Smoke·최종 문서는 scripts/select_final_preprocessing.py, validate_final_preprocessing_decode.py, smoke_test_data_loaders.py, validate_known_loader_cases.py, finalize_data_loader_validation.py를 사용한다. 선택과완료 보고서는 기존 증거를 덮어쓰지 않으며 decode단계만 체크포인트로 재개한다.

[검증 JSON](../outputs/data_loader_validation_v1/validation.json), [실제 Shape](../outputs/data_loader_validation_v1/sample_shapes.json), [전수 행별 감사](../outputs/data_loader_validation_v1/per_image_decode_validation.csv), [탐지 감독 가능 여부](../outputs/data_loader_validation_v1/annotation_contract.csv), [구현 사용법](DATA_LOADER_IMPLEMENTATION.md). PDF/PPT·Crop이미지 생성0, 원본·승인·최종좌표 수정0, 모델학습0, 유료API0, GitHubPush0.