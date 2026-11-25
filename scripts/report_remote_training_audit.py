"""이미 수집한 원격/로컬 증거로 모델별 총합 Markdown 보고서를 생성한다.

학습·평가를 재실행하거나 부족한 수치를 만들어 채우지 않는다. 카테고리 macro와 전체 AUROC를 구분한다.
"""
from pathlib import Path
import argparse,csv,json,math,os,statistics
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[1]
MODELS={'patchcore':'PatchCore','efficientad_s':'EfficientAD-S','uniad':'UniAD','hvq_trans':'HVQ-Trans',
 'dinomaly':'Dinomaly','inp_former':'INP-Former','faster_rcnn':'Faster R-CNN','retinanet':'RetinaNet',
 'yolo11':'YOLO11','rtdetrv2':'RT-DETRv2','yolos':'YOLOS','vitdet':'ViTDet'}
ANOMALY=set(list(MODELS)[:6])


def load(path):return json.loads(Path(path).read_text())
def number(x):return f'{x:.6f}' if isinstance(x,(int,float)) and math.isfinite(x) else 'N/A'
def mean(values):
 values=[x for x in values if isinstance(x,(int,float)) and math.isfinite(x)]
 return statistics.mean(values) if values else None


def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--evidence',type=Path,default=ROOT/'outputs/remote_training_audit_20261119_v1');p.add_argument('--output',type=Path,default=ROOT/'reports/remote_training_20261119_v1');args=p.parse_args()
 source=args.evidence.resolve();out=args.output.resolve();out.mkdir(parents=True,exist_ok=False);fig=out/'figures';fig.mkdir()
 snapshot=load(source/'remote_snapshot.json');final=load(source/'remote_final.json');bundle=load(source/'report_inputs.json');backup=load(source/'local_backup_audit.json');containers=load(source/'checkpoint_container_validation.json')
 hashes=load(source/'checkpoint_sha256_validation.json') if (source/'checkpoint_sha256_validation.json').exists() else None
 stamp=final['time_utc'];records={key:{} for key in MODELS};backuproot=ROOT/'real-iad-backup'
 def link(path):return os.path.relpath(Path(path),out).replace(os.sep,'/')
 def key_for(run):
  cfg=run.get('config.json',{});k=cfg.get('backend_settings',{}).get('model_key')
  if k in MODELS:return k
  for key,name in MODELS.items():
   if cfg.get('model_name')==name:return key
  for key in MODELS:
   if '/'+key+'/' in run['run_dir']:return key
  return None
 def category(run):return Path(run['run_dir']).parts[-3]
 def compact_row(key,cat,metrics,origin):
  val=metrics.get('validation',{});test=metrics.get('test',{});image=test.get('image',{});pixel=test.get('pixel',{})
  return dict(model=key,category=cat,validation_image_auroc=val.get('image',{}).get('auroc'),test_image_auroc=image.get('auroc'),
   test_image_ap=image.get('ap'),test_image_f1=image.get('f1'),test_pixel_auroc=pixel.get('auroc'),test_pixel_ap=pixel.get('ap'),
   test_aupro=test.get('aupro',{}).get('value'),test_images=image.get('n'),test_pixel_images=test.get('pixel_images'),source=origin)
 # 완료 export의 카테고리별 수치가 기본이며 원격의 실제 선택된 평가 Run이 있으면 근거를 더한다.
 for key,folder in [('patchcore','patchcore_array_hotfix_20261117'),('efficientad_s','efficientad_s_recovery_20261117')]:
  for path in (backuproot/'export'/folder).glob('*/metrics.json'):
   records[key][path.parent.name]=dict(metrics=load(path),source=path,config=None,run=None)
 for path in (backuproot/'export/remaining_models_recovery_20261117/inp_former').glob('*/metrics.json'):
  records['inp_former'][path.parent.name]=dict(metrics=load(path),source=path,config=None,run=None)
 for run in bundle['runs']:
  key=key_for(run);metrics=run.get('metrics.json',{})
  if key in ANOMALY and 'test' in metrics:
   cat=category(run)
   if cat in records[key]:records[key][cat]['config']=run.get('config.json');records[key][cat]['run']=run
   elif metrics['test'].get('data_kind')=='REAL':records[key][cat]=dict(metrics=metrics,source=source/'report_inputs.json',config=run.get('config.json'),run=run)
 perf=[];views=[]
 for key,categories in records.items():
  for cat,entry in categories.items():
   perf.append(compact_row(key,cat,entry['metrics'],str(entry['source'])))
   for view,value in entry['metrics'].get('test',{}).get('by_view',{}).items():
    views.append(dict(model=key,category=cat,view=view,n=value.get('n'),image_auroc=value.get('auroc'),f1=value.get('f1')))
 def write_csv(name,rows,fields=None):
  with (out/name).open('x',newline='') as stream:
   writer=csv.DictWriter(stream,fieldnames=fields or list(rows[0]));writer.writeheader();writer.writerows(rows)
 write_csv('MODEL_METRICS.csv',perf);write_csv('VIEW_METRICS.csv',views)
 cp=backup['remote_latest_checkpoints'];cpfields=['remote_checkpoint','completed_epochs','global_step','bytes','remote_exists','local_size_matches','sha256']
 write_csv('CHECKPOINT_SYNC_STATUS.csv',[{k:r[k] for k in cpfields} for r in cp])
 write_csv('LOCAL_CHECKPOINT_CONTAINER_STATUS.csv',[dict(path=r['path'],bytes=r['bytes'],container_valid=r['zip_structure_valid'],error=r.get('error','')) for r in containers])
 import matplotlib
 matplotlib.use('Agg')
 import matplotlib.pyplot as plt
 for key in ['patchcore','efficientad_s','inp_former']:
  rows=[r for r in perf if r['model']==key and r['test_image_auroc'] is not None]
  if not rows:continue
  rows.sort(key=lambda r:r['category']);figure,axis=plt.subplots(figsize=(14,5))
  axis.bar([r['category'] for r in rows],[r['test_image_auroc'] for r in rows],color='#3073a8')
  axis.set_ylim(0,1.05);axis.set_ylabel('Image AUROC (unitless)');axis.tick_params(axis='x',labelrotation=75)
  axis.set_title(f'{MODELS[key]} | available category test results | categories={len(rows)}, images={sum(r["test_images"] or 0 for r in rows)}')
  figure.tight_layout();figure.savefig(fig/f'{key}_category_auroc.png',dpi=150);plt.close(figure)
 figure,axis=plt.subplots(figsize=(8,4));axis.bar(['export','offload'],[sum(p.stat().st_size for p in (backuproot/d).rglob('*') if p.is_file())/2**30 for d in ['export','offload']],color=['#2a7c99','#cc9549']);axis.set_ylabel('Stored size (GiB, includes duplicates)');axis.set_title('Local received artifacts | inventory '+stamp);figure.tight_layout();figure.savefig(fig/'backup_storage.png',dpi=150);plt.close(figure)
 # 실행 상태는 오래된 parent state 하나가 아닌 활성 프로세스/학습 이력/완료 영수증을 함께 사용한다.
 status={
 'patchcore':('FIT_EVALUATION_COMPLETED','30/30 품목 메모리뱅크 fit·평가 완료. Gradient 기반 50 epoch 모델이 아님.','새 학습보다 메모리뱅크·설정·평가 결과 묶음 보존 및 재현 추론을 우선한다.'),
 'efficientad_s':('EVALUATION_AVAILABLE_WITH_RECOVERY','30/30 품목 평가 있음. 20건 EVALUATION_COMPLETED, 10건 EVALUATION_RECOVERED. 모든 품목 50 epoch 완료를 뜻하지 않음.','회복 평가 10품목과 PCB처럼 짧은 회복 학습을 별도 표시하고 calibration 붕괴 원인을 해결한 뒤 필요한 품목만 새 실험/안전한 checkpoint에서 이어간다.'),
 'uniad':('TRAINED_50_EPOCH_EVALUATION_PAUSED','50 epoch /95,650 step 체크포인트 존재. EVAL_PAUSED 마커로 평가 중지.','재학습보다 저장된 가중치의 스트리밍 Validation/Test 평가를 먼저 복구한다. NPY 전체 누적으로 디스크가 다시 차지 않도록 한다.'),
 'hvq_trans':('TRAINING_OR_END_OF_TRAINING_RETRY','최근 50/50 로그. 이전 exit -11과 watchdog 재시작 반복 이력, 완료 평가 미확인.','50 epoch 종료 지점의 signal11/저장/평가 전환을 진단하고 가장 최근 유효 checkpoint로 평가부터 검증한다. 50 epoch 전체 반복을 자동 성공으로 세지 않는다.'),
 'dinomaly':('COMPLETION_RECEIPT_ARTIFACTS_INCOMPLETE','완료 영수증 47,850 step과 로컬 best 가중치는 있으나 영수증이 가리키는 원격 보고서/가중치 경로가 없어짐. 평가 수치 원본도 이번 조사에서 확보 못함.','로컬 가중치와 정확한 설정을 먼저 묶고 평가·보고서를 재생성한다. 원본 경로 부재를 학습 실패나 모델 손상으로 단정하지 않는다.'),
 'inp_former':('CATEGORY_TRAINING_IN_PROGRESS','확인 시점 완료 영수증 12/30 품목. toy_brick·porcelain_doll 학습 중.','현재 두 worker를 유지하고 남은 18품목(진행 중2 포함)을 이어간다. 완료 품목을 재학습하지 않고 각 best/설정/평가를 즉시 백업한다.'),
 'faster_rcnn':('V2_TRAINING','v2 약 3번째 epoch /50, 최근 Loss0.0919. 디스크 부족으로 이전 attempt가 중단된 이력이 있음.','현재 v2 학습을 이어가고 새 체크포인트와 best를 안전하게 수신한다. 이전 v1 class-error 결과를 현재 결과와 섞지 않는다.'),
 'retinanet':('V2_TRAINING','v2 첫 epoch /50, 최근 Loss0.9505·gradient norm1.77. 재시도 학습 중.','현재 lr0.0025 설정을 유지한 채 Validation 추이를 관찰하고 원래 발산한 lr0.01 실험과 분리한다. 단기 유한 Loss를 최종 성능으로 해석하지 않는다.'),
 'yolo11':('V2_TRAINING','v2 8~9번째 epoch /50. v1 50 epoch 결과는 class-error superseded로 별도 보존.','현재 v2 50 epoch를 이어가고 Validation으로 best를 고른다. v1 완료 수치를 최신 모델 최종 성능으로 보고하지 않는다.'),
 'rtdetrv2':('V2_PENDING_OLD_RUN_INTERRUPTED','과거 v1 약7번째 epoch에서 중단. 현재 활성 worker 미확인, v2 runner 대기 목록.','현재 실행 모델들의 GPU/메모리 여유가 생기면 고정된 v2 클래스/데이터 계약으로 새 실험을 시작한다. v1 가중치의 다른 head를 무조건 이어받지 않는다.'),
 'yolos':('V2_PENDING_OLD_RUN_INTERRUPTED','과거 v1 약11번째 epoch에서 중단. 현재 활성 worker 미확인, v2 runner 대기 목록.','현재 v2 대기 순서대로 시작한다. class head가 바뀌는 초기화/재개 조건을 기록하고 v1 결과와 분리한다.'),
 'vitdet':('V2_PENDING_OLD_RUN_INTERRUPTED','과거 v1 약7번째 epoch에서 중단. 현재 활성 worker 미확인, v2 runner 대기 목록.','GPU 여유와 공식 입력 제약을 확인한 뒤 v2 실행을 시작한다. 먼저 256 입력 설정이 공식 baseline과 다른 조건임을 기록한다.')}
 summary=[]
 for key,name in MODELS.items():
  modelrows=[r for r in perf if r['model']==key];aggregate={metric:mean([r[metric] for r in modelrows]) for metric in ['test_image_auroc','test_image_ap','test_image_f1','test_pixel_auroc','test_pixel_ap','test_aupro']}
  summary.append(dict(model=name,status=status[key][0],categories_with_metrics=len(modelrows),test_images=sum(r['test_images'] or 0 for r in modelrows),**aggregate))
  lines=[f'# {name} 모델별 종합 보고서',f'\n확인 시점: {stamp} (UTC). 원격 학습 상태는 이후 계속 변한다. 이 보고서가 학습이나 Test 평가를 새로 실행한 것은 아니다.',
   '\n## 현재 상태',f'\n**{status[key][0]}** — {status[key][1]}', '\n## 학습·데이터 조건',
   '\n원격 주 실험 코호트는 30,000장 /6,000 선언 제품 /30품목이며 Train21,045·Validation4,400·Test4,555이다. 전체151,050장 전수 학습 결과가 아니다. v1/v2는 같은 코호트 경로를 사용해도 Crop/클래스 계약이 다를 수 있다.']
  configs=[r.get('config.json',{}) for r in bundle['runs'] if key_for(r)==key and r.get('config.json')]
  if configs:
   fields=['official_repo','official_commit','manifest_sha256','split_version','crop_policy_version','epochs','batch_size','optimizer','learning_rate','input_resolution']
   lines+=['\n|설정|관측된 값(복수 Run 포함)|','|---|---|']
   for field in fields:
    values=sorted(set(json.dumps(c[field],ensure_ascii=False) for c in configs if field in c));lines.append(f'|{field}|'+('; '.join(values)[:900] if values else 'UNVERIFIED')+'|')
  else:lines+=['\n정확한 Run 설정 일부는 미확보다. 기존 체크포인트의 파일명만으로 학습 epoch나 공식 입력 설정을 추측하지 않는다.']
  if key not in ANOMALY:
   lines+=['\n현재 v2 입력256·batch4·계획50 epoch이며 141개 품목×결함/품목별 OK 객체 클래스를 사용한다. 원본 전체 이미지를 모델 내부 Resize/LetterBox로 입력한다. `annotation_policy=defect_only`라는 설정 문자열과 달리 클래스/Target에 OK 제품 박스가 포함되어 있어 기존 공통8결함 D1 기준선과 동일한 실험이 아니다. 제품 객체와 결함 객체의 성능을 구분해 평가해야 한다.']
  lines+=['\n## 확보된 평가 수치']
  if modelrows:
   lines+=['\n아래는 **확보된 품목들의 category macro 평균**이다. 모든 이미지 점수를 합쳐 다시 계산한 pooled AUROC가 아니며, 서로 다른 데이터/전처리 Run 간 성능 순위를 뜻하지 않는다.',
    '\n|품목 수|Test 이미지 합|Image AUROC macro|Image AP macro|Image F1 macro|Pixel AUROC macro|AUPRO macro|','|---:|---:|---:|---:|---:|---:|---:|',
    f'|{len(modelrows)}|{sum(r["test_images"] or 0 for r in modelrows)}|{number(aggregate["test_image_auroc"])}|{number(aggregate["test_image_ap"])}|{number(aggregate["test_image_f1"])}|{number(aggregate["test_pixel_auroc"])}|{number(aggregate["test_aupro"])}|',
    '\n|품목|Val AUROC|Test AUROC|Test AP|Test F1|Pixel AUROC|AUPRO|Test n|','|---|---:|---:|---:|---:|---:|---:|---:|']
   for row in sorted(modelrows,key=lambda r:r['category']):lines.append('|'+row['category']+'|'+ '|'.join(number(row[k]) for k in ['validation_image_auroc','test_image_auroc','test_image_ap','test_image_f1','test_pixel_auroc','test_aupro','test_images'])+'|')
   if (fig/f'{key}_category_auroc.png').exists():lines+=[f'\n![category AUROC](figures/{key}_category_auroc.png)', '\n해석: 품목별 편차가 있으며 높은 평균만으로 취약 품목의 안정성이 보장되지 않는다. 표본 수와 회복 평가 여부를 함께 확인한다.']
  else:lines+=['\n**N/A — 현재 계약에 맞는 최종 평가 원본을 확보하지 못했다.** 진행 중/중단/영수증만 있는 모델에 성능0이나 성공 판정을 채우지 않는다. 이전 class-error 탐지 수치는 현재 모델 성능에서 제외한다.']
  lines+=['\n## 체크포인트 및 로컬 수신', '\n[전체 체크포인트 대조 CSV](CHECKPOINT_SYNC_STATUS.csv), [로컬 컨테이너 검사](LOCAL_CHECKPOINT_CONTAINER_STATUS.csv)를 참고한다. ZIP 구조 검사는 tensor 값의 유한성이나 full CRC 검사를 뜻하지 않는다. SHA 검증 파일 수는 전체 점검 보고서에 별도 기록한다.']
  relevant=[x for x in cp if '/'+key+'/' in x['remote_checkpoint'] or key in x['remote_checkpoint'].split('/')[-5:]]
  if relevant:
   lines+=['\n|원격 파일|완료 epoch|step|원격 존재|로컬 동일 이름/크기|','|---|---:|---:|---|---|']
   for r in relevant[:35]:lines.append(f'|`{r["remote_checkpoint"]}`|{r["completed_epochs"]}|{r["global_step"]}|{r["remote_exists"]}|{r["local_size_matches"]}|')
  else:lines+=['\n전용 체크포인트 참조를 이번 snapshot에서 확보하지 못했거나 이미 offload되어 원본 참조가 남아 있지 않다. 해당 상태를 가중치 부재로 단정하지 않는다.']
  demo=source/'inference_preview'/f'{key}_cpu_v1'
  lines+=['\n## 실제 추론 시연']
  if (demo/'summary.json').exists():
   examples=load(demo/'summary.json');lines+=['\n학습 중 checkpoint 또는 완료 best로 Validation2장 CPU 추론했다. 2장 시연은 mAP/AUROC 성능 검증이 아니다. 표시 confidence0.25는 최종 평가 threshold가 아니다.']
   for row in examples:
    lines+=[f'\n### {row["image_id"]}',f'\n원본 상태 **{row["source_status"]}**, 예측 **{row["image_status"]}**, CPU model-call {row["latency_seconds"]:.3f}s.']
    if 'anomaly_score' in row:lines+=[f'이상 점수 {row["anomaly_score"]:.6f}, Validation image threshold {row["validation_image_threshold"]}.']
    if row['source_status']=='NG' and row['image_status']=='OK_CANDIDATE':lines+=['불량 표본에서 정상 객체만 탐지했다. 현재 시연에서는 미검출/오판 사례이며 정상으로 확정하면 안 된다.']
    if row['source_status']=='OK' and row['image_status']=='NG':lines+=['정상 표본을 NG로 판정한 False Positive 사례다.']
    if row['image_status']=='NO_DETECTION_UNCERTAIN':lines+=['표시 threshold 이상 검출이 없어 불확실 상태로 표시했다. 정상으로 재분류하지 않았다.']
    lines+=[f'\n![actual prediction]({link(demo/row["figure"])})']
  else:lines+=['\nNOT_EXECUTED — 이 모델의 실제 추론 예시는 이번 작업에서 실행하지 않았다. 공통 CLI의 모델 이름 지원과 실제 런타임 검증은 다르다.']
  lines+=['\n## 다음 학습·평가 작업', '\n'+status[key][2], '\n## 근거 및 한계',
   f'\n- [원격 초기 snapshot]({link(source/"remote_snapshot.json")}) / [원격 후속 점검]({link(source/"remote_final.json")}) / [설정·평가 수집]({link(source/"report_inputs.json")})',
   f'- [품목별 수치 CSV](MODEL_METRICS.csv) / [시점별 원본 집계](VIEW_METRICS.csv)',
   '- 기존 체크포인트/학습/원본/승인 기록은 변경하지 않았다. GPU benchmark와 전체 재평가는 NOT_EXECUTED다.']
  (out/f'{key.upper()}_REPORT.md').write_text('\n'.join(lines))
 write_csv('MODEL_SUMMARY.csv',summary)
 main=['# Real-IAD 원격 학습·백업·모델별 종합 보고서',f'\n점검 기준: {stamp} UTC. Git 동기화가 아닌 SSH/rsync와 실제 파일/로그를 점검했다.',
 '\n## 핵심 판정','\n원격 GPU 학습은 진행 중이지만 **로컬 백업이 최신 학습 상태를 모두 포함하지 않는다.** 점검 시 A6000 GPU100%, 약19.9GiB 사용. 기존 수신 데이터는160,920,352,373bytes(약149.87GiB), PT416개다. 점검 시 pull_loop/rsync 프로세스가 없었고 마지막 수신 흔적은16:48경이다.',
 '\n- 활성 모델5개 최신 체크포인트(Toy brick/Porcelain doll INP, v2 Faster R-CNN/RetinaNet/YOLO11)는 snapshot 기준 로컬에 동일 파일이 없었다.',
 '- pull 스크립트는 export와 offload 큐만 읽는다. 현재 job_v2/진행 중 checkpoint는 아직 그 경로로 export되지 않아 큐가0이어도 최신 백업 완료가 아니다.',
 '- PT416개 중413개는 ZIP 구조 정상,3개 파일(서로 다른 가중치2종)은 잘리거나 손상되어 구조 검사를 통과하지 못했다. 파일은 삭제하지 않았다.',
 '- 동일 이름/크기 중복 후보197개, 추가 저장 약67.77GiB. 중복 전량 해시 검증/삭제는 하지 않았다.',
 '- rsync 임시 파일4개 약2.18GiB도 남아 있어 전송 중단 이력이 있다. 현재 transfer가 실행 중이라는 뜻은 아니다.',
 '- 기존 pull_realiad.sh는 서버 파일 삭제 기능이 있고, 큐 전송은 rsync 실패를 무시한 뒤 로컬 존재만으로 서버 삭제를 결정한다. 이 점검에서 해당 스크립트는 실행하지 않았다.',
 '\n![storage](figures/backup_storage.png)', '\n## 모델별 상태', '\n|모델|현재 상태|후속 작업|','|---|---|---|']
 for key,name in MODELS.items():main.append(f'|[{name}]({key.upper()}_REPORT.md)|{status[key][0]}|{status[key][2]}|')
 main+=['\n## 데이터·비교 조건 주의','\n현재 원격은30,000장 코호트다. 탐지 v2는111개 품목×결함 +30개 품목별 OK=141클래스이며 OK에 제품 영역 박스가 있다. 기존8결함-only D1와 동일하지 않다. 원격 source.json은30,000장 중 실제 축소 Crop713장/원본 유지29,287장이라고 기록한다. 로컬에서 진행한 새로운 전수 Crop 결과가 현재 학습에 자동 반영된 것은 아니다.',
 '\n## 확인된 로컬 손상 파일', '\n|파일|크기|판정|','|---|---:|---|']
 for r in containers:
  if not r['zip_structure_valid']:main.append(f'|`{r["path"]}`|{r["bytes"]:,}|PK 헤더는 있으나 종료 구조 부재/잘린 ZIP. 재개 사용 금지, 유효한 다른 best/원격 보존본 대조 필요|')
 main+=['\n## 체크섬 점검 범위']
 if hashes:main+=[f'\n참조/manifest 기반 SHA256 확인 {hashes["checks"]}건, 고유 파일{hashes["unique_files"]}개, 불일치{len(hashes["mismatches"])}건. 이는 전체416개 가중치 전수 tensor 검증이 아니다.']
 else:main+=['\n전체 참조 SHA 검사는 별도 진행 중이며 결과를 확보하기 전 성공으로 표시하지 않는다. 대표2개 해시 일치만 먼저 확인했다.']
 main+=['\n## 추론 코드·실행 결과','\n[scripts/inference/run_checkpoint.py](../../scripts/inference/run_checkpoint.py)를 구현했다. 실제 실행은EfficientAD-S/RetinaNet/YOLO11/Faster R-CNN 각2장, 총8장이다. 나머지8모델의 실제 추론 통합은 UNVERIFIED/NOT_EXECUTED다. 일부 모델은 native memory bank/checkpoint 계약이 달라 추가 검증이 필요하다.',
 '\n시연에서 YOLO11은 NG/OK 각1장에 해당 객체를 예측했고, Faster R-CNN은NG에도 정상 객체만 예측했으며, RetinaNet은 표시 threshold 이상 검출이 없었다. EfficientAD는 정상1장을NG로 판정했다. 이것은 각2장 시연이며 전체 모델 순위나 최종 성능이 아니다.',
 '\n## 남은 작업 순서', '\n1. 최신 closed checkpoint와 request/config/class mapping을 삭제 없는 동기화로 먼저 보존한다. 학습 중 파일을 임의 삭제하거나 덮어쓰지 않는다.',
 '2. 현재 실행 중 v2 탐지3개와 INP2 worker를 유지하고 추가 모델의 동시 실행을 늘리지 않는다. GPU가 이미 포화다.',
 '3. HVQ 종료 signal11와 UniAD 평가·디스크 문제를 복구하여 기존 가중치를 재사용한다.',
 '4. Dinomaly의 누락 평가 자료를 복구하거나 저장된 checkpoint로 다시 평가해 보고서를 완성한다.',
 '5. v2 데이터·클래스 정책을 확인한 뒤 RT-DETRv2/YOLOS/ViTDet 대기 실행을 진행한다.',
 '6. 모든 모델의 동일 Manifest/평가 계약과 같은 하드웨어 benchmark를 맞춘 후 최종 비교한다.',
 f'\n세부 증거: [로컬 점검]({link(source/"local_backup_audit.json")}), [ZIP 구조 검사]({link(source/"checkpoint_container_validation.json")}), [수집 설정]({link(source/"remote_targeted.json")}).']
 (out/'ALL_MODELS_TRAINING_REPORT.md').write_text('\n'.join(main))
 (out/'NEXT_TRAINING_PLAN.md').write_text('# 다음 학습·평가 순서\n\n현재 실행 중인 학습은 이 작업에서 중단하거나 재시작하지 않았다.\n\n'+'\n'.join(f'## {MODELS[k]}\n\n현재: {status[k][1]}\n\n다음: {status[k][2]}\n' for k in MODELS))
 (out/'validation.json').write_text(json.dumps(dict(model_reports=12,metric_rows=len(perf),view_metric_rows=len(views),evidence_snapshot=stamp,
  new_training_executed=False,gpu_benchmark=False,existing_backups_modified=False,model_inference_actual=['efficientad_s','retinanet','yolo11','faster_rcnn']),indent=2))
 print(out,'model reports',12,'category metrics',len(perf),flush=True)


if __name__=='__main__':main()
