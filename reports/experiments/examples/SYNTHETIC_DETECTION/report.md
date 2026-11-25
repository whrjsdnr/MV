# SYNTHETIC 실험 보고서 — YOLO11

Run `run_20261113T023608_274d81958c664ae2bfbfecb620fbf737` / 상태 **PARTIAL** / 실제 학습 실행 `False`

SYNTHETIC이면 모든 점수·Loss·예측 예시는 인프라 검증용이며 실제 모델 성능으로 해석하면 안 된다.

## 1. 실험 개요

| 항목 | 관측값 |
|---|---|
| experiment_id | shared-infrastructure-demo |
| run_id | run_20261113T023608_274d81958c664ae2bfbfecb620fbf737 |
| model_family | detection |
| data_kind | SYNTHETIC |
| comparison_track | COMMON_INPUT |

## 2. 모델 및 공식 구현

| 항목 | 관측값 |
|---|---|
| model_name | YOLO11 |
| official_repo | https://github.com/ultralytics/ultralytics |
| official_commit | d2b7876e79ad2e02fd77221622774b511a8f0cb3 |
| project_commit | 8ee73b42b4c5e0552696d439c439623dff6c8531 |

## 3. 데이터와 Manifest 버전

| 항목 | 관측값 |
|---|---|
| manifest_sha256 | 105a0760f9289ad0ce31d3059959c28b9c376ae24cc5730d9d399ce20cf2c9af |
| annotation_sha256 | 9838f606e7b213b1d0df26c7f04a16b2cd4206c0142d285eb0485af77cf2abe2 |
| evaluation_set_sha256 | 47f89b7f35340818cdd8161f3f2064fac261a1f8329f84c78bac129f2028e024 |
| class_mapping_sha256 | 3eb04b1f75446bc6ef66389ae760388662e31a89a07fc5cc04bd22fd3954b1d6 |
| split_version | synthetic-fixed-v1 |
| crop_policy_version | no_crop_synthetic |
| model_adapter_version | synthetic-demo-v1 |

## 4. 학습 환경

| 항목 | 관측값 |
|---|---|
| python | 3.12.14 |
| system | Linux-6.18.33.2-microsoft-standard-WSL2-x86_64-with-glibc2.39 |
| cpu | 12th Gen Intel(R) Core(TM) i5-12400 |
| logical_cpus | 4 |
| ram_bytes | 10429767680 |
| torch_version | 2.15.0+cpu |
| cuda_version | N/A |
| gpu | [] |
| torch_threads | 1 |

## 5. 학습 설정

| 항목 | 관측값 |
|---|---|
| seed | 17 |
| device | cpu |
| batch_size | 1 |
| epochs | 0 |
| optimizer | N/A |
| scheduler | N/A |
| learning_rate | N/A |
| input_resolution | [24, 24] |
| normalization | synthetic RGB float01 |

기록된 checkpoint 메타데이터(가중치 파일은 별도 전달):

| 항목 | 관측값 |
|---|---|
| 0 | {'path': 'synthetic_checkpoint.bin', 'sha256': '702b18d9d885274576226b38b05b66892726908b711da417b8ec7fbc5e07d2e3', 'bytes': 41, 'epoch': None, 'role': 'SYNTHETIC_NOT_TRAINED', 'time_utc': '2026-11-13T02:36:08.333987+00:00'} |

## 6. Loss 분석

- 관측: loss_total Train 처음 1 → 마지막 0.333333. Loss 감소는 모델 성능 개선 증명이 아니다.
- 관측: loss_auxiliary Train 처음 0.2 → 마지막 0.0666667. Loss 감소는 모델 성능 개선 증명이 아니다.
- 관측: Validation image_auroc 최고값 0.9, epoch=2. Test로 선정하지 않았다.

## 7. Validation 성능

| 항목 | 관측값 |
|---|---|
| images | 10 |
| evaluated_images | 8 |
| map50 | 0.663366 |
| map50_95 | 0.663366 |
| precision | 0.666667 |
| recall | 0.666667 |
| f1 | 0.666667 |
| tp | 2 |
| fp | 1 |
| fn | 1 |
| exclusions | 2 |
| threshold_policy | {'image': None, 'pixel': None, 'pixel_score_range': None, 'detection': 0.9, 'source_split': 'validation', 'validation_ids_sha256': '9656b3b87e552a6329eb9168389e6b536b517ad05487ea37ce4a9955372fae7b', 'protocol_sha256': '582a7377118d32cb2b0397e5416211702445796d92deb4aaf11086d3a4decab7', 'data_kind': 'SYNTHETIC'} |
| validation_product_count | 2 |

## 8. Test 성능

| 항목 | 관측값 |
|---|---|
| images | 10 |
| evaluated_images | 8 |
| map50 | 0.663366 |
| map50_95 | 0.663366 |
| precision | 0.666667 |
| recall | 0.666667 |
| f1 | 0.666667 |
| tp | 2 |
| fp | 1 |
| fn | 1 |
| exclusions | 2 |
| threshold_policy | {'image': None, 'pixel': None, 'pixel_score_range': None, 'detection': 0.9, 'source_split': 'validation', 'validation_ids_sha256': '9656b3b87e552a6329eb9168389e6b536b517ad05487ea37ce4a9955372fae7b', 'protocol_sha256': '582a7377118d32cb2b0397e5416211702445796d92deb4aaf11086d3a4decab7', 'data_kind': 'SYNTHETIC'} |
| validation_product_count | 2 |

## 9. 클래스별 성능

| 항목 | 관측값 |
|---|---|
| AK | {'class_id': 0, 'ap': 0.6633663366336634, 'ap50': 0.6633663366336634, 'recall': 0.6666666666666667} |
| BX | {'class_id': 1, 'ap': None, 'ap50': None, 'recall': None} |

## 10. 품목·시점별 성능

| 항목 | 관측값 |
|---|---|
| synthetic_product | {'n': 8, 'auroc': None, 'ap': None, 'precision': 0.6666666666666666, 'recall': 0.6666666666666666, 'f1': 0.6666666666666666} |

| 항목 | 관측값 |
|---|---|
| C1 | {'n': 2, 'auroc': None, 'ap': None, 'precision': 1.0, 'recall': 1.0, 'f1': 1.0} |
| C2 | {'n': 2, 'auroc': None, 'ap': None, 'precision': 0.0, 'recall': 0.0, 'f1': 0.0} |
| C3 | {'n': 2, 'auroc': None, 'ap': None, 'precision': 1.0, 'recall': 1.0, 'f1': 1.0} |
| C4 | {'n': 1, 'auroc': None, 'ap': None, 'precision': 0.0, 'recall': 0.0, 'f1': 0.0} |
| C5 | {'n': 1, 'auroc': None, 'ap': None, 'precision': 0.0, 'recall': 0.0, 'f1': 0.0} |

## 11. 예측 이미지와 그래프

### Train / Validation loss

![Train / Validation loss](figures/report_2/loss.png)

관측 이력만 표시. 합성 Run의 곡선은 실제 학습 결과가 아니다.

### Loss components

![Loss components](figures/report_2/loss_components.png)

관측 이력만 표시. 합성 Run의 곡선은 실제 학습 결과가 아니다.

### Learning rate

![Learning rate](figures/report_2/learning_rate.png)

관측 이력만 표시. 합성 Run의 곡선은 실제 학습 결과가 아니다.

### Gradient norm

![Gradient norm](figures/report_2/gradient_norm.png)

관측 이력만 표시. 합성 Run의 곡선은 실제 학습 결과가 아니다.

### Epoch duration

![Epoch duration](figures/report_2/epoch_seconds.png)

관측 이력만 표시. 합성 Run의 곡선은 실제 학습 결과가 아니다.

### Validation metrics

![Validation metrics](figures/report_2/validation_metrics.png)

관측 이력만 표시. 합성 Run의 곡선은 실제 학습 결과가 아니다.

### Confusion matrix

![Confusion matrix](figures/report_2/validation_confusion.png)

GT행/예측열, BACKGROUND 행은FP·열은FN. 클래스무관 IoU 매칭 표다.

### validation category

![validation category](figures/report_2/validation_category.png)

고정 Validation Threshold의 그룹별 F1. 단일/소량 표본은 일반화 근거가 부족하다.

### validation view

![validation view](figures/report_2/validation_view.png)

고정 Validation Threshold의 그룹별 F1. 단일/소량 표본은 일반화 근거가 부족하다.

### Confusion matrix

![Confusion matrix](figures/report_2/test_confusion.png)

GT행/예측열, BACKGROUND 행은FP·열은FN. 클래스무관 IoU 매칭 표다.

### test category

![test category](figures/report_2/test_category.png)

고정 Validation Threshold의 그룹별 F1. 단일/소량 표본은 일반화 근거가 부족하다.

### test view

![test view](figures/report_2/test_view.png)

고정 Validation Threshold의 그룹별 F1. 단일/소량 표본은 일반화 근거가 부족하다.

### Latency distribution

![Latency distribution](figures/report_2/latency.png)

전처리/후처리를 분리했다. 다른 GPU나 batch/input 집합과 속도 순위를 합치지 않는다.

### Run / stability events

![Run / stability events](figures/report_2/stability_events.png)

NaN/Inf·중단·예외 등 관측 사건이다. 사건이 없다고 실제 학습 안정성이 입증된 것은 아니다.

![prediction example](figures/cases_v2/test_NG_C1.png)

내부 검토용 예측 예시. 제목의 SYNTHETIC/REAL 출처와 GT 제공 여부를 확인한다.

![prediction example](figures/cases_v2/test_NG_C2.png)

내부 검토용 예측 예시. 제목의 SYNTHETIC/REAL 출처와 GT 제공 여부를 확인한다.

![prediction example](figures/cases_v2/test_NG_C3.png)

내부 검토용 예측 예시. 제목의 SYNTHETIC/REAL 출처와 GT 제공 여부를 확인한다.

![prediction example](figures/cases_v2/test_NG_C5.png)

내부 검토용 예측 예시. 제목의 SYNTHETIC/REAL 출처와 GT 제공 여부를 확인한다.

![prediction example](figures/cases_v2/test_OK_C1.png)

내부 검토용 예측 예시. 제목의 SYNTHETIC/REAL 출처와 GT 제공 여부를 확인한다.

## 12. FP/FN 및 실패 사례

| 항목 | 관측값 |
|---|---|
| tp | 2 |
| fp | 1 |
| fn | 1 |
| pixel_exclusions | N/A |
| exclusions | [{'image_id': 'test_NG_C4', 'reason': 'MISSING_ANNOTATION'}, {'image_id': 'test_NG_C5', 'reason': 'EMPTY_NG_REVIEW'}] |

## 13. 추론 속도

| 항목 | 관측값 |
|---|---|
| subject | SYNTHETIC_TINY_CONV_NOT_OFFICIAL_MODEL |
| model_only | {'mean_ms': 0.01613300119061023, 'p50_ms': 0.014293007552623749, 'p95_ms': 0.02169599465560168, 'samples_ms': [0.023204993340186775, 0.015659999917261302, 0.014293007552623749, 0.0136339949676767, 0.013873010175302625], 'repetitions': 5, 'batch_size': 1, 'throughput_images_s': 61984.74717661476, 'fps': 61984.74717661476} |
| end_to_end | {'mean_ms': 0.015865397290326655, 'p50_ms': 0.01551299646962434, 'p95_ms': 0.017260393360629678, 'samples_ms': [0.017557991668581963, 0.01607000012882054, 0.01551299646962434, 0.015068988432176411, 0.015117009752430022], 'repetitions': 5, 'batch_size': 1, 'throughput_images_s': 63030.25267509143, 'fps': 63030.25267509143} |
| stages | {'preprocess': {'mean_ms': 0.00429799547418952, 'p50_ms': 0.004278990672901273, 'p95_ms': 0.004666991299018264, 'samples_ms': [0.004706991603597999, 0.004506990080699325, 0.004278990672901273, 0.003863999154418707, 0.0041330058593302965], 'repetitions': 5, 'batch_size': 1, 'throughput_images_s': 232666.60144368152, 'fps': 232666.60144368152}, 'model': {'mean_ms': 0.010638000094331801, 'p50_ms': 0.010490999557077885, 'p95_ms': 0.011288211680948734, 'samples_ms': [0.011414012988097966, 0.010785006452351809, 0.010490999557077885, 0.010242991265840828, 0.010256990208290517], 'repetitions': 5, 'batch_size': 1, 'throughput_images_s': 94002.6312401356, 'fps': 94002.6312401356}, 'postprocess': {'mean_ms': 0.0003766035661101341, 'p50_ms': 0.00037001154851168394, 'p95_ms': 0.0004189903847873211, 'samples_ms': [0.0004249886842444539, 0.0003949971869587898, 0.0003440072759985924, 0.00037001154851168394, 0.0003490131348371506], 'repetitions': 5, 'batch_size': 1, 'throughput_images_s': 2655312.084080371, 'fps': 2655312.084080371}} |
| model_load_seconds | 0.000221952 |
| hardware_sha256 | 36b4fb23b79993321ec8089bd317380eccc7c5339fe4dc22d2696e822064bf85 |
| batch_size | 1 |
| warmup | 2 |
| repetitions | 5 |
| input_set_sha256 | 6bdd3fa86a3d8053559cca0de38f72ae47a8eebf5e229ce633d9b532101e703b |

## 14. 모델 크기

| 항목 | 관측값 |
|---|---|
| parameters | 56 |
| trainable_parameters | 56 |
| checkpoint | {'bytes': 41, 'sha256': '702b18d9d885274576226b38b05b66892726908b711da417b8ec7fbc5e07d2e3'} |
| memory_bank_bytes | N/A |
| search_index_bytes | N/A |

## 15. 메모리

| 항목 | 관측값 |
|---|---|
| peak_cpu_rss_bytes | 525717504 |
| cpu_rss_baseline_bytes | 525713408 |
| cpu_rss_delta_bytes | 4096 |
| rss_measurement | sampled_process_RSS_5ms_not_exact_model_memory |
| gpu_memory | {'model_only': None, 'end_to_end': None} |

## 16. 실패와 한계

상태: PARTIAL. 실제 GPU·공식 모델 통합 여부는 별도 확인한다. 미측정 값은 N/A다.

| 항목 | 관측값 |
|---|---|
| missing_plots | [] |
| events | [{'time_utc': '2026-11-13T02:36:08.271037+00:00', 'event': 'STARTED'}, {'time_utc': '2026-11-13T02:36:09.429636+00:00', 'event': 'PARTIAL', 'training_executed': False}] |

## 17. 재현 명령어

```bash

uv run --locked python scripts/experiments/smoke_test_reporting.py

```

[설정](config.json) · [환경](environment.json) · [학습 이력](training_history.csv)
