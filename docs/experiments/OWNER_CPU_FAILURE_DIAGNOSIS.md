# Owner CPU 학습 실패 진단 (최종 보고서)

기존 실행은 읽기 전용으로 보존했다. 전체 50 epoch를 재실행하지 않았다.
본 보고서는 첫 진단(2026-11-16, 이전 에이전트)과 인수인계 완료 검증(2026-11-16, 본 세션)을 합쳐 정리한다.

- CONFIRMED: EfficientAD는 epoch 3의 calibration에서 실패했다. 로그 5445 / 저장 checkpoint 3630 차이는 validation 이후 저장 순서로 설명된다. 실패 순간 가중치와 실패 map 증거는 저장되지 않았다.
- CONFIRMED: RetinaNet은 32 step 이후 비유한 Loss로 실패했다. 원인은 입력 결함이 아니라 random 초기화 SGD 업데이트의 발산이다(초기 40개 입력 좌표·라벨 검사 통과).
- CONFIRMED: 세 안정화 후보(lr0.01+clip1.0, lr0.001, lr0.001+clip1.0)는 모두 기존 발산 지점(31~33 step)을 지나 40+1 update까지 유한했다.
- CONFIRMED: YOLO11은 7 epoch(609539 update)까지 정상 기록되었고 체크포인트 무결성이 검증됐다. 다만 코드 지문 불일치로 기존 Run 직접 resume은 계약상 거부된다.
- UNKNOWN(유지): EfficientAD epoch 3 quantile 퇴화의 정확한 원인. 실패 map 증거가 없어 임의 eps 우회 없이 미해결로 둔다.

진단 산출물: `outputs/owner_failure_diagnosis_20261116_v1/` · 안정화 비교: `outputs/owner_stabilization_20261116_v1/`
보존 대상 해시: `outputs/owner_failure_diagnosis_20261116_v1/protected_before.json`

---

## 1. 인수인계 당시 상태

- git 작업 트리: 훈련 인프라 전체(`mv_analysis/training/`, `models/_shared/`, 각 backend/train.py, 일부 tests)가 미추적 신규 파일. 추적 파일 변경은 `integration.py` 3종 + README(실구현 진입점 연결, 빈 설정 NotImplementedError 계약 유지).
- 테스트: 이전 기록 `317 passed / 2 failed / 8 errors` — 실패 10건 전량 일시 환경 요인(소켓 생성 PermissionError, 전체 실행 부하 중 worker 타임아웃). 코드 회귀 아님.
- EfficientAD: 체크포인트 2개(epoch 1·2, 마지막 step 3630) 존재, 학습 기록은 step 5445까지. epoch 3 calibration 실패.
- RetinaNet: 기존 발산 재현 완료(baseline). 후보 A(clip) 시도는 recorder만 생성된 빈 상태.
- YOLO11: 7 epoch 체크포인트, 네이티브 last/best/epoch0~6.pt 존재.

## 2. 기존 수정 사항 검증 결과

이전 에이전트 수정(모두 의도와 구현 일치 확인, 집중 회귀 106 passed):

- `models/anomaly/efficientad_s/backend.py`: `CalibrationError`가 진단 보존 + 기존 quantile 버퍼 보호(실패 시 `quantiles.copy_` 미실행). `calibration_quantiles`는 공식 float32 q90/q99.5 검증으로, epsilon/다른 분위수 우회 없음. `calibrate_maps`는 이미지별 input/st/ae `tensor_stats` evidence 기록.
- `models/_shared/runtime.py`: calibration 직전 스냅샷 저장, `calibration_pending` phase로 실패 epoch 재학습 없이 calibration 재시도, `checked_losses`/`clip_grad_norm_(error_if_nonfinite=True)`/update 후 parameter finite 검사, 실패 시 `failure_diagnostics.json` 기록.
- `models/detection/retinanet/backend.py`·`preprocessing.py`: 입력 이미지/bbox/라벨 검증, 공식 matcher·head 관찰 진단(compute_loss 수치 변경 없음), 좌표계·라벨 오프셋(0→1) 명확화.
- `models/_shared/diagnostics.py`: `tensor_stats`/`checked_losses`/`sample_evidence`.
- `mv_analysis/training/{runner,state,worker}.py`: lease 기반 중복 실행 방지, checkpoint 등록·검증 계약, worker 응답의 `training_evidence` 집계(예외 경로 포함).
- `tests/test_owner_failure_diagnosis.py` 포함 신규 회귀 테스트.

본 세션 추가 수정:

- `scripts/experiments/diagnose_owner_failures.py`
  1. recorder가 고정하는 evaluation ID를 실제 평가 subset과 일치시킴. 기존에는 전체 validation ID를 고정핆고 4장 subset을 평가해 `Evaluation image set differs from frozen config` 오류 발생 — retinanet 분기는 40 update를 전부 통과했을 때만 드러나는 잠재 버그였다. efficientad/retinanet 양 분기 수정.
  2. `--learning-rates`·`--clippings` 인수 추가(후보 비교용). 인수 없으면 기존 동작과 동일.
  3. result.json에 `learning_rate` 기록.

## 3. EfficientAD-S 상태

- 실제 학습 실행 확인. epoch 1·2 checkpoint 존재, 마지막 정상 global_step 3630, 학습 기록은 step 5445(=3 epoch분)까지 유한(loss_total 3.73, grad 40.5).
- 실패: `ValueError: Degenerate validation map quantiles` — epoch 3 배치 종료 후 calibration에서 발생. 실패 순간 가중치는 저장되지 않았고, 당시 코드에는 실패 map 진단 기록이 없어 **원인은 UNKNOWN**으로 유지.
- 재개 검증(`efficientad_bounded/`): checkpoint 3630 복원 → 3 update → 저장/복원 → step 3633 손실 4.028(유한). resume.json으로 계약 확인. calibration_before(15장 OK 표본): st q90=0.524313/q99.5=0.524613(폭 0.000299, VALID), ae 0.0652→0.2907(VALID). calibration_after(4 update 후): st 0.51446→0.51833(VALID). 4장 표본 validation AUROC 1.0(정보용).
- 위험 신호: 마지막 양호 체크포인트 기준 st map 분포가 표본 상단에서 극도로 좁다(폭 3e-4). q99.5>q90 조건이 한계에 가까우며, epoch 3의 1815 update 중 어느 지점에서 상단 분포가 붕괴(q99.5≤q90)하거나 비유한 값이 섞였을 가능성을 배제할 수 없다. 추가 확정 증거 없음.
- 코드 경로는 실패 후에도 기존 버퍼를 보호하고 calibration 직전 상태로 재개 가능하다(`calibration_pending`).

## 4. RetinaNet 안정화 비교

동일 seed(42)·동일 입력 순서(첫 41개)·800px·random init·SGD, CPU 4 thread. 각 후보 최대 40 update + checkpoint 저장/복원 후 41번째 update + 4장 validation subset. 기존 baseline 재현 로그를 그대로 비교에 사용했다(무의미한 재현 반복 안 함).

| 측정 항목 | 기존 lr0.01 clip 없음 | A: lr0.01 + clip1.0 | B: lr0.001 clip 없음 | C: lr0.001 + clip1.0 |
| --- | --- | --- | --- | --- |
| 완료 update | 32 후 실패 | **40 + resume 41** | **40 + resume 41** | **40 + resume 41** |
| loss_total 최대 | 1.58e14 (step 32) | 5.38 | 2.93 | 2.93 |
| classification loss 최대 | 1.58e14 | 4.76 | 1.54 | 1.54 |
| bbox loss 최대 | 1.77e6 | 1.62 | 1.61 | 1.60 |
| gradient norm 최대(pre-clip) | 2.13e16 | 495 | 66 | 153 |
| parameter norm(최종) | 2.13e14(발산) | 275.4 | 275.5 | 275.5 |
| 비유한 loss 항목 | 0(단 step 33에서 NONFINITE raise) | 0 | 0 | 0 |
| step 30~33 loss | 13.6 / 1473.7 / 1.58e14 | 3.06 / 0.03 / 4.63 / 0.02 | 1.77 / 0.78 / 1.96 / 0.78 | 1.80 / 0.76 / 1.95 / 0.76 |
| 소요 시간(40 update) | — | 245.8s | 211.4s | 210.9s |
| 정상 종료 | FAILED | 성공 | 성공 | 성공 |
| resume step 41 loss | — | 0.0099 | 0.7649 | 0.7437 |

- 세 후보 모두 기존 발산 지점(step 31~33)을 통과했다. 발산 자체가 사라진 것이 아니라 억제된 것이므로, clip 없는 lr0.001(B)도 언젠가는 불안정할 수 있다. 41 update 관측으로 장기 안정성을 주장하지 않는다.
- 후보 A(lr0.01+clip)는 유한하지만 loss가 0.01~5.4로 격렬히 진동(clip이 폭발만 막고 방향성 불안정은 남김). B·C(lr0.001)는 loss가 0.76~1.96 범위로 완만.
- 4장 validation subset의 map50·map50_95는 세 후보 모두 0.0 — 41 update로는 탐지 성능이 나오지 않으며, 이는 bounded 진단으로 성능 개선 주장의 근거가 아니다.
- peak memory는 스크립트에 측정 계측이 없어 기록하지 못했다. 실행 중 OOM은 없었다.

근거 요약: 입력 40개 좌표·라벨 검사 통과 + OK empty target 정상 처리 + positive anchor 없을 때 bbox loss 0은 정상 + 발산이 optimizer 업데이트 시점에 발생 → 데이터 좌표 오류보다 optimizer 불안정. clip/LR 감소가 발산을 억제함을 확인.

## 5. YOLO11 체크포인트 상태

- checkpoint_latest.json → `checkpoint_3c6fb0e8…`: completed_epochs=7, global_step=609539, 등록 sha256/bytes 일치(이전 세션 + 등록 계약 확인).
- 7개 checkpoint(step 87077×1…7) 전부 해시 유효. 네이티브 가중치 `native_runs/<attempt>/weights/`에 last.pt·best.pt·epoch0~6.pt 존재.
- resume 메커니즘: 네이티브 last.pt + 스냅샷(model/optimizer/scheduler/scaler/RNG) 이중 복구, 해시 검증, `Trainer.resume_training` 확장 — 구현 확인.
- **재개 가능 여부: 메커니즘상 가능하나, 현재 코드로는 기존 Run을 resume할 수 없다.** `RunStore.verify()`의 code_fingerprint가 weekend Run 계획의 code_sha256(759eb345…)와 현재(66ac0ce0…)가 달라 거부. 지문은 이전 에이전트의 하드닝 수정(정당한 개선) 때문에 변경됐다. 이 건은 EfficientAD·RetinaNet에도 동일하게 적용된다.
- 강제로 지문을 맞추거나 검사를 우회하지 않는다. YOLO11을 이어가려면 새 Run을 만들고, 원하면 네이티브 last.pt/best.pt를 가중치로 등록해 웜스타트한다(새 설정에 weights 해시가 묶인다).

## 6. 테스트 통과/실패 결과

- 전체 스위트(본 세션 재실행): **329 passed, 1 warning (68s)**.
- 이전 실패 10건의 원인 분류:
  - `test_product_bbox_review_http.py` 8 errors + `test_crop_range_review.py` 1 failed: `ThreadingHTTPServer` 생성 시 `PermissionError` — 당시 환경의 소켓 생성 제한. 현재는 동일 테스트 47 passed로 소거.
  - `test_training_runner.py::test_full_worker_smoke_and_checkpoint_resume` 1 failed: 전체 실행 부하 중 60s 타임아웃. 단독 실행 8.6s 통과로 소거.
- 코드 결함으로 분류된 것은 없음. 테스트 삭제·skip 처리 없음.

## 7. 실제 수정 파일 목록

인수인계 목록(이전 에이전트, 검증 완료): `models/_shared/diagnostics.py`, `models/_shared/runtime.py`, `models/anomaly/efficientad_s/backend.py`, `models/detection/retinanet/backend.py`, `models/detection/retinanet/preprocessing.py`, `mv_analysis/training/runner.py`, `mv_analysis/training/state.py`, `mv_analysis/training/worker.py`, `tests/test_owner_failure_diagnosis.py`. (이 외 훈련 패키지 파일들은 미추적 신규 작성분.)

본 세션 추가: `scripts/experiments/diagnose_owner_failures.py`(recorder subset 고정 + 후보 인수). 진단 산출물은 `outputs/owner_failure_diagnosis_20261116_v1/`, `outputs/owner_stabilization_20261116_v1/` 신규 생성.

## 8. 데이터 및 체크포인트 보존 여부

- 데이터 릴리스: `state.json`의 data_sha256(e790c7…)가 checkpoint 바인딩과 일치, 이전 세션 preservation_validation(140 files, changed=[]) — 불변 확인.
- 기존 Run/checkpoint/figure/로그: 무수정 보존(읽기 전용 진단만 수행, 원자 저장 경로만 신규 생성).
- 파괴 명령(`git reset --hard`, `git clean`, `rm -rf`) 미사용. 실패한 진단 산출물은 삭제하지 않고 `efficientad_bounded_partial/`로 이름만 바꿔 보존.

## 9. 남은 문제

1. EfficientAD epoch 3 quantile 퇴화 원인 — UNKNOWN. 실패 map/가중치 증거 부재. 전수 replay는 약 2시간 CPU로 제한 진단 범위를 넘어 수행하지 않았다.
2. RetinaNet 장기 안정성 — 41 update까지만 확인. clip/LR 값은 검증 후보이지 확정 해결책이 아니다.
3. Peak memory 측정 미기록(계측 부재).
4. YOLO11 epoch 8 일부(609539→675037 step)는 마지막 체크포인트 이후 기록이며 복구 대상 아님(체크포인트 기준 재개).

## 10. 모델별 학습 재개 가능 여부

- EfficientAD-S: 마지막 양호 checkpoint(epoch 2, step 3630)로부터 새 Run 재개 가능. 코드는 현재 하드닝 버전을 사용하고, calibration 실패 시 버퍼 보호 + calibration_pending 재개가 동작한다. 다만 원인 미확정이므로 같은 설정으로 재개하면 재실패 가능성이 있다.
- RetinaNet: 재개 설정 변경 근거 확보(아래 후보). 발산 억제 확인됐으나 성능 개선 미검증 — 장기 실행 전 추가 검토 권장.
- YOLO11: 체크포인트·네이티브 가중치 무결성 확보. 새 Run + 선택적 웜스타트(last.pt/best.pt)로 재개 가능.

## 11. 실행 권장 명령

- 제한 진단(안전, 수 분 이내): `uv run --offline python scripts/experiments/diagnose_owner_failures.py --source-run outputs/owner_cpu_training/weekend_20261113T112234_d1bb183d4dd24b6d81ce479bb9e3288e --output <새디렉터리> --model <키> [--learning-rates … --clippings …]`
- 회귀 테스트: `uv run --offline python -m pytest tests/ -q`
- 전체 50 epoch 학습: 승인 없이 시작하지 않는다. 재개가 필요하면 `scripts/experiments/run_weekend.py --resume …` 대신 **새 Run**으로 생성하고(코드 지문 변경으로 기존 Run resume은 거부됨), RetinaNet 설정은 위 후보 비교를 참고해 결정한다.
