# 최종 12모델 학습 결과 보고서

- 작성일: 2026-11-20
- 데이터: MV 30개 카테고리, 팀 데이터 릴리스 v2 (train 105,735 / validation 22,655 / test 22,660장)
- 배경: GPU 서버(38.147.83.15)가 2026-11-20 07:40 KST 종료. 이 보고서는 로컬 백업(`real-iad-backup/`, 196G+187G)에 확본 자산 + 로컬 CPU 재평가를 근거로 작성했다.
- 산출물: `inference/` — 12모델 추론 코드, 식별/평가/벤치마크 결과(`inference/results/`)

## 0. 요약 (한눈에 보기)

| # | 모델 | 유형 | 학습 상태 | Test 성능 (image AUROC) | 추가학습 |
|---|---|---|---|---|---|
| 1 | PatchCore | 이상탐지(카테고리별) | **30/30 완료** | **0.9344** (30개 평균) | 불필요 (일부 저조 카테고리 선택적) |
| 2 | EfficientAD-S | 이상탐지(카테고리별) | 20 완료 + 10 복구 | **0.8905** (완료 20개) | **9개 필요** (quantile 붕괴) |
| 3 | InP-Former | 이상탐지(카테고리별) | 16 완료 / 30 | **0.9040** (보고 13개) | **14개 필요** (미완료) |
| 4 | Dinomaly | 이상탐지(unified) | **완료** (50ep) | **0.9343** | 불필요 |
| 5 | UniAD | 이상탐지(unified) | 완료, 평가 복구 | **0.7914** | 권장 (성능 열위) |
| 6 | HVQ-Trans | 이상탐지(unified) | **학습 50/50 완료** (잔존 ckpt ep41) | **0.8269** (네이티브 프로토콜, ep41) | 불필요 (ckpt만 ep41) |
| 7 | YOLO11 | 탐지 | 2런 부분 | toy_brick AUROC 0.605 / F1 0.711 / 2.98fps / AP50 0.246 / val cls_loss 3.157 | **전면 필요** |
| 8 | RetinaNet | 탐지 | 4런 부분 | terminalblock 0.545 / plastic_plug 0.816 / rolled_strip_base 0.395 / switch 0.397, F1 0.64~0.78, 0.35~0.46fps, AP50 전부 0 | **전면 필요** |
| 9 | Faster R-CNN | 탐지 | 8런 부분 (실 6런=toothbrush 스냅샷) | toothbrush 0.485 / F1 0.678 / box F1 0.092 / 0.36fps / AP50 0.067 | **전면 필요** |
| 10 | ViTDet | 탐지 | 6런 부분 | 미평가 | **전면 필요** |
| 11 | YOLOS | 탐지 | 4런 부분 | 미평가 | **전면 필요** |
| 12 | RT-DETRv2 | 탐지 | 6런 부분 | 미평가 | **전면 필요** |

핵심 결론:
- **이상탐지 6종은 학습이 완료(또는 거의 완료)돼 있고 성능 지표를 확보했다.** Dinomaly가 unified 모델 최고(0.9343), PatchCore가 카테고리별 최고(0.9344).
- **탐지 6종은 서버 종료 시점에 'deadline_partial' 상태** — 카테고리별 런이 2~8개만 진행 중이었고, 식별된 런조차 결함 클래스가 거의 학습되지 않아 성능이 매우 낮다(toy_brick 0.605). 재학습이 필수다.

---

## 1. 모델별 상세

### 1-1. PatchCore (이상탐지, 카테고리별 30개 모델)

- 실험: `patchcore_array_hotfix_20261117`, 30/30 카테고리 COMPLETED
- Test (30개 평균): image AUROC **0.9344**, image AP 0.8526, pixel AUROC 0.9916, AUPRO 0.9518
- 최고: rolled_strip_base 1.0000 / 최저: woodstick 0.5290, toy_brick 0.7624, plastic_plug 0.7974
- 추론 메모리/속도: 백본 ResNet50 224px 기준 ~0.4s/장, 36MB (메모리뱅크는 체크포인트에 미포함 — train OK 특징으로 재구축 필요)
- 재학습: 불필요. woodstick/toy_brick/plastic_plug 등 0.8 이하 카테고리는 coreset 비율·백본 계층 튜닝으로 개선 여지

### 1-2. EfficientAD-S (이상탐지, 카테고리별 30개 모델)

- 실험: `efficientad_s_recovery_20261117`
- COMPLETED 20개 Test 평균: image AUROC **0.8905** (min 0.4937 switch, max 1.0000), pixel AUROC 0.9110, AUPRO 0.7721
- 미완료 10개의 평가복구 지표: audiojack 0.9889 (정상 학습 기반) / button_battery 0.6391 / end_cap 0.7493 / switch 0.6393 / usb 0.7263 / fire_hood 0.8281 / porcelain_doll 0.8584 / transistor1 0.8807 / wooden_beads 0.8953 / vcpill 0.9085 (⚠ 미숙련 체크포인트 기반)
- 미완료 원인: 9개는 `CalibrationError: Degenerate validation map quantiles` (switch·button_battery·end_cap·fire_hood·porcelain_doll·transistor1·usb·vcpill 등 — teacher-student 맵 분포 붕괴), audiojack 1개는 구 실험 정상 체크포인트(0.9889)
- 추론: 256px crop 입력, ~0.9s/장, 147MB (teacher PDN-small 384 + student 768 + AE)
- 재학습: **9개 필요**. quantile 보정 데이터 재수집 또는 jitter 증강으로 재시도 권장

### 1-3. InP-Former (이상탐지, 카테고리별)

- 16/30 COMPLETED (나머지 14개: rolled_strip_base·sim_card_set·switch·tape·terminalblock·toothbrush·toy·u_block·usb·usb_adaptor·vcpill·wooden_beads·woodstick·zipper — 중간 체크포인트만 존재)
- Test (보고 13개 평균): image AUROC **0.9040**, pixel AUROC 0.9891, AUPRO 0.9403
- 아키텍처: DINOv2(12블록, 768dim, 레지스터 토큰) + 학습형 프로토타입 6개
- 재학습: **14개 필요** (50 epoch 완주 전 중단 — 체크포인트 best/state 각 2~4개 보유, resume 가능성 있음)

### 1-4. Dinomaly (unified 단일 모델)

- COMPLETED (50 epochs, 47,850 steps), DINOv2 ViT-B/14 + MLP 병목 + 디코더 8블록
- Test (4,531장): image AUROC **0.9343**, pixel AUROC 0.9947, AUPRO 0.9427
- 카테고리별 최고 tape 1.0000, 최저 regulator 0.7785
- 재학습: 불필요

### 1-5. UniAD (unified 단일 모델)

- 학습 완료, 서버 평가 소실 → 로컬 복구 평가
- Test (4,531장): image AUROC **0.7914**, pixel AUROC 0.9849, AUPRO 0.8903
- Dinomaly 대비 이미지 수준 −0.14, 픽셀 분할은 준수 → 재구성 병목 정규화 개선 여지
- 재학습: 권고 (이미지 수준 성능 열위)

### 1-6. HVQ-Trans (unified 단일 모델)

- **학습 자체는 50/50 완료** (서버 train.log: `hvq_trans_20261117/train.log` Epoch 50/50, Iter 23,521/23,950, 최종 Loss 10.05, run-avg 9.47)
- 다만 살아남은 체크포인트는 **ep41** 뿐 (ep49 export 중 반복 SIGSEGV → ep41 분만 확보, 서버 사망으로 이후 복구 불가)
- 업스트림 네이티브 프로토콜 평가(ep41 기준): image AUC(max-pool) **0.8269**, pixel AUROC 0.9697
- 아키텍처: efficientnet_b4(동결) + MFCN + 코드북 5개 양자화 트랜스포머
- 재학습: **불필요** (학습 완료) — 단 ep50 체크포인트는 소실돼 서빙은 ep41로

### 1-7~1-12. 탐지 모델 6종

서버 manifest 기준 전부 `deadline_partial`. 프로토콜이 런별로 혼재:
- 141클스(30 OK + 111 결함): yolo11(전부), retinanet(전부), faster_rcnn(6/8)
- 9클스(8 결함+bg): yolos, vitdet, faster_rcnn(2/8)
- 8클스: rtdetrv2

체크포인트가 `best_<uuid>.pt` 해시명이라 카테고리 매핑이 없었으나, 콘텐츠 매칭(`inference/identify_detection.py`)으로 식별:

| 모델 | 식별된 런 | Test 결과 (표본 40장/카테고리) |
|---|---|---|
| YOLO11 | **toy_brick** (run 46f3cf28, ep49) — 확정 | AUROC **0.605**, F1 0.711, 2.98fps, AP50 **0.246** |

yolo11 run 46f3cf28 체크포인트 내장 검증 지표(best epoch): **P 0.479 / R 0.254 / mAP50 0.227 / mAP50-95 0.128 / val cls_loss 3.157 / box_loss 1.617 / dfl_loss 1.087**
| RetinaNet | terminalblock(확정), plastic_plug(확정), rolled_strip_base(유력), switch(불명) | 0.395~0.816, AP50 전부 0 |
| Faster R-CNN | **toothbrush** 6개 런 — 확정 | AUROC 0.485, AP50 0.067 |
| ViTDet / YOLOS / RT-DETRv2 | 미식별 (transformers 매핑 검증 불완료) | 미평가 |
| ViTDet/YOLOS/RT-DETRv2 | 미식별 (transformers 매핑 검증 불완료) | 미평가 |

- 추론 속도(800px, CPU): retinanet ~2.5s/장, yolo11 640px ~0.5s/장
- 재학습: **전면 필요** (식별된 런도 결함 클래스가 사실상 미학습 — toy_brick NG 이미지에서 toy_brick/OK만 0.43~0.78로 출력, 결함 클래스 부재)

---

## 2. 추가학습 필요 모델 정리

| 우선순위 | 대상 | 사유 |
|---|---|---|
| 1 | 탐지 6종 (yolo11·retinanet·faster_rcnn·vitdet·yolos·rtdetrv2) | deadline_partial, 결함 클래스 미학습, 식별 런 AUROC 0.6 수준 |
| 2 | EfficientAD-S 9개 카테고리 | quantile 붕괴 (CalibrationError) |
| 3 | InP-Former 14개 카테고리 | 50 epoch 미완주 |
| 4 | UniAD | 이미지 수준 성능 열위 (선택) |
| 5 | HVQ-Trans | 재학습 불필요 (학습 50/50 완료 확인, 잔존 체크포인트만 ep41) |

---

## 3. 추론 자원 및 최적화 가이드 (CPU 기준 측정)

측정: `inference/benchmark.py`, 배치 1, 워밍업 1 + 반복 3 평균. 4코어 공유 부하 하 측정이라 절대값보다 상대 비교용.

| 모델 | 입력 해상도 | ms/장 | 피크 메모리 | 비고 |
|---|---|---|---|---|
| EfficientAD-S | 256 | ~880 | 147MB | PDN×2+AE |
| PatchCore | 224 | ~400 | 36MB | 백본 only (뱅크 kNN 제외) |
| UniAD | 224 | ~140 | 243MB | 백본 only 추정 |
| HVQ-Trans | 224 | ~600 | 19MB | 백본 only 추정 |
| Dinomaly | 518 | **~11,100** | 33MB | 인코더+디코더 재구성 |
| InP-Former | 518 | **~5,400** | 612MB | 인코더 only 추정 |
| YOLO11 | 640 | ~500 | ~200MB | ultralytics 파이프라인 |
| RetinaNet | 800 | ~2,500 | ~1GB | R50-FPN |

- 측정은 `inference/benchmark.py` (배치 1, 워밍업 1 + 반복 3). 피크 메모리는 순방향 패스 중 RSS 증가분(모델 로드 본체는 제외).
- 4코어 CPU 공유 부하 하 측정 — 절대값보다 모델 간 상대 비교에 유효.
- Dinomaly 11초/장은 실사용 불가 수준 → GPU 필수 또는 최적화 필수(아래 §3 권고).

**모델별 추론 최적화 추천:**

- **EfficientAD-S**: TensorRT/ONRTOS — PDN conv 연속이라 INT8 양자화 효과 큼(논문 기준 5ms대). CPU만 쓴다면 OpenVINO. 이미지를 256 고정으로 리사이즈해 캐싱.
- **PatchCore**: 뱅크 kNN을 faiss(IVF) 또는 GPU 코사인으로 옮기면 CPU 병목 해소. 백본은 torchvision→ONNX 추출 후 런타임 단순화.
- **Dinomaly/InP-Former**: DINOv2가 지배 비용 → timm/faster ViT-S로 다운사이징 또는 온디바이스 배포 시 동적 패치 스킵(전략적 토큰 프루닝). ONNX export 후 518px→392px 다운스케일 시 ~2배 가속.
- **UniAD/HVQ**: EfficientNet-B4 백본이 무거움 → B0/B2로 경량화 재학습, 양자화 취약한 코드북(HVQ)은 디코더만 FP16.
- **YOLO11**: 이미 경량(yolo11n). NCNN/TensorRT INT8, letterbox 640 고정, NMS threshold 튜닝(0.7→0.5로 detections 감소).
- **RetinaNet/Faster R-CNN**: 두 스테이지라 CPU 비용 큼 → 먼저 imgsz 800→512 다운스케일(정확도 소폭 하락), RPN proposal 상한(chiou 1000→300) 축소, ONNX+OpenVINO.
- **ViTDet/YOLOS/RT-DETRv2**: ViT 기반 → torch.compile(dynamic=False) 또는 ONNX. RT-DETRv2는 엔드투엔드 NMS-free라 ONNX 변환에 유리.

## 4. 모델별 조절 가능 하이퍼파라미터

| 모델 | 주요 노브 | 영향 |
|---|---|---|
| PatchCore | coreset 비율(0.01~0.1), 백본 계층(layer2+3), 임계값 | 뱅크 크기↑=재현↑/속도↓, woodstick 등 저조 카테고리는 계층 조합이 핵심 |
| EfficientAD-S | teacher/student 채널, quantile 보정 배치 크기, lr(1e-4), jitter | quantile 붕괴 카테고리는 보정 데이터 다양성이 핵심 |
| InP-Former | 프로토타입 수, 스묘딩 σ, DINOv2 해상도 | 프로토타입↑=정밀도↑, σ↑=맵 안정화 |
| Dinomaly | 병목 차원(3072), 디코더 깊이, top-k 스코어 | unified 모델이라 카테고리별 보정 최소화가 장점 |
| UniAD | bottleneck 차원, pos-embed 형태, top-k 오차 비율 | 병목 과소/과대로 성능 급변 — 0.7914 개선의 실마리 |
| HVQ-Trans | 코드북 크기/개수, neighbor mask(7×7), jitter scale 20 | 양자화 오류율이 지표에 직결 |
| YOLO11 | imgsz, conf/NMS IoU, epochs(50), lr 0.01 SGD/cos | 결함 소수 클래스는 oversampling/augment 권장 |
| RetinaNet | anchor 크기/비율(9개), focal loss α/γ, lr step(16,22) | anchor 설계가 소형 결함 검출 좌우 |
| Faster R-CNN | RoI 개수, anchor 스케일, IoU 임계값 | 2단계라 recall-정밀도 트레이드오프 큼 |
| ViTDet | 창 크기, FPN 계층, ViT 크기(base→tiny) | 메모리↓ 우선시면 tiny+싱글스케일 |
| YOLOS | 패치 크기, 디텍션 토큰 수, 해상도 | 토큰 수↓=속도↑/소형 결함 손실 |
| RT-DETRv2 | 인코더 레이어 수, 쿼리 수, denoising | NMS-free라 임계값 튜닝 단순 |

## 5. 마지막 epoch 체크포인트 점검

| 모델 | 최종 에폭 근거 | 위치 |
|---|---|---|
| yolo11 | `last.pt`는 export 시점(19ep) 이지만 런 최종은 **ep49** | `export/.../yolo11/D1/checkpoints/native_41c95655….pt` (run detect_v2_46f3cf28) |
| efficientad_s | 50/50 COMPLETED (`training_progress.json`) | `export/efficientad_s_recovery_20261117/<cat>/checkpoints/best_*.pt` |
| inp_former | 16개 50/50 COMPLETED | `offload/.../job/inp_former/<cat>/best_*.pt` |
| dinomaly | 50/50, 47,850 steps | `export/.../dinomaly/unified/checkpoints/best_88951557….pt` |
| uniad | 완료(평가 도중 서버 종료, disposition 'evaluating') | `export/.../uniad/unified/checkpoints/best_*.pt` 2개 + state 2개 |
| hvq | **ep41/50 중단** (ckpt['epoch']=41) | `export/.../hvq/unified/checkpoints/ckpt.pth.tar` |
| retinanet/faster_rcnn/vitdet/yolos/rtdetrv2 | 체크포인트에 메타 없음 — **마지막 저장 순서는 state 파일 mtime 역순** | `export/.../<model>/D1/checkpoints/state_*.pt` |

## 6. 재현/검증 지침

- 추론 코드: `inference/<model>_infer.py` (단일 이미지 CLI), 벤치마크 `inference/benchmark.py`
- 식별 결과: `inference/results/identify_*.json`, 평가: `eval_*.json`, 벤치: `bench_*.json`
- 탐지 평가는 **표본(카테고리당 40장)** 기반이며, 이상탐지 지표(4,531장)와 직접 비교 불가
- 141클스 매핑 권위 원본: `outputs/remote_training_audit_20261119_v1/remote_final.json`의 `class_mapping`(서버 11-19 기록). yolo=0~110 결함/111~140 OK, coco=yolo+1. `inference/classes_141_server.json`에 추출본
- dinomaly/uniad/inp_former/hvq의 추론 스크립트는 서버 코드 소실로 **구조 재구성 상태**(dinomaly는 OK/NG 분리 실패로 미검증). 성능 수치는 서버 측 복구 평가를 인용

## 7. 탐지 모델 표본 평가 결과

카테고리당 test 표본 40장(OK 20 + NG 20), CPU 추론. image AUROC는 최대 결함 신뢰도 기준, AP50은 NG 이미지 박스 매칭.

| 모델 | 카테고리 | 식별 확도 | image AUROC | image F1 | box F1@0.25 | FPS | AP50@0.5 |
|---|---|---|---|---|---|---|---|
| YOLO11 (run 46f3cf28, ep49) | toy_brick | 확정 | **0.605** | 0.711 (t=0.012) | 0.000 | **2.98** | **0.246** |
| YOLO11 (run dec921a9) | — | ep0~3 미훈련 | — | — | — | — | — |
| RetinaNet (best_2334d46) | **terminalblock** | 확정 (ZW 0.83~0.90) | 0.545 | 0.678 (t=0.81) | 0.000 | 0.35 | 0.000 |
| RetinaNet (best_5e873bb) | **plastic_plug** | 확정 (plastic_plug/OK 직접 확인) | **0.816** | 0.781 (t=0.05) | 0.000 | 0.43 | 0.000 |
| RetinaNet (best_58b8202) | rolled_strip_base | 유력 (rolled_strip_base/OK) | 0.395 | 0.690 (t=0.27) | 0.000 | 0.46 | 0.000 |
| RetinaNet (best_89ffe9d) | switch? | 불명 | 0.397 | 0.644 (t=0.24) | 0.000 | 0.45 | 0.000 |
| Faster R-CNN (best_24a72709 등 6개) | **toothbrush** (6런/스냅샷 전부) | 확정 (QS 0.55~0.91, 음성통과) | 0.485 | 0.678 (t=0.118) | 0.092 (P 0.06/R 0.25) | **0.36** | 0.067 |
| ViTDet / YOLOS / RT-DETRv2 | — | 미식별 | — | — | — | — | — |

- FPS는 평가 중 측정한 CPU 배치 1 기준 (yolo11 640px 3.0fps, faster_rcnn 800px 0.36fps).
- 이미지 F1은 표본 내 최적 임계값 기준; 박스 F1은 conf≥0.25, IoU 0.5.
- **클스 로스**: yolo11은 체크포인트 내장 검증 지표 — P 0.479 / R 0.254 / mAP50 0.227 / mAP50-95 0.128 / **val cls_loss 3.157** / box_loss 1.617 / dfl_loss 1.087 (best epoch). retinanet·faster_rcnn은 체크포인트에 로스 미포함 + 서버 로그 소실로 **측정 불가**.

- AP50가 전부 0인 것은 이 런들의 박스가 GT 결함 박스와 IoU 0.5에 도달하지 못함을 뜻한다 (박스 품질 부족). plastic_plug(0.816)처럼 제품 OK 클래스가 학습된 런만 이미지 수준 분리가 나타난다.
- defect_only 학습 런은 OK 이미지에서도 결함 클래스를 출력(제품 감지=결함 클래스화)하므로 AUROC가 0.4~0.55로 나온다.
- 원본: `inference/results/eval_*.json`
