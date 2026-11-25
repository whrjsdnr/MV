# YOLO11 — 팀원 구현 계약

공식 소스: https://github.com/ultralytics/ultralytics

고정 commit: `d2b7876e79ad2e02fd77221622774b511a8f0cb3`. 임의로 최신 HEAD로 바꾸지 않는다. 실제 모델 통합은 **UNVERIFIED / TODO**다. 담당자 이름은 팀에서 정한다.

## 시작 순서

[전처리 계약](preprocessing_contract.md) → [학습 연결 계약](train_contract.md) → [평가 계약](evaluation_contract.md) → [완료 체크리스트](integration_checklist.md)를 따른다. `integration.py`는 미구현 인터페이스이며 실행 가능한 Train 명령이 아니다.

1. 공식 소스를 MV 밖에 Clone하고 위 commit·라이선스를 확인한다.
2. 담당 GPU PC에 별도 환경을 준비하고 GPU/VRAM/CUDA/torch를 기록한다.
3. 승인된 Manifest/주석/클래스 매핑을 받아 기존 공통 Dataset을 연결한다.
4. 전처리·forward·학습 단계·Validation·Test·Benchmark를 차례로 검증한다.
5. 공통 Recorder와 [평가 규약](../../../docs/experiments/EXPERIMENT_PROTOCOL.md)을 사용해 Run과 Markdown을 생성한다.

## 결과 공유

GitHub에는 추론/연결 코드·실행 설정·Markdown 결과와 권한이 확인된 그래프를 제출한다. **가중치·체크포인트·메모리 뱅크·검색 인덱스는 올리지 않는다.** 별도 팀 채널로 전달하고 파일명·bytes·SHA-256·수령 방법을 보고서에 적는다. 비밀 URL/토큰/개인 절대 경로는 공개하지 않는다.

모델별 공식 학습 함수/전처리/출력은 담당자가 고정 소스를 조사해 구현한다. 공통 시스템이 이 모델의 실제 학습 성공을 보증하지 않는다.

## CPU Backend 구현 추가

전처리·로더·학습·평가·시각화 진입점은 이 폴더의 Python 파일입니다.
[Owner CPU 실행 가이드](../../../docs/experiments/OWNER_CPU_TRAINING.md)를 먼저 확인하세요.
기존 TODO 문서는 초기 계약 기록이며, 실제 연결 상태는 새 가이드와 검증 로그를 따릅니다.
