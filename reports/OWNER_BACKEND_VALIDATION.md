# Owner CPU Backend 검증 결과

검증일: 2026-11-13. **전체 50 epoch 학습은 미실행**이다. 현재 요청은 실행 준비이며 장시간 학습은 사용자가 시작한다.

## 확정 실행 설정

- 순서: EfficientAD-S → RetinaNet → YOLO11. CPU / 50 epoch / batch size 1.
- EfficientAD-S는 30개 품목 각각 정상 Train으로 50 epoch를 수행한다.
- RetinaNet은 명시적 랜덤 초기화, EfficientAD는 고정 Teacher, YOLO11은 기존 yolo11n.pt를 사용한다.

## 실제 수행한 검증

|모델|실제 학습|Validation|Test|입력 크기|결과|
|---|---:|---:|---:|---|---|
|EfficientAD-S|audiojack Train 1장 / 1 epoch / 1 update|OK/NG 각 1장|OK/NG 각 1장|256|학습·평가·예측 PNG·Benchmark·보고서 완료|
|RetinaNet|Train 1장 / 1 epoch / 1 update|OK/NG 각 1장|OK/NG 각 1장|64 (Smoke 전용)|학습·평가·예측 PNG·Benchmark·보고서 완료|
|YOLO11|Train 1장 / 1 epoch / 1 update|OK/NG 각 1장|OK/NG 각 1장|64 (Smoke 전용)|학습·평가·예측 PNG·Benchmark·보고서 완료|

축소 Smoke 입력에서 얻은 성능/시간은 기본 RetinaNet800 / YOLO640의 전체 데이터 성능이나 소요시간이 아니다.

학습 전후 승인 Crop, 원본 BBox, 클래스 ID, Split을 v2 로더가 유지한다. 마스크 미제공 NG는 D1 학습에서 제외한다.

## 실제 결과 파일

- efficientad_s: [실제 소량 Run 보고서](../outputs/owner_backend_validation_v1/verified_runs/weekend_20261113T111313_ed4d922ee75a425d9d37743b243f4cfe/efficientad_s/audiojack/runs/run_20261113T111347_61538ad2de2f41eba754dfe2037d5783/report.md)
- yolo11: [실제 소량 Run 보고서](../outputs/owner_backend_validation_v1/verified_runs/weekend_20261113T111313_ed4d922ee75a425d9d37743b243f4cfe/yolo11/runs/run_20261113T111458_5f7c1e70e72d43fa8f761fa3b2ea662f/report.md)
- retinanet: [실제 소량 Run 보고서](../outputs/owner_backend_validation_v1/verified_runs/weekend_20261113T111313_ed4d922ee75a425d9d37743b243f4cfe/retinanet/D1/runs/run_20261113T111433_d6cb5670e4854d9eaeb5446bf52d46c2/report.md)

## 테스트 및 보존

- 전체 pytest: **309 passed, 1 warning**. 새 Owner 테스트 22개를 포함한다.
- 최초 sandbox 실행의 localhost 검수 서버 9건은 소켓 제한으로 실패했다. 테스트를 제외하지 않고 loopback 허용 환경에서 전체를 다시 실행해 통과했다.
- 경고 1건은 기존 NumPy timedelta deprecation이다.
- 모델별 독립 Python import, v2 데이터 사전검사, Owner 최종 설정 Dry Run: 3/3 통과.
- 체크포인트 원자 저장/해시/위변조 거부, RNG 복구, SGD/Adam·Scheduler 복구 후 동일 다음 update를 검사했다.
- 최종 코드의 실제 50 epoch 중단/재개, 모든 품목 장시간 안정성은 미검증이다.
- pyproject.toml/uv.lock은 HEAD와 바이트 일치, v2 ZIP/Canonical SHA는 이전 배포값과 일치한다.
- 원본과 승인 Ledger를 수정하는 코드는 실행하지 않았다. Git Commit/Push는 하지 않았다.

## 확인된 한계

- EfficientAD의 선택 저장소는 논문 저자 공식 구현이 아닌 고정 재현 구현이다. ImageNet penalty는 사용하지 않는 조건이다.
- TorchVision 설치 wheel의 Git commit은 f12281517f1b2f6255904639b027c9436f3e5008이며 수집 소스 4260301과 다르다. 고정 소스/실제 런타임의 완전 일치도는 UNVERIFIED다.
- YOLO 공식 loop의 Best 선택은 native Validation fitness이다. 최종 비교는 공통 COCO 평가와 Validation 고정 threshold로 다시 수행한다.
- CPU Benchmark의 전처리/후처리 포함 범위는 모델별 benchmark.json의 scope_note를 따른다.
- Teammate 3개 및 다른 모델 Backend는 이 작업에서 구현하지 않았다.

## 실행

```bash
cd ~/MV
uv run --offline python scripts/experiments/run_owner_cpu.py
```

[실행·복구 가이드](../docs/experiments/OWNER_CPU_TRAINING.md) · [검증 JSON](../outputs/owner_backend_validation_v1/validation.json) · [전체 테스트 로그](../outputs/owner_backend_validation_v1/pytest_final.log)
