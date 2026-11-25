# 분석 근거 인덱스

초기파일조사154,993개(요청확장자별메타인벤토리). 이것은모든파일을수치검증했다는뜻이아니다. 아래선정본만해당validation범위에서VERIFIED로사용한다. 생성시각은manifestcreated가있으면그값,없으면파일mtime을보조로쓴다. mtime은원래실행시각을증명하지않는다.

| domain | source | validation | scope | status | note | mtime_utc |
| --- | --- | --- | --- | --- | --- | --- |
| metadata | outputs/windows_preserved_20261111_v1 | outputs/windows_preserved_20261111_v1/metadata_validation_report.json | 151050 JPG,51329 PNG; Windows split | VERIFIED | declared product groups; physical identity UNVERIFIED | 2026-11-11T09:33:10.393646+00:00 |
| brightness | outputs/windows_preserved_20261111_v1 | outputs/windows_preserved_20261111_v1/brightness_per_image_execution.json | 151050 JPG; whole grayscale | VERIFIED | v6 cache imported and regrouped by preserved split | 2026-11-11T09:33:10.393646+00:00 |
| regional_brightness | outputs/background_full_20261111_v1 | outputs/background_full_20261111_v1/scientific_validation.json | 151050 JPG; border-lab-v5, accepted78526 | VERIFIED | values numerically checked; product GT accuracy UNVERIFIED | 2026-11-11T09:29:55.561661+00:00 |
| heatmap | outputs/windows_preserved_20261111_v1 | outputs/windows_preserved_20261111_v1/heatmap_validation.json | Train NG54805; provided masks36173;presence64 | VERIFIED | occupancy_known/positive, unobserved NaN | 2026-11-11T09:33:10.393646+00:00 |
| bbox | outputs/spatial_20261111_v7 | outputs/spatial_20261111_v7/detection_export_validation.json | 60629 boxes,8classes | VERIFIED | 7 masked conflicting images excluded; unannotated NG excluded | 2026-11-11T03:57:22.142567+00:00 |
| mask | outputs/mask_integrity_20261111_v6 | outputs/mask_integrity_20261111_v6 | 51329 PNG,gray>0 | VERIFIED | all grayscale values are supported; not independent semantic boundary proof | 2026-11-11T04:18:08.178046+00:00 |
| resolution | outputs/windows_preserved_20261111_v1 | outputs/windows_preserved_20261111_v1/resolution_scientific_validation.json | 151050x3 frozen metric rows | VERIFIED | numeric cache rebound metadata without recomputation | 2026-11-11T09:33:10.393646+00:00 |
| crop | outputs/preprocessing_review_20261112_v2 | outputs/preprocessing_review_20261112_v2/complete.json | 51329 provided masks;60629 boxes;300 product samples | VERIFIED | heuristic product geography remains UNVERIFIED | 2026-11-12T00:27:44.922814+00:00 |
| content | outputs/content_audit_20261111_v7 | outputs/content_audit_20261111_v7/content_hash_validation.json | 202379 exact byte hashes | VERIFIED | cross-split count belongs to old split; canonical quality review is separate | 2026-11-11T04:30:58.243483+00:00 |

[selected_evidence_versions.csv](../outputs/preprocessing_review_20261112_v2/review_assets/statistics/selected_evidence_versions.csv)

[output_version_inventory.csv](../outputs/preprocessing_review_20261112_v2/review_assets/statistics/output_version_inventory.csv)

[artifact_inventory_summary.csv](../outputs/preprocessing_review_20261112_v2/review_assets/statistics/artifact_inventory_summary.csv)

버전차이: full_v6은최초hash탐색split의원본계산. windows_preserved_v1은Windowsseed42분할로수치재계산없이메타만재결합. 해상도수치는동일하지만split이바뀌어Train집계가다르다. 기존spatial의area-v1열지도는새presence-v2조건부빈도와단위가달라직접비교금지. 최신presence는원본어느픽셀이라도양성이면64gridcell점유로기록하고n_known/n_positive분모를구분한다.

heatmap Train NG54805,provided36173,560groups,미관측6groups. 결함발생실제확률이아니라제공Train위치정답의빈도다. 未관측은NaN이고정상0이아니다.

초기535밝기비교는29품목checkpoint,현재원래Windows555는u_block추가20조합. 새560은fire_hood경로충돌의UNRESOLVED분리로5조합추가. 560모두제품밝기비교가능한것은아니며유효326만해석한다.

reports/와docs/기존보고서는보존했다. src/와notebook_results_real/루트는현재없음;실제Windows원본소스는legacy/windows_snapshot에보존되어있다. PDF/이미지사례는로컬기존자료로남기고이번ZIP에서제외한다.

## 공유 자료 provenance

| asset | source | bytes | source_mtime_utc | status |
| --- | --- | --- | --- | --- |
| outputs/preprocessing_review_20261112_v2/review_assets/statistics/category_status_counts.csv | outputs/preprocessing_review_20261112_v2/category_status_counts.csv | 1573 | 2026-11-12T00:15:57.572984+00:00 | VERIFIED |
| outputs/preprocessing_review_20261112_v2/review_assets/statistics/defect_counts.csv | outputs/preprocessing_review_20261112_v2/defect_counts.csv | 265 | 2026-11-12T00:15:57.594874+00:00 | VERIFIED |
| outputs/preprocessing_review_20261112_v2/review_assets/statistics/view_mask_counts.csv | outputs/preprocessing_review_20261112_v2/view_mask_counts.csv | 266 | 2026-11-12T00:15:57.611966+00:00 | VERIFIED |
| outputs/preprocessing_review_20261112_v2/review_assets/statistics/split_counts.csv | outputs/preprocessing_review_20261112_v2/split_counts.csv | 200 | 2026-11-12T00:15:57.631138+00:00 | VERIFIED |
| outputs/preprocessing_review_20261112_v2/review_assets/statistics/mask_crop_overall.csv | outputs/preprocessing_review_20261112_v2/mask_crop_overall.csv | 470 | 2026-11-12T00:16:05.177312+00:00 | VERIFIED |
| outputs/preprocessing_review_20261112_v2/review_assets/statistics/mask_crop_category.csv | outputs/preprocessing_review_20261112_v2/mask_crop_category.csv | 9945 | 2026-11-12T00:16:05.438211+00:00 | VERIFIED |
| outputs/preprocessing_review_20261112_v2/review_assets/statistics/mask_crop_view.csv | outputs/preprocessing_review_20261112_v2/mask_crop_view.csv | 1743 | 2026-11-12T00:16:05.497174+00:00 | VERIFIED |
| outputs/preprocessing_review_20261112_v2/review_assets/statistics/mask_crop_defect.csv | outputs/preprocessing_review_20261112_v2/mask_crop_defect.csv | 3001 | 2026-11-12T00:16:05.573226+00:00 | VERIFIED |
| outputs/preprocessing_review_20261112_v2/review_assets/statistics/mask_crop_by_size.csv | outputs/preprocessing_review_20261112_v2/mask_crop_by_size.csv | 1280 | 2026-11-12T00:19:16.866504+00:00 | VERIFIED |
| outputs/preprocessing_review_20261112_v2/review_assets/statistics/bbox_crop_counts.csv | outputs/preprocessing_review_20261112_v2/bbox_crop_counts.csv | 208 | 2026-11-12T00:16:07.147520+00:00 | VERIFIED |
| outputs/preprocessing_review_20261112_v2/review_assets/statistics/bbox_crop_category_view.csv | outputs/preprocessing_review_20261112_v2/bbox_crop_category_view.csv | 34010 | 2026-11-12T00:16:07.167445+00:00 | VERIFIED |
| outputs/preprocessing_review_20261112_v2/review_assets/statistics/bbox_crop_resize_risk.csv | outputs/preprocessing_review_20261112_v2/bbox_crop_resize_risk.csv | 418 | 2026-11-12T00:19:17.007926+00:00 | VERIFIED |
| outputs/preprocessing_review_20261112_v2/review_assets/statistics/mask_crop_resize_area_proxy.csv | outputs/preprocessing_review_20261112_v2/mask_crop_resize_area_proxy.csv | 1559 | 2026-11-12T00:19:16.938779+00:00 | VERIFIED |
| outputs/preprocessing_review_20261112_v2/review_assets/statistics/bbox_category_distribution.csv | outputs/preprocessing_review_20261112_v2/bbox_category_distribution.csv | 2259 | 2026-11-12T00:16:07.201274+00:00 | VERIFIED |
| outputs/preprocessing_review_20261112_v2/review_assets/statistics/bbox_defect_distribution.csv | outputs/preprocessing_review_20261112_v2/bbox_defect_distribution.csv | 613 | 2026-11-12T00:16:07.221642+00:00 | VERIFIED |
| outputs/preprocessing_review_20261112_v2/review_assets/statistics/bbox_view_distribution.csv | outputs/preprocessing_review_20261112_v2/bbox_view_distribution.csv | 406 | 2026-11-12T00:16:07.241436+00:00 | VERIFIED |
| outputs/preprocessing_review_20261112_v2/review_assets/statistics/product_geometry_summary.csv | outputs/preprocessing_review_20261112_v2/product_geometry_summary.csv | 25816 | 2026-11-12T00:19:15.586808+00:00 | VERIFIED |
| outputs/preprocessing_review_20261112_v2/review_assets/statistics/regional_global_statistics.csv | outputs/preprocessing_review_20261112_v2/regional_global_statistics.csv | 2065 | 2026-11-12T00:15:59.283146+00:00 | VERIFIED |
| outputs/preprocessing_review_20261112_v2/review_assets/statistics/regional_category_statistics.csv | outputs/preprocessing_review_20261112_v2/regional_category_statistics.csv | 56642 | 2026-11-12T00:15:59.647833+00:00 | VERIFIED |
| outputs/preprocessing_review_20261112_v2/review_assets/statistics/regional_view_statistics.csv | outputs/preprocessing_review_20261112_v2/regional_view_statistics.csv | 10365 | 2026-11-12T00:16:00.108500+00:00 | VERIFIED |
| outputs/preprocessing_review_20261112_v2/review_assets/statistics/regional_background_statistics.csv | outputs/preprocessing_review_20261112_v2/regional_background_statistics.csv | 8116 | 2026-11-12T00:16:01.643633+00:00 | VERIFIED |
| outputs/preprocessing_review_20261112_v2/review_assets/statistics/regional_per_image_percentile_summary.csv | outputs/preprocessing_review_20261112_v2/regional_per_image_percentile_summary.csv | 159323 | 2026-11-12T00:16:01.748413+00:00 | VERIFIED |
| outputs/preprocessing_review_20261112_v2/review_assets/statistics/selection_category.csv | outputs/preprocessing_review_20261112_v2/selection_category.csv | 2444 | 2026-11-12T00:19:16.221018+00:00 | VERIFIED |
| outputs/preprocessing_review_20261112_v2/review_assets/statistics/selection_status.csv | outputs/preprocessing_review_20261112_v2/selection_status.csv | 210 | 2026-11-12T00:19:16.226903+00:00 | VERIFIED |
| outputs/preprocessing_review_20261112_v2/review_assets/statistics/selection_view.csv | outputs/preprocessing_review_20261112_v2/selection_view.csv | 446 | 2026-11-12T00:19:16.234954+00:00 | VERIFIED |
| outputs/preprocessing_review_20261112_v2/review_assets/statistics/selection_background_type.csv | outputs/preprocessing_review_20261112_v2/selection_background_type.csv | 402 | 2026-11-12T00:19:16.242403+00:00 | VERIFIED |
| outputs/preprocessing_review_20261112_v2/review_assets/statistics/selection_failure_reasons.csv | outputs/preprocessing_review_20261112_v2/selection_failure_reasons.csv | 356 | 2026-11-12T00:19:16.502939+00:00 | VERIFIED |
| outputs/preprocessing_review_20261112_v2/review_assets/statistics/selection_candidate_diagnostics.csv | outputs/preprocessing_review_20261112_v2/selection_candidate_diagnostics.csv | 2301 | 2026-11-12T00:19:16.554365+00:00 | VERIFIED |
| outputs/preprocessing_review_20261112_v2/review_assets/statistics/segmentation_category_coverage.csv | outputs/preprocessing_review_20261112_v2/segmentation_category_coverage.csv | 652 | 2026-11-12T00:16:01.654453+00:00 | VERIFIED |
| outputs/preprocessing_review_20261112_v2/review_assets/statistics/provided_view_count_per_ng_product.csv | outputs/preprocessing_review_20261112_v2/provided_view_count_per_ng_product.csv | 60 | 2026-11-12T00:15:57.766171+00:00 | VERIFIED |
| outputs/preprocessing_review_20261112_v2/review_assets/statistics/five_view_brightness_correlation.csv | outputs/preprocessing_review_20261112_v2/five_view_brightness_correlation.csv | 661 | 2026-11-12T00:15:58.196846+00:00 | VERIFIED |
| outputs/preprocessing_review_20261112_v2/review_assets/statistics/brightness_interpretation_changes.csv | outputs/background_full_20261111_v1/brightness_interpretation_changes.csv | 134119 | 2026-11-11T09:29:06.258142+00:00 | VERIFIED |
| outputs/preprocessing_review_20261112_v2/review_assets/statistics/background_stratified_comparison.csv | outputs/background_full_20261111_v1/background_stratified_comparison.csv | 123929 | 2026-11-11T09:29:01.969654+00:00 | VERIFIED |
| outputs/preprocessing_review_20261112_v2/review_assets/statistics/strict_selection_sensitivity_comparison.csv | outputs/background_full_20261111_v1/strict_selection_sensitivity_comparison.csv | 72908 | 2026-11-11T09:29:53.474376+00:00 | VERIFIED |
| outputs/preprocessing_review_20261112_v2/review_assets/statistics/segmentation_selection_brightness.csv | outputs/background_full_20261111_v1/segmentation_selection_brightness.csv | 448 | 2026-11-11T09:29:06.561370+00:00 | VERIFIED |
| outputs/preprocessing_review_20261112_v2/review_assets/statistics/train_product_augmentation_candidates.csv | outputs/background_full_20261111_v1/train_product_augmentation_candidates.csv | 14889 | 2026-11-11T09:29:02.076182+00:00 | VERIFIED |
| outputs/preprocessing_review_20261112_v2/review_assets/statistics/train_normal_only_augmentation_candidates.csv | outputs/background_full_20261111_v1/train_normal_only_augmentation_candidates.csv | 7289 | 2026-11-11T09:29:02.093654+00:00 | VERIFIED |
| outputs/preprocessing_review_20261112_v2/review_assets/statistics/overall_statistics.csv | outputs/resolution_detail_20261111_v2/overall_statistics.csv | 3842 | 2026-11-11T11:04:27.057781+00:00 | VERIFIED |
| outputs/preprocessing_review_20261112_v2/review_assets/statistics/category_statistics.csv | outputs/resolution_detail_20261111_v2/category_statistics.csv | 122010 | 2026-11-11T11:04:28.389052+00:00 | VERIFIED |
| outputs/preprocessing_review_20261112_v2/review_assets/statistics/view_statistics.csv | outputs/resolution_detail_20261111_v2/view_statistics.csv | 19192 | 2026-11-11T11:04:28.800668+00:00 | VERIFIED |
| outputs/preprocessing_review_20261112_v2/review_assets/statistics/status_statistics.csv | outputs/resolution_detail_20261111_v2/status_statistics.csv | 7624 | 2026-11-11T11:04:29.162028+00:00 | VERIFIED |
| outputs/preprocessing_review_20261112_v2/review_assets/statistics/category_view_status_statistics.csv | outputs/resolution_detail_20261111_v2/category_view_status_statistics.csv | 1253992 | 2026-11-11T11:04:39.568934+00:00 | VERIFIED |
| outputs/preprocessing_review_20261112_v2/review_assets/statistics/existing_roi_summary.csv | outputs/resolution_detail_20261111_v2/existing_roi_summary.csv | 1881 | 2026-11-11T11:05:03.603710+00:00 | VERIFIED |
| outputs/preprocessing_review_20261112_v2/review_assets/statistics/bbox_projected_size_risk.csv | outputs/resolution_detail_20261111_v2/bbox_projected_size_risk.csv | 170 | 2026-11-11T11:05:03.467716+00:00 | VERIFIED |
| outputs/preprocessing_review_20261112_v2/review_assets/statistics/stepwise_distribution.csv | outputs/resolution_detail_20261111_v2/stepwise_distribution.csv | 500 | 2026-11-11T11:04:39.744242+00:00 | VERIFIED |
| outputs/preprocessing_review_20261112_v2/review_assets/statistics/heatmap_summary.csv | outputs/windows_preserved_20261111_v1/heatmap_summary.csv | 47563 | 2026-11-11T06:24:04.736227+00:00 | VERIFIED |