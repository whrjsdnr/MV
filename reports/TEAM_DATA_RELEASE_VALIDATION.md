# Real-IAD 팀 데이터 배포 v2 최종 검증

최신 정책: **이상탐지 approved_crop / 객체탐지 original_full / D1 defect_only / D2 product_and_defect**. 아래 v1 보고서는 이력으로 보존한다. HEAD c4b4a46의 기존 공통 로더·공식 모델 코드를 수정하지 않고 새 배포 연결 계층을 확장했다. Commit/Push/학습/GPU 실행은 없다.

## v2 파일과 해시

- [데이터 ZIP](../outputs/team_data_release_v2/MV_TEAM_DATA_RELEASE_v2.zip): **24,040,260 bytes** (24.04 MB).
- ZIP SHA-256: `39acd673b0042e5b626a8e84fa25f0d1190db02b56f6f1dded4b5c8886dada43`.
- Canonical SHA-256: `98cd47086afc939fc960b92e32ee70f38a13cfde54df71b7a54b5d68aa0222ed`.
- [새 도구 ZIP](../outputs/team_data_release_v2/tooling_final/MV_TEAM_DATA_TOOLS_v2.zip): 63,926 bytes, SHA-256 `f4c6090fc8de12be93c02708a3a3cb472a27851812e90ae9f61d824de9879e00`.
- 원본 v1 ZIP, v1 통합 canonical, 기존 승인 좌표·원장은 보존한다. 데이터 ZIP은 16개 파일이며 원본 JPG/PNG, 가중치, 승인 Ledger를 포함하지 않는다.

## v1과 v2의 차이

|구분|v1|v2|
|---|---|---|
|이상탐지 입력|승인 Crop|동일 승인 Crop|
|객체탐지 입력|승인 Crop|원본 전체 실제 H/W|
|D1|Crop 기준 결함 Target|원본 기준 결함 Target|
|D2|기본 Target에 제품 미포함|명시적 제품+결함 정책, 출처/품질 필수|
|클래스|기존 결함8 + 이미지상태|D1 결함8, D2 결함8+제품30, 이미지상태 별도|
|제품 평가|확장 자료|개발 GT 진단과 독립 평가 적격성 분리|
|예측 복원|Crop 원점 이동+Scale/Pad 복원|검출은 원점0 + Scale/Pad 복원|

기존 `TeamRelease`는 v1만 지원하고 v2를 잘못 읽으면 오류를 낸다. `TeamReleaseV2.dataset`는 task와 image_policy를 일치시키며 detection+approved_crop을 거부한다. 원본 정책은 기존 ManifestIndex 행의 **메모리 사본만** full-frame으로 설정하여 기존 디코딩/기하/마스크 로더를 재사용한다. 승인 좌표는 canonical 및 metadata.approved_crop_xyxy에 그대로 남는다.

## 실제 데이터·주석 재확인

151,050장 / OK72,840 / NG78,210 / 선언제품30,210 / 카테고리30 / C1~C5. 검증된 metadata의 실제 원본 크기는 151,050장 모두1024×1024다. 로더 구현은 크기를 하드코딩하지 않고 행과 디코딩 결과를 비교한다.

v1의 제공 PNG51,329장 재검증과 BBox60,636개를 재사용했다. 새 전체 이미지/해상도 분석이나 마스크 전수 재계산은 없다. source v1 SHA와 파일별 체크섬·좌표·그룹·참조·정책을 v2에서 다시 검사했다. 43장 재검수 반영 및 1,594건 Crop 승인/600건 제품 GT 대조 근거도 보존했다. v1 source Crop 주석 손실0, 최종 v2 D1/D2는 원본 주석 좌표여서 Crop으로 결함을 제거하지 않는다.

NG 미주석26,881, 제공 빈마스크NG34는 기본 D1/D2 통합 학습에서 제외한다. 상태는 NG이고 없는 결함 BBox는 UNKNOWN이다. D1 OK는 빈 Target, D2 OK는 제품 Target만 있다. normal 객체 클래스를 추가하지 않는다. 기존 결함 AK0/BX1/CH2/HS3/PS4/QS5/YW6/ZW7은 유지하며 D2 제품은8..37, COCO/TorchVision은+1이다.

## 적격 수와 제품 라벨 한계

|Split|전체|이상탐지 Train|D1 Train|D1 평가(주석 유효)|제품만 Train 후보|D2 통합 Train|제품 독립 평가|제품 개발 GT 진단|D2 통합 진단|
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
|Train|105,735|50,930|87,077|0|105,735|87,077|0|0|0|
|Validation|22,655|0|0|18,416|0|0|0|290|243|
|Test|22,660|0|0|18,642|0|0|0|310|256|

이상탐지 Val/Test 영상 평가45,315, 픽셀 평가37,058이다. D1의 주석 유효 평가 적격은 미사용 독립 데이터의 증명이 아니다. 기존 탐색·검수의 사용 이력을 별도로 고려해야 한다.

저장된 제품 후보는 사람GT600, 자동제안600, Crop근사151,050이다. D2 선택은 사람GT600 + Crop근사150,450이다. 자동제안600은 같은 이미지의 사람GT에 우선순위가 밀려 선택0이며 원래 후보는 삭제하지 않는다. 사람GT는 Validation290/Test310, Train0이다. 따라서 **D2 Train87,077장의 제품 주석은 전부 Crop 기반 Pseudo-label**이다.

전체 선택 제품 박스 중 **148,872/151,050개는 원본 전체 범위**다. 이는 제품 외형을 정밀하게 감싼 GT가 아니다. 이 자료로 제품 위치 정확도를 주장하거나 Pseudo끼리의 높은 mAP를 실제 제품 검출 성능으로 해석하면 안 된다. 기존 사람GT600개도 Crop 정책 개발에 사용됐으므로 독립 최종 제품 평가 적격은0이다. D2 개발 진단은 이 한계를 명시하고 수행할 수 있지만 최종 성능 판정에는 새 독립 사람 GT가 필요하다.

제품만 감독 가능105,735장과 D2 통합87,077장을 혼동하지 않는다. NG 미주석 제품을 일반 D2 Loss에 넣으면 결함이 배경으로 학습될 수 있다. 부분 주석 무시 Loss를 별도로 구현하지 않았으므로 기본 통합 Train에서 제외한다.

근거: [v2 검증](../outputs/team_data_release_v2/MV_TEAM_DATA_RELEASE_v2/validation/validation.json), [Split별 적격](../outputs/team_data_release_v2/MV_TEAM_DATA_RELEASE_v2/validation/split_eligibility.csv), [class map](../outputs/team_data_release_v2/MV_TEAM_DATA_RELEASE_v2/schemas/class_mapping.json).

## 코드·검증 범위

- v1 공통 모듈의 버전 분기/검증을 확장하고 `team_release_v2.py`에서 입력 정책·D1/D2·제품 출처·적격성·원본 주석 export를 구현했다.
- `release_smoke_v2.py`는 실제 원본/마스크·세 정책·5시점·6검출 Adapter 좌표 왕복 및 내부 점검용 주석 그림을 검사한다. 모델 예측/학습 그림이 아니다.
- v2 합성 회귀16개를 추가했다. v1 포함 전체 **223 passed, 1 warning**. 기존 NumPy timedelta 경고는 남아 있다. 테스트는 실제 승인 원장을 수정하지 않는다.
- ZIP CRC/파일별 SHA/16개 파일 집합/참조/ID/클래스/좌표/Split/5시점/적격성을 새 임시 폴더에 해제해 통과했다. [해제 검사](../outputs/team_data_release_v2/extraction_validation.json).
- 깨끗한 c4b4a46 코드 사본에 TOOLS 설치기로 새12파일 설치, 독립 .venv에 `uv sync --locked --offline`170패키지 설치 성공. 기존 캐시 사용이며 인터넷 cold install과 실제 팀원4명 PC 설치를 의미하지 않는다.

### 실제 로딩·좌표·원본 주석 export 완료

[실제 smoke 결과](../outputs/team_data_release_v2/actual_smoke.json): 30품목,108선언제품,540고유이미지. 모든 C1~C5와 Train/Validation/Test, OK/NG, 양성/빈/미제공 마스크, 제품GT/Pseudo,43장 재검수 그룹을 포함했다.

|정책|실제 로딩 이미지|제품 그룹|원본 전체 입력|5시점 배치|
|---|---:|---:|---:|---|
|이상탐지|280|56|저장 Crop에 따름|(2,5,3,256,256)|
|D1|540|108|540/540|(2,5,3,640,640)|
|D2|540|108|540/540|(2,5,3,640,640)|

이상탐지의 Train NG는 기본 정상 학습 필터로 제외되어 280장이다. D1/D2 원본 입력 크기는 실제1024×1024를 확인했고, 6개 검출 Adapter의 대표 BBox 원본 좌표 왕복 오차는 모두0px였다. 마스크 원본 복원은329양성픽셀과 Crop 밖 미관측 영역을 유지했다. 합성 비정사각형/작은 성분/원본 범위·정규화 테스트도 포함된다. 실제 모델 출력으로 성능을 평가한 결과는 아니다.

내부 좌표 그림4장을 실제로 열어 원본/이상탐지 Crop/D1 결함/D2 제품+결함을 점검했다. 제품GT와 Crop근사가 구분되어 표시되고 NG 미주석은 결함 박스가 없는 NG로 표시된다. 새 사람 승인이나 제품 GT를 만들지 않았다. 그림은 ZIP에 넣지 않는다.

- [사람 제품GT/OK](../outputs/team_data_release_v2/figures/coordinate_case_00.png)
- [Crop된 이상탐지와 원본 D1/D2의 양성 결함](../outputs/team_data_release_v2/figures/coordinate_case_01.png)
- [NG 위치주석 미제공](../outputs/team_data_release_v2/figures/coordinate_case_02.png)
- [전체 프레임 Pseudo 제품 박스의 한계](../outputs/team_data_release_v2/figures/coordinate_case_03.png)

실제 Validation COCO export도 확인했다. D1은18,416이미지/8,918결함객체/4,239제외, D2 개발 GT 진단은243이미지/372제품+결함객체/22,412제외다. 두 파일의 file_name은 원본 상대 경로이며 좌표는 원본 XYWH다. 후자는 독립 최종 평가가 아니다. [D1 export](../outputs/team_data_release_v2/d1_coco_validation/export.json), [D2 diagnostic export](../outputs/team_data_release_v2/d2_diagnostic_coco_validation/export.json).

원본 주석 좌표(source_annotation_coordinate_space), 현재 Target 좌표(target_coordinate_space)를 별도 메타데이터로 구분한다. 최종 도구로 anomaly Crop / D1·D2 원본 / Adapter 이후 MODEL_INPUT 표시를 다시 검사했다. [최종 도구 실제 로딩](../outputs/team_data_release_v2/final_tooling_real_smoke.json).

최종 로컬 전체 회귀는 **223 passed, 1 warning / 24.40초**, 최종 도구 ZIP을 설치한 새 Git Clone도 **223 passed, 1 warning / 25.12초**였다. 문서 상대 링크110개에서 누락0을 확인했다. 최초 코드 압축 사본은 .git이 없어서 Recorder 테스트가 실패했고 제한 환경의 소켓 오류도 있었다. 그 결과 로그를 보존한 뒤 **실제 Git Clone + 새 도구 설치 + 독립 잠금 환경 + 로컬 소켓 허용** 조건으로 전체 회귀 검사를 다시 수행했다. 데이터나 테스트를 삭제/skip해서 통과시키지 않았다. 최종 검증 묶음은 [final_validation.json](../outputs/team_data_release_v2/final_validation.json)이다.


## 재현과 남은 한계

[최신 README_DATA](../docs/data/README_DATA_TEMPLATE.md), [스키마](../docs/data/MANIFEST_SCHEMA.md), [로더 연결](../docs/data/DATA_LOADER_GUIDE.md)를 따른다. 관리자는 build-v2로 기존 검증 v1만 읽고 새 출력 디렉터리를 만든다. 팀원은 DATA/TOOLS v2 ZIP과 해시를 수령하여 verify→원본 경로→smoke→담당 모델 연결 순서로 진행한다.

실제 모델 공식 런타임의 보간/Normalize 일치·학습·Fine-tuning·GPU·성능 개선은 미검증이다. 기존 Adapter의 추가 CenterCrop 비활성화 조건은 공식 baseline과 구분한다. Test 주석 참조 Crop189건의 독립성 위험과 PENDING1건도 보존한다. v2 검출은 Crop을 사용하지 않지만 과거 탐색 이력을 소급해서 제거하지 않는다. 제품 독립 GT 부족과 대부분 전체 프레임인 Pseudo 품질을 다음 팀 결정 사항으로 남긴다.

---

## 이전 v1 검증 기록 (보존, 최신 정책은 위 v2)

# Real-IAD 팀 데이터 계약 및 배포 v1 검증

작성일 2026-11-13. 대상은 `MV_TEAM_DATA_RELEASE_v1`이다. 원본 이미지·마스크, 기존 Canonical CSV, 승인 Ledger, Split, 기존 모델 코드는 수정하지 않았다. Commit/Push·모델 학습은 수행하지 않았다. 배포 ZIP은 팀 내부 전용이며 공개 재배포 허가는 미확인이다.

## 배포 파일과 버전

- 데이터 ZIP: [MV_TEAM_DATA_RELEASE_v1.zip](../outputs/team_data_release_v1/MV_TEAM_DATA_RELEASE_v1.zip), **23,816,724 bytes** (23.82 MB, 약 22.71 MiB).
- ZIP SHA-256: `4cffdf09dfd1402bf4ad5838402330e6c9f437056d303e2b55fb6bdee4abd52f`.
- 통합 canonical SHA-256: `a4e0c603539b7e9146c9d12abc2af5f551dda32e63b7bd45a763ddb19cc41833`.
- 원본 Crop v2 SHA-256: `d1c13cae3fc352f457cb22f9955280e0ce140827a449465d5e05519fd6c9073d`.
- 추가 도구 ZIP: [MV_TEAM_DATA_TOOLS_v1.zip](../outputs/team_data_release_v1/MV_TEAM_DATA_TOOLS_v1.zip), 41,547 bytes. SHA-256 `c5fa95c65ab3386d2aa034a1285fc0c6e24da3bc7d17474887e8a5b3a089903d`.

GitHub의 기존 공통 코드 c4b4a46에 새 도구를 연결한다. 이번 요청은 Commit/Push 금지이므로 새 CLI를 별도 작은 ZIP으로 전달한다. 설치기는 기존 의존 코드/uv.lock 해시를 확인하고, 새 파일 8개만 추가한다. 기존 수정 파일을 덮어쓰지 않는다. 실제 설치 절차는 TOOLS ZIP의 README를 따른다.

데이터 ZIP 안에는 17개 파일이 있다. 원본 JPG/PNG·모델 가중치·승인 Ledger·검수자 이름·자유 입력 notes·개인 절대 경로는 포함하지 않는다. 승인 내용 중 허용된 제품 좌표와 출처 상태만 별도 주석에 반영했다. 출처 파일명과 SHA는 재현 근거로 release.json에 남긴다.

## 최종 CSV 선택 근거와 승인 대조

기존 `configs/data/canonical_manifest.release.json`의 v2/annotation/BBox/class SHA를 먼저 대조했다. 수정 시각으로 파일을 선택하지 않았다. Crop v1→v2 변경 ID 집합은 기존 재검수 목록 43장과 정확하게 같고, 모든 좌표를 최신 유효 승인 이벤트와 비교했다. 승인 revision 해시·기준 CSV 해시·reviewer/시각 일치도 내부 검증했다. 배포에서는 개인 reviewer 정보는 제거한다.

|항목|실제 결과|
|---|---:|
|Crop 원장 이벤트|1,641|
|최신 APPROVED_CROP 이미지|1,594|
|승인 없이 변경된 좌표|0|
|43장 재검수 좌표 반영|43/43|
|43장 마스크 픽셀 손실|0|
|제품 GT 원장 이벤트|605|
|최신 사람 승인 제품 GT|600|
|승인 출처 이미지 현재 콘텐츠 SHA 재검사|2,178 고유 이미지|
|최신 PENDING Crop 기록|1|

PENDING image_id는 `54c1c890c8dd2789`이며 Train/woodstick/C5다. 최신 CSV에는 UNREVIEWED_BASELINE, 정책 C, 원본 전체 좌표로 남아 있다. 사람 승인으로 승격하지 않았고, 현재 제공 마스크는 손실 없이 보존됐다. 추가 검수 필요 여부는 담당자가 확인한다. PENDING 1건 때문에 “모든 검수 항목 승인 완료”라고 선언하지 않는다.

근거: [배포 validation](../outputs/team_data_release_v1/MV_TEAM_DATA_RELEASE_v1/validation/validation.json), [43장 대조](../outputs/team_data_release_v1/MV_TEAM_DATA_RELEASE_v1/validation/re_review_43.csv).

## 전수 계약 검증

|항목|개수|
|---|---:|
|이미지|151,050|
|선언 제품 그룹|30,210|
|제품 카테고리|30|
|시점|C1~C5, 제품당 5장|
|OK|72,840|
|NG|78,210|
|제공 마스크|51,329|
|양성 마스크 NG|51,295|
|제공된 빈 마스크 NG|34|
|마스크 미제공 NG|26,881|
|원본 결함 연결 성분 BBox|60,636|
|Crop 후 유지 BBox|60,636|
|부분 Clip/완전 제거 BBox|0 / 0|
|제공 마스크 양성 픽셀 손실 이미지|0|
|파일/마스크/타깃 오류|0 / 0 / 0|

마스크 총수가 NG 총수보다 작다는 사실은 오류로 취급하지 않는다. 미제공 NG는 NG 이미지 라벨을 유지하며 위치 평가와 기본 검출 학습에서 제외한다. OK에는 빈 결함 BBox를 사용하며 normal 결함 클래스를 추가하지 않는다.

기존 JPEG 전수 디코딩·콘텐츠 SHA 기록은 v1 출처 해시, 이미지 ID 집합, 현재 원본 크기/mtime 일치 조건으로 151,050장 재사용했다. **이번에 JPEG 전체를 새로 디코딩한 것은 아니다.** 승인 출처 2,178장은 현재 콘텐츠 SHA를 새로 확인했다. 제공 PNG 51,329장은 이번에 다시 디코딩하고 원본 크기와 비교했다. 기존 검증된 >0 임계값, 8방향 연결 성분, 면적 필터 없음 정책으로 BBox를 재추출하여 기존 파일명 보정 BBox와 전부 대조했다. 해상도 정보 손실 분석은 재실행하지 않았다.

151,050개 ID/경로 중복 없음, 좌표 범위/크기/exclusive 계약 유효, 완전한 C1~C5 그룹, 제품 단위 Split 누수 없음이 확인됐다. 제품 그룹의 실제 물리적 동일성을 독립 검증했다는 의미는 아니다. 정책 C 149,463장, HUMAN_CROP 1,587장이고 수동 승인 1,594건에는 원본 전체 승인도 포함된다.

## 클래스와 제품 주석

|결함|YOLO/Canonical|COCO/TorchVision|
|---|---:|---:|
|AK|0|1|
|BX|1|2|
|CH|2|3|
|HS|3|4|
|PS|4|5|
|QS|5|6|
|YW|6|7|
|ZW|7|8|

기존 ID 순서를 유지했다. 폴더 HS/파일명 QS 충돌 10장은 사용자 지정 파일명 우선 정책과 일치한다. 그중 7장은 유효 마스크, 3장은 미제공 상태를 유지한다. 한 NG 이미지의 모든 연결 성분에 이미지의 결함 종류를 부여하는 기존 가정은 유지한다.

제품 주석은 HUMAN_VERIFIED_GT 600개, AUTOMATIC_PROPOSAL 600개, CROP_APPROXIMATION 151,050개로 나눴다. 모두 기본 검출 타깃에서 제외한다. Crop 영역이 제품 전체 정답이라는 주장은 하지 않는다. 확장 실험에서 제품/결함 유형과 OK/NG 상태를 분리하고 양쪽 상태에 일관된 주석 기준을 적용해야 한다. 정상에만 큰 제품 BBox를 추가하는 방식을 기본 데이터로 채택하지 않았다.

## Split별 학습 적격성

|Split|이미지|이상탐지 Train|이상탐지 이미지 평가|이상탐지 픽셀 평가|검출 Train|검출 평가|
|---|---:|---:|---:|---:|---:|---:|
|Train|105,735|50,930|0|0|87,077|0|
|Validation|22,655|0|22,655|18,416|0|18,416|
|Test|22,660|0|22,660|18,642|0|18,642|

기본 검출 적격 전체는 124,135장(OK72,840 + 주석 유효 NG51,295)이다. Train/평가 분리를 유지한다. 이미지 평가 적격성과 픽셀/검출 적격성은 같지 않다. 대상의 상세 제외 사유는 eligibility.csv에 있다. 기본 계약에서는 부분 주석 손실도 검출/위치 평가에서 제외하지만 이번 최종 v2에서 손실 사례는 0이었다.

근거: [Split 집계](../outputs/team_data_release_v1/MV_TEAM_DATA_RELEASE_v1/validation/split_eligibility.csv), [품목×Split](../outputs/team_data_release_v1/MV_TEAM_DATA_RELEASE_v1/validation/category_split_eligibility.csv), [시점×Split](../outputs/team_data_release_v1/MV_TEAM_DATA_RELEASE_v1/validation/view_split_eligibility.csv).

## 구현 및 테스트

새 코드 `mv_analysis/data/team_release.py`, `release_builder.py`, `scripts/team_data_release.py`는 기존 로더/기하 변환 코드를 재사용한다. 기존 canonical이나 승인 좌표를 변경하지 않는다. 통합 CSV의 label/geometry 중복 컬럼을 분리하고, 다른 PC에서 콘텐츠 SHA를 확인한 후 mtime 식별값을 메모리에서만 연결한다. 모델별 전처리나 학습 구현을 추가하지 않았다.

새 합성 테스트 22개를 추가했다. ZIP 구조/해시/탈출 경로/덮어쓰기 방지, NG 미주석·빈 마스크·부분/완전 손실, 작은 연결 성분, 원점 이동/Clip, OK 빈 YOLO/COCO/TorchVision, 클래스 오프셋, 제품 출처, Split/좌표/중복 오류, 복사 후 mtime 변경과 원본 변조, Single/Five-view/Collate를 검사한다.

`uv run --locked pytest -q`: **207 passed, 1 warning**. 최초 제한 환경에서는 기존 로컬 HTTP 테스트가 소켓 차단으로 1 failed/8 errors였고, 127.0.0.1 테스트 허용 환경에서 전체를 재실행하여 통과했다. 기존 NumPy timedelta 경고 1개는 남아 있다. 테스트에서 실제 승인 원장은 변경하지 않았다.

데이터 ZIP을 새 임시 디렉터리에 압축 해제하고 CRC, 전체 파일 SHA, Manifest/Annotation 참조, 클래스, 좌표, Split, 5시점, 적격성 검사를 통과했다. [압축 해제 검사](../outputs/team_data_release_v1/extraction_validation.json)를 따른다. 추가 실제 원본 로딩과 주석 export 결과는 다음 절의 완료 기록에 이어 적는다.

## 한계와 팀 결정

1. Test 이미지 189장의 Crop 검수는 주석 참조가 기록되어 있다. 데이터 계약 일치가 독립 Test 평가를 보장하지 않는다. 새 독립 평가 또는 투명한 제외/별도 보고 방식을 팀에서 결정해야 한다. Split은 임의로 바꾸지 않았다.
2. PENDING 1건은 미승인 상태와 원본 전체 좌표를 유지한다. 원장을 자동 수정하지 않았다.
3. 원본 JPEG 전수 재디코딩 대신 이전 검증의 조건부 캐시를 사용했다. 수령 측 로더는 첫 사용마다 콘텐츠 SHA를 확인한다. 실행 중 원본은 읽기 전용으로 유지한다.
4. 결함 마스크 없음은 결함 없음이 아니다. 미주석 NG를 검출 Negative로 넣지 않는다.
5. 제품 BBox와 Crop 근사치는 픽셀 분할 정답이 아니다. 별도 normal/product 확장 정책 및 분류 Head/Loss는 미구현이다.
6. 모델 Adapter 독립 변환과 실제 모델 런타임 통합을 구분한다. 12개 모델 학습/성능·GPU 검증·팀원 4명 각자의 설치는 미실행이다.

## 재현

관리자: `uv run --locked python scripts/team_data_release.py build --data-root "$REALIAD_DATA_ROOT" --workers 2 --output outputs/team_data_release_new_run`. 내부 출처 자료가 있어야 하며 1,000장 단위 체크포인트를 사용한다. 기존 패키지는 덮어쓰지 않는다.

팀원: TOOLS ZIP 설치 → `uv sync --locked` → 새 pytest → DATA ZIP verify → REALIAD_DATA_ROOT 연결 → smoke → 동일 canonical SHA를 Recorder에 기록. [배포 README](../docs/data/README_DATA_TEMPLATE.md), [로더 안내](../docs/data/DATA_LOADER_GUIDE.md), [스키마](../docs/data/MANIFEST_SCHEMA.md)를 따른다.
