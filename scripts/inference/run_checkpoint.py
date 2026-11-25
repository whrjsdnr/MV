"""저장된 학습 요청·체크포인트와 동일 Backend로 소량 추론한다. 학습/보정/다운로드 없음.

--code-root는 해당 가중치를 만든 고정 소스(snapshot)를 지정한다. 데이터/클래스 계약이 다르면
억지로 로드하지 않는다. 표시 threshold는 평가 threshold와 구분하며 Test에 맞춰 조정하지 않는다.
"""
from pathlib import Path
import argparse,hashlib,importlib,json,math,os,sys,time,traceback

MODULES={
 'efficientad_s':'models.anomaly.efficientad_s.backend','patchcore':'models.anomaly.patchcore.backend',
 'uniad':'models.anomaly.uniad.backend','hvq_trans':'models.anomaly.hvq_trans.backend',
 'dinomaly':'models.anomaly.dinomaly.backend','inp_former':'models.anomaly.inp_former.backend',
 'retinanet':'models.detection.retinanet.backend','faster_rcnn':'models.detection.faster_rcnn.backend',
 'yolo11':'models.detection.yolo11.backend','rtdetrv2':'models.detection.rtdetrv2.backend',
 'yolos':'models.detection.yolos.backend','vitdet':'models.detection.vitdet.backend'}


def sha(path):
 with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def selected_checkpoint(reference,checkpoint,expected_hash):
 """가변 latest 포인터를 먼저 고정된 참조로 해석하고 실제 가중치 SHA256을 확인한다."""
 metadata=None
 if reference:
  ref=Path(reference).resolve();metadata=json.loads(ref.read_text())
  if 'reference' in metadata:
   child=(ref.parent/metadata['reference']).resolve()
   if not child.is_relative_to(ref.parent):raise ValueError('Checkpoint reference escapes directory')
   if sha(child)!=metadata['reference_sha256']:raise ValueError('Reference SHA mismatch')
   ref=child;metadata=json.loads(ref.read_text())
  target=(ref.parent/metadata['checkpoint_path']).resolve()
  if not target.is_relative_to(ref.parent):raise ValueError('Checkpoint escapes reference directory')
  expected_hash=metadata['sha256']
 else:target=Path(checkpoint).resolve()
 if not expected_hash:raise ValueError('--checkpoint-sha256 is required for a direct weight file')
 if sha(target)!=expected_hash:raise ValueError('Checkpoint SHA256 mismatch')
 if metadata and target.stat().st_size!=metadata['bytes']:raise ValueError('Checkpoint byte count mismatch')
 return target,metadata,expected_hash


def status_from_detections(labels,scores,classes,threshold):
 """정상 클래스가 있는 현재141-class 실험과 결함 전용 실험을 구분한다."""
 names={value:key for key,value in classes.items()};selected=[]
 for label,score in zip(labels,scores):
  if label not in names:raise ValueError('Prediction class outside recorded mapping')
  if not math.isfinite(score) or not 0<=score<=1:raise ValueError('Invalid confidence')
  if score>=threshold:selected.append(names[label])
 defects=[name for name in selected if not name.endswith('/OK')]
 normal=[name for name in selected if name.endswith('/OK')]
 return dict(image_status='NG_CANDIDATE' if defects else 'OK_CANDIDATE' if normal else 'NO_DETECTION_UNCERTAIN',
             defect_objects=len(defects),normal_objects=len(normal),displayed_objects=len(selected))


def main(argv=None):
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--code-root',type=Path,required=True);p.add_argument('--request',type=Path,required=True)
 weights=p.add_mutually_exclusive_group(required=True);weights.add_argument('--checkpoint-reference',type=Path);weights.add_argument('--checkpoint',type=Path)
 p.add_argument('--checkpoint-sha256');p.add_argument('--output',type=Path,required=True)
 p.add_argument('--device',default='cpu');p.add_argument('--threads',type=int,default=1)
 p.add_argument('--split',choices=['validation','test'],default='validation');p.add_argument('--samples',type=int,default=2)
 p.add_argument('--category');p.add_argument('--image-id',action='append');p.add_argument('--image',type=Path)
 p.add_argument('--display-confidence',type=float,default=.25);p.add_argument('--metrics',type=Path)
 args=p.parse_args(argv)
 if args.samples<1 or args.threads<1 or not 0<=args.display_confidence<=1:p.error('Invalid samples/threads/confidence')
 sys.path.insert(0,str(args.code_root.resolve()));sys.dont_write_bytecode=True
 out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
 def save(name,data):
  with (out/name).open('x') as stream:json.dump(data,stream,ensure_ascii=False,indent=2,allow_nan=False)
 start=time.monotonic();result=dict(status='RUNNING',training_executed=False,threshold_recalibration=False,device=args.device,model_runtime_integration='UNVERIFIED_UNTIL_EXECUTED')
 try:
  import torch,numpy as np,cv2
  torch.set_num_threads(args.threads)
  request=json.loads(args.request.read_text());cfg=request['settings'];key=cfg['model_key'];family=cfg['model_family']
  if key not in MODULES:raise ValueError('Unsupported model key')
  if args.image and family!='detection':raise ValueError('Anomaly external images need approved crop metadata; use --image-id from manifest')
  weight,metadata,weight_sha=selected_checkpoint(args.checkpoint_reference,args.checkpoint,args.checkpoint_sha256)
  if metadata:
   for field in ['model_key','settings_sha256','data_sha256']:
    if metadata['bindings'].get(field)!=request.get(field):raise ValueError('Checkpoint/request binding mismatch: '+field)
  save('config.json',dict(model_key=key,request_path=str(args.request),request_sha256=sha(args.request),
   code_root=str(args.code_root.resolve()),checkpoint=str(weight),checkpoint_sha256=weight_sha,
   checkpoint_metadata=metadata,device=args.device,threads=args.threads,split=args.split,
   display_confidence=args.display_confidence,display_threshold_is_evaluation_threshold=False,
   metrics_source=str(args.metrics) if args.metrics else None))
  from models._shared.data import open_release,datasets
  module=importlib.import_module(MODULES[key]);payload=torch.load(weight,map_location='cpu',weights_only=True)
  thresholds={}
  if args.metrics:
   metrics=json.loads(args.metrics.read_text());thresholds=metrics.get('validation',{}).get('threshold_policy',{})
  with open_release(request) as release:
   classes=release.classes['yolo']
   if key=='yolo11':backend=module.TrainingValidationBackend(cfg,classes,args.device)
   else:backend=module.Backend(cfg,classes,args.device)
   if hasattr(backend.model,'load_state_dict'):
    state=payload.get('model',payload);backend.model.load_state_dict(state,strict=True)
   elif hasattr(backend,'restore_training_state') and 'backend_state' in payload:
    backend.restore_training_state(payload['backend_state'])
   else:raise ValueError('No verified checkpoint restoration interface for this Backend')
   if hasattr(backend.model,'eval'):backend.model.eval()
   del payload
   if args.image:
    raw=cv2.imread(str(args.image));
    if raw is None:raise ValueError('Cannot decode external image')
    h,w=raw.shape[:2];sample=dict(image=torch.from_numpy(cv2.cvtColor(raw,cv2.COLOR_BGR2RGB).copy()).permute(2,0,1).float()/255,
     image_id=sha(args.image)[:16],product_id='UNKNOWN',category='UNKNOWN',view='UNKNOWN',split='INFERENCE_ONLY',
     original_size=(h,w),crop_xyxy=(0,0,w,h),metadata={'image_policy':'original_full'},status='UNKNOWN',mask_status='MISSING')
    samples=[(sample,raw,str(args.image))]
   else:
    data=datasets(release,cfg,category=args.category);ds=data[args.split];frame=ds.data
    if args.image_id:
     selected=frame[frame.image_id.isin(args.image_id)]
     if len(selected)!=len(set(args.image_id)):raise ValueError('Image ID missing from selected split/category')
    else:
     # 시연 표본에 OK/NG를 포함한다. 라벨은 모델 입력이나 Crop 결정에 쓰지 않는다.
     ids=list(frame[frame.status.eq('OK')].head((args.samples+1)//2).image_id)+list(frame[frame.status.eq('NG')].head(args.samples//2).image_id)
     selected=frame[frame.image_id.isin(ids)].head(args.samples)
    samples=[]
    for index,row in selected.iterrows():
     sample=ds[int(index)];path=ds.index.source_path(row.to_dict());raw=cv2.imread(str(path))
     if raw is None:raise ValueError('Source decode failed')
     samples.append((sample,raw,str(path)))
   predictions=[];summaries=[];inverse={value:name for name,value in classes.items()}
   for index,(sample,raw,path) in enumerate(samples):
    timer=time.monotonic()
    with torch.inference_mode():
     # 새 외부 이미지는 학습 Target 없이 추론한다. NG를 빈 정상 Target으로 재분류하지 않는다.
     if args.image and key in ['retinanet','faster_rcnn']:
      pred=backend.model([sample['image'].to(args.device)])[0];keep=pred['labels']>0
      prediction=dict(image_id=sample['image_id'],split=sample['split'],coordinate_space='original',
       boxes=pred['boxes'][keep].cpu().tolist(),labels=(pred['labels'][keep]-1).cpu().tolist(),scores=pred['scores'][keep].cpu().tolist())
     else:prediction=backend.predict(sample)
    elapsed=time.monotonic()-timer;canvas=raw.copy();prediction=dict(prediction)
    entry=dict(image_id=sample['image_id'],category=sample['category'],view=sample['view'],
     source_status=sample['status'],source_path=path,latency_seconds=elapsed,
     checkpoint_sha256=weight_sha,coordinate_space='original',real_model_inference=True)
    if family=='detection':
     classification=status_from_detections(prediction['labels'],prediction['scores'],classes,args.display_confidence);entry.update(classification)
     for box,label,score in zip(prediction['boxes'],prediction['labels'],prediction['scores']):
      if score<args.display_confidence:continue
      x0,y0,x1,y1=map(int,box);cv2.rectangle(canvas,(x0,y0),(x1,y1),(0,200,0),2)
      cv2.putText(canvas,f'{inverse[label]} {score:.3f}',(max(0,x0),max(15,y0-5)),cv2.FONT_HERSHEY_SIMPLEX,.45,(0,200,0),1)
     entry['top_predictions']=sorted([dict(class_id=l,class_name=inverse[l],confidence=s,bbox_xyxy=b) for l,s,b in zip(prediction['labels'],prediction['scores'],prediction['boxes'])],key=lambda x:x['confidence'],reverse=True)[:10]
    else:
     values=np.asarray(prediction.pop('score_map'));observed=np.asarray(prediction.pop('observed',np.isfinite(values)),bool)
     if not np.isfinite(values[observed]).all():raise ValueError('Nonfinite anomaly map in observed region')
     score=float(prediction['score']);threshold=thresholds.get('image');entry.update(anomaly_score=score,
      validation_image_threshold=threshold,image_status=('NG' if score>=threshold else 'OK') if threshold is not None else 'THRESHOLD_NOT_AVAILABLE')
     np.save(out/f'{index:03d}_score_map.npy',values);np.save(out/f'{index:03d}_observed.npy',observed)
     lo,hi=np.percentile(values[observed],[1,99]);scaled=np.zeros_like(values,dtype=np.uint8)
     if hi>lo:scaled[observed]=(np.clip((values[observed]-lo)/(hi-lo),0,1)*255).astype(np.uint8)
     color=cv2.applyColorMap(scaled,cv2.COLORMAP_JET);blend=cv2.addWeighted(canvas,.55,color,.45,0);canvas[observed]=blend[observed]
     entry['heatmap_display_scaling']='PER_IMAGE_P01_P99_VISUALIZATION_ONLY'
     prediction['score_map_file']=f'{index:03d}_score_map.npy';prediction['observed_file']=f'{index:03d}_observed.npy'
    thumb=cv2.resize(canvas,(640,round(canvas.shape[0]*640/canvas.shape[1])))
    cv2.putText(thumb,f'{key} | {entry["image_status"]}',(8,20),cv2.FONT_HERSHEY_SIMPLEX,.55,(255,100,0),2)
    if not cv2.imwrite(str(out/f'{index:03d}_prediction.png'),thumb):raise ValueError('Cannot save prediction image')
    entry['figure']=f'{index:03d}_prediction.png';summaries.append(entry);predictions.append(prediction)
   save('predictions.json',predictions);save('summary.json',summaries)
   result.update(status='COMPLETED_INFERENCE_ONLY',samples=len(samples),model_key=key,
    model_runtime_integration='VERIFIED_ON_RECORDED_SAMPLES',checkpoint_sha256=weight_sha,
    total_seconds=time.monotonic()-start,gpu_benchmark_performed=False)
   (out/'report.md').write_text('# 실제 체크포인트 추론 시연\n\n학습 성능 평가가 아닌 소량 실제 추론이다. 표시 confidence와 평가 threshold는 구분한다.\n\n'+''.join(
    f'## {x["image_id"]}\n\n- 원본 상태: {x["source_status"]}\n- 예측: {x["image_status"]}\n- 추론 시간(CPU/GPU 지정 장치): {x["latency_seconds"]:.3f}s\n\n![prediction]({x["figure"]})\n\n' for x in summaries))
  save('validation.json',result)
 except BaseException as exc:
  result.update(status='FAILED',error=repr(exc),traceback=traceback.format_exc());save('validation.json',result);raise


if __name__=='__main__':main()
