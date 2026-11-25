# 전체 전처리 좌표 정책 요약

전처리 파일은 [preprocessing_metadata.csv](../outputs/adaptive_crop_full_v1/preprocessing_metadata.csv) 하나다. 151050행,40컬럼. 원본 영상은 별도로 있어야 한다.

전체 좌표 생성 완료. 현재정책C151050장/A0/B0, exclusive[0,0,1024,1024], 확대1배. 검증된 A/B 범위가 없고 제품 GT에서 Gate 오통과가 관측돼 원본 유지 안전 기본값을 사용했다. 전수GrabCut은 하지 않았다.

| method | images | partial | removed | exact_containment | area_recall |
| --- | --- | --- | --- | --- | --- |
| calibrated_research_gate | 600 | 2 | 0 | 0.996667 | 0.999941 |
| center896 | 600 | 121 | 0 | 0.798333 | 0.988057 |
| grabcut90_m10 | 600 | 15 | 0 | 0.975 | 0.998722 |
| previous_image_gate | 600 | 6 | 0 | 0.99 | 0.999806 |
| production_safe_policy | 600 | 0 | 0 | 1 | 1 |

제품 GT600개, 원장이력605개를 읽기 전용으로 확인했다. 현재Final310장 원시A 손실9장 중GatePASS3장(3/9), GatePASS258장 중손실3장(3/258). 독립 미사용 제품 Final이 아니라는 한계가 있다.

위치GT없는NG26881장은 정상으로 바꾸지 않았다. 제공양성마스크51295장 원본좌표보존100%. 다만 모델추가CenterCrop896 상당 적용 시양성82장완전제거·1029장부분잘림이다. 추가Crop을 별도감사없이 적용하지 않는다.

Crop 이미지저장0, Split변경0, 승인Ledger변경0, 모델학습0, GitHubPush0. [상세 보고서](FULL_DATASET_ADAPTIVE_CROP_REPORT.md).