# 팀 배포 Canonical 데이터 계약 — v2

**최신 v2는 이상탐지 approved_crop / 객체탐지 original_full을 분리한다.** 승인 Crop 필드는 보존되지만 Detection 입력 좌표를 이동시키지 않는다. v1은 별도 ZIP과 호환 로더로 보존한다. 실제 사용 예제는 [최신 배포 README](README_DATA_TEMPLATE.md)에 있다.

v2 추가 필드: anomaly_image_policy, detection_image_policy, detection_annotation_policy, annotation_coordinate_space, product_bbox_source, release_version, source_manifest_sha256. `annotation_status`는 원본 결함 주석 상태, `crop_annotation_status`는 기존 Crop 기준 상태다. 원본과 Crop BBox 열을 함께 보존하지만 D1/D2 Target은 원본 x0/y0/x1/y1만 사용한다.

D1은 defect_* 0..7 그대로다. D2는 기존 defect_* 0..7 + 새 product_* 8..37, COCO/TorchVision은 각각 +1이다. 제품 단독 클래스 0..29는 별도 네임스페이스다. OK/NG는 객체 클래스가 아니다.

제품 주석에는 bbox_xyxy, bbox_source, annotation_quality, human_verified, coordinate_space, selected_for_d2, d2_class_id를 추가했다. 이미지당 사람 GT→자동 제안→Crop 근사 순으로 1개를 선택하되 모든 원래 후보를 유지한다. Pseudo는 사람이 확인한 GT가 아니다. `default_detection_target=False`는 D1 기준이고 D2는 selected_for_d2를 명시적으로 읽는다.

적격성 추가: detection_defect_train/eval_eligible(D1), detection_product_train/eval_eligible(제품 감독), detection_joint_train/eval_eligible(D2 통합), product_gt_diagnostic_eligible, detection_joint_diagnostic_eligible. 제품만 감독 가능한 NG 미주석은 일반 D2 통합 적격과 구분한다. 독립 제품 평가 GT가 없어 product/joint 독립 eval은 False이고 기존 600 GT의 Val/Test 부분은 진단용이다. 기존 detection_train/eval_eligible 열은 D1의 호환 별칭이다.

## v1에서 이어받은 공통 필드와 차이

아래는 보존된 v1 공통 필드 설명이다. v1의 결함-only 기본 Target/공통 Crop 규칙은 v2 Detection에 적용하지 않는다. v2에서는 위 정책과 최신 README가 우선한다.

배포명은 `MV_TEAM_DATA_RELEASE_v1`이다. 기존 내부 `preprocessing_metadata_reviewed_v2.csv`를 수정하지 않고, 그 좌표·제품 그룹·Split과 파일명 기준 클래스 보정 정보를 합친 별도 배포 테이블을 만든다. 선택 근거는 수정 시각이 아니라 기존 release descriptor SHA, 최신 유효 승인 이벤트, 43장 좌표 변경 목록의 대조다.

## 이미지 테이블

`manifests/canonical.csv`는 이미지당 한 행이다. 열의 실제 dtype은 배포 ZIP의 `schemas/annotation_schema.json`에 있다.

|열|의미/검증|
|---|---|
|image_id|유일한 이미지 식별자. 기존 ID 유지|
|product_id|기존 선언 제품 그룹. 물리 제품 동일성의 독립 검증은 아님|
|category/view/split|30품목 / C1~C5 / train,validation,test. Split 재생성 금지|
|image_path,source_relative_path,original_path|모두 데이터 루트 기준 동일 POSIX 상대 경로. 개인 절대 경로 없음|
|status|OK/NG 이미지 상태. 추론 입력으로 사용 금지|
|defect_class|NG의 기존 결함 종류. OK는 빈 값|
|has_mask,mask_path,mask_status|제공 여부/상대 경로/양성·빈·미제공·무효 상태|
|crop_x0,y0,x1,y1|원본 기준 정수 XYXY, 끝 좌표 exclusive|
|crop_width,height|끝 좌표−시작 좌표. 승인 직사각형을 정사각형으로 강제 수정하지 않음|
|selected_policy,crop_policy|저장된 정책. 로더에서 다시 선택하지 않음|
|crop_review_status,latest_review_state|CSV 반영 승인 상태와 원장 최신 상태. PENDING은 승인 아님|
|policy_version,policy_sha256|기존 정책/승인 revision 식별자 유지|
|source_fingerprint|작성 PC의 크기/mtime 증거. 다른 PC에서는 콘텐츠 SHA 검증 후 메모리 연결값으로 대체|
|source_sha256,mask_sha256|원본 파일 콘텐츠 식별자. 원본 파일 자체는 배포하지 않음|
|image_verification|이전 전수 디코딩 캐시 재사용인지 현재 디코딩인지 명시|
|image_valid,target_geometry_valid|파일/좌표 유효성. 오류는 자동 보정하지 않음|
|annotation_status|OK_NEGATIVE, SUPERVISED_VALID, MISSING_ANNOTATION, EMPTY_NG_REVIEW, INVALID_TARGET|
|source_box_count,crop_clipped_boxes,crop_removed_boxes|원본 성분/부분 Clip/완전 제거 수|
|original_positive_pixels,cropped_positive_pixels,crop_mask_loss|제공 마스크의 평가용 보존 점검. Crop 선택 입력 아님|
|manual_annotation_assisted,requires_evaluation_leakage_review|정답 참조 검수와 평가 독립성 위험. False가 외부 GT 미사용의 증명은 아님|
|release_version|배포 계약 식별자|

## 객체/제품 주석

`annotations/defect_boxes.csv`는 마스크 8연결 성분당 한 행이다. `bbox_id`는 `image_id:cc:component_id`이고 `x0,y0,x1,y1`은 원본, `crop_bbox_*`는 Crop 원점 이동 및 Clip 후 좌표다. `kept_after_crop=False`도 감사 목적으로 보존하며 학습 Target에는 넣지 않는다. `component_area`는 원본 양성 픽셀 수로 BBox 직사각형 면적과 다르다. 작은 성분 필터는 없다.

기존 클래스 순서 AK/BX/CH/HS/PS/QS/YW/ZW의 0~7을 유지한다. COCO/TorchVision은 1~8을 사용한다. 모델 배경 0은 정상 객체 클래스가 아니다. 폴더 HS/파일명 QS 충돌 10장은 파일명 QS 정책이다.

`annotations/product_boxes.csv`는 source_type을 반드시 구분한다.

- HUMAN_VERIFIED_GT: 원장의 명시적 승인 기록이 있는 제품 BBox. 결함 주석이 아님.
- AUTOMATIC_PROPOSAL: OpenCV 제안. 기존 승인 이미지와 같은 행이어도 자동 결과 자체는 GT가 아님.
- CROP_APPROXIMATION: 저장 Crop 영역. 제품 외형 정답이 아닌 근사치.

모두 `default_detection_target=False`다. 기본 검출 클래스에 normal/product를 추가하지 않는다. 별도 실험에서는 양쪽 상태에 같은 제품 주석 기준을 적용하고 상태 분류 Head/Loss를 별도 정의해야 한다.

## 학습 적격성

`manifests/eligibility.csv`는 canonical의 image_id와 1:1이다. 영상 전처리는 라벨에 따라 바뀌지 않는다. 적격성은 학습/평가 대상 선정에만 사용한다.

|열|기본 조건|
|---|---|
|anomaly_train_eligible|Train + 유효 OK_NEGATIVE|
|anomaly_image_eval_eligible|Validation/Test + 유효 영상/좌표. NG 미주석도 NG 유지|
|anomaly_pixel_eval_eligible|Validation/Test + 유효 OK 또는 양성 주석 NG + Crop 주석 손실 없음|
|detection_train_eligible|Train + OK_NEGATIVE 또는 SUPERVISED_VALID + Crop 주석 손실 없음|
|detection_eval_eligible|Validation/Test + 위와 같은 타깃 조건|
|detection_trainable|Split과 무관한 기본 검출 타깃 유효성. 기존 로더 연결용|
|exclusion_reason|MISSING_ANNOTATION, EMPTY_NG_REVIEW, CROP_ANNOTATION_LOSS, FILE_OR_GEOMETRY_INVALID 등|

Train/평가 Split 조건 때문에 False인 경우까지 오류로 취급하지 않는다. image_eval 적격성이 pixel_eval 또는 detection 적격성을 의미하지 않는다. 일부 시점만 검출 적격인 제품은 Five-view 묶음을 유지한 뒤 시점별 supervised loss 마스크를 명시한다.
