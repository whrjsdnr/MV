# 모델별 팀원 작업 영역

Owner 3개 모델(EfficientAD-S, RetinaNet, YOLO11)의 실제 전처리·로더·학습·평가·시각화 코드는 각 모델 폴더에 구현되어 있다.
[CPU 50 epoch / batch 1 실행 안내](../docs/experiments/OWNER_CPU_TRAINING.md)를 따른다.
나머지 9개 모델은 기존 계약/TODO 인터페이스를 유지하며 담당 팀원이 구현한다.

가중치·체크포인트·memory bank·검색 인덱스는 GitHub에 올리지 않는다. 추론/연결 코드·설정·Markdown 결과와 공유 가능한 그래프를 PR로 제출하고, weights는 SHA-256과 함께 별도 수령한다.
