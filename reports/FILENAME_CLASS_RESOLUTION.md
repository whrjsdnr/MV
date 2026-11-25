# 파일명 기준 클래스 충돌 해결 및 Crop 재검토 안내

사용자 지시에 따라 불량 클래스 충돌은 이미지 파일명 `_NG_{code}_C{view}_`의 코드를 우선한다. 폴더 이름, 선언 제품 ID, Split, 원본 JPG/PNG, 기존 승인 Ledger, 저장된 Crop 좌표는 변경하지 않았다. 이는 사람의 제품 BBox 승인이나 Crop 승인을 새로 생성하는 작업이 아니다.

## 실제 확인 결과

`fire_hood/NG/HS/S0131`, `fire_hood/NG/HS/S0132`의 10장은 폴더 코드 HS와 파일명 코드 QS가 충돌한다. 10장 모두 QS(YOLO class_id=5, COCO class_id=6)로 해결했다. 원본 `label_conflict=True`는 감사 목적으로 유지하고, 새 파생 메타데이터의 `defect_type`만 QS로 정했다.

- 양성 마스크가 제공된 7장: 기존 검증 정책인 마스크 `>0`, 8방향 연결 성분, 원본 XYXY exclusive로 BBox 7개를 복구했다. 실제 Single-view 로딩에서 클래스 5, 마스크와 원본 BBox 일치, 객체탐지 collate 통과를 확인했다.
- 마스크 미제공 3장: 클래스는 QS지만 `MISSING_ANNOTATION`을 유지한다. 빈 마스크나 정상 Negative를 만들지 않는다.
- 파생 전체 메타데이터 151,050행, BBox 60,636개(기존 60,629 + 복구 7). 이번 변경 대상은 10장만 실제 재로딩했다. 이전 전수 디코딩 결과는 재사용했다.

새 기본 `ManifestIndex`는 아래 파생 테이블을 읽는다. 원본 테이블을 명시적으로 전달하면 이전 원본 계약을 재현할 수 있다.

- [파생 클래스 메타데이터](../outputs/filename_class_resolution_v1/image_metadata_with_split.csv)
- [파생 BBox](../outputs/filename_class_resolution_v1/defect_bboxes.csv)
- [변경 10장 감사표](../outputs/filename_class_resolution_v1/class_resolution_audit.csv)
- [갱신된 전체 학습 적격 계약](../outputs/filename_class_resolution_v1/annotation_contract.csv)
- [재검증 JSON](../outputs/filename_class_resolution_v1/target_revalidation.json)

객체탐지 필터에는 새 `annotation_contract.csv`를 사용한다. 이전 `outputs/data_loader_validation_v1/`의 7장 INVALID_TARGET 기록은 변경 전 시점의 증거로 보존되며, 현재 클래스 정책에서는 위 새 검증 결과가 우선한다. 실제 모델 forward/학습 검증은 하지 않았다.

## Crop 손실 43장 직접 수정

서버 실행 위치는 프로젝트 루트다.

```bash
uv run --offline python scripts/review_loader_findings.py --port 8771
```

브라우저: <http://127.0.0.1:8771>

이 화면의 이전/다음은 저장된 Crop에서 양성 마스크가 일부 잘린 **43장만** 순회한다. 기존 승인 상태와 이번 재검토 완료 수를 구분하며 최초 진행률은 0/43이다. 기존 8766/8767/8769 서버는 종료하지 않는다.

1. 검수자 이름을 입력한다. 원본과 하늘색 제품 GT, 마스크 표시를 확인한다. 하늘색은 검수된 제품 BBox이며 Crop 좌표 자체가 아니다.
2. 초록색 Crop을 드래그해 넓히거나 원본 전체 복원 버튼을 사용한다. 제품 전체와 결함을 함께 확인한다.
3. 보존 점검을 실행한다. 제공 마스크 보존율 100%는 확인 가능한 결함에 한정된 결과이며 전체 제품 보존의 증명과 다르다.
4. 직접 확인 및 기존 승인 재검수 확인을 체크한 뒤 승인/저장한다. 손실 또는 미확인 영역이 남으면 별도 위험 확인이 요구된다.
5. 수정 완료 후 CSV 내보내기를 눌러 전체 151,050행을 담은 `preprocessing_metadata_reviewed_v2.csv`(이미 존재하면 다음 버전)를 만든다. 43행만 내보내는 방식이 아니므로 이전 승인도 유지된다.
6. 새 CSV는 승인 Ledger와 다시 대조하고 좌표/마스크 변환을 재검증한 뒤 학습 입력으로 선택한다. 기존 v1 검증 결과를 새 CSV의 검증 결과로 사용하지 않는다.

실제 HTTP로 HTML/JavaScript/표준 JSON/원본 JPEG/마스크 PNG 응답을 확인했다. 실제 Windows 브라우저의 화면 렌더링은 미검증이다. 테스트 승인은 임시 Ledger에만 수행하며 실제 승인 기록은 사람이 저장할 때만 추가된다.

## 재현

새 체크아웃에서는 보존된 원본 분석 산출물이 있어야 한다. 생성기는 기존 출력이 있으면 덮어쓰지 않고 종료한다.

```bash
uv run --offline python scripts/resolve_filename_class_conflicts.py
uv run --offline python scripts/validate_filename_class_resolution.py
uv run --offline pytest -q
```

## 최종 검증 결과

- 전체 pytest: **143 passed, 1 warning**. 로컬 소켓이 제한된 샌드박스에서 HTTP 테스트 1건이 실행 제한으로 실패한 후, 허용된 로컬 HTTP 환경에서 전체 테스트를 다시 실행해 통과했다. 경고는 기존 NumPy timedelta 테스트의 사용 중단 경고다.
- 새 전체 계약: OK_NEGATIVE 72,840 / SUPERVISED_VALID 51,295 / MISSING_ANNOTATION 26,881 / EMPTY_NG_REVIEW 34. 합계 151,050. 클래스 충돌에 따른 INVALID_TARGET 7건은 해결됐으나 Crop 부분 손실 43건은 별도의 재검토 대상이다.
- 파생 테이블 생성 전후 원본 메타데이터 및 원본 BBox SHA-256 동일함을 확인했다.
- 필터 검수 저장·전체 행 내보내기 회귀 테스트는 임시 승인 Ledger와 합성 이미지로 통과했다. 실제 사람 승인 기록은 테스트하지 않았다.
