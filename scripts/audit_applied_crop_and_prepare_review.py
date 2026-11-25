"""전수 자동 적용 CSV를 사후 감사하고 손실/이미지 위험을 별도 사람 검수 큐로 만든다.

GT/마스크는 감사 단계에서만 읽으며 적용 좌표를 고치지 않는다. 기존 원장에 새 승인도 쓰지 않는다.
"""
from pathlib import Path
import argparse,csv,hashlib,json,os,sys,time,fcntl
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import cv2
ROOT=Path(__file__).resolve().parents[1]


def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def queue_record(row,reason,priority,manifest_sha,gt):
 """기존 CropReviewStore가 그대로 읽는 큐 계약. 수정/승인 원장은 새 디렉터리로 분리한다."""
 crop=[int(row['crop_'+k]) for k in ['x0','y0','x1','y1']]
 return dict(case_id=row['image_id'],image_id=row['image_id'],image_path=row['source_relative_path'],
  original_path=row['original_path'],product_id=row['product_id'],category=row['category'],view=row['view'],split=row['split'],
  status='CROP_REVIEW_REQUIRED',review_priority=priority,review_reasons=';'.join(reason),
  current_policy=row['selected_policy'],current_crop=json.dumps(crop),proposal_bbox=json.dumps(crop),
  proposal_method='APPLIED_IMAGE_GATE_PENDING_HUMAN_REVIEW',reference_product_bbox=json.dumps(gt) if gt else '',
  evaluation_mask_path=row['mask_path'],mask_available=bool(row['mask_path']),source_fingerprint=row['source_fingerprint'],
  base_policy_version=row['policy_version'],base_manifest_sha256=manifest_sha)


def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--directory',type=Path,required=True)
 p.add_argument('--data-root',type=Path,default=ROOT/'dataset');p.add_argument('--resume',action='store_true')
 p.add_argument('--features-complete',action='store_true',help='전수 계산이 끝난 후 남은 미계산/오류도 수동 검수에 포함')
 args=p.parse_args();out=args.directory.resolve();source=out/'preprocessing_metadata_final.csv';manifest_sha=sha(source)
 lock=(out/'audit.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 receipt=out/'post_crop_audit_validation.json'
 if receipt.exists():
  old=json.loads(receipt.read_text())
  if not args.resume:raise FileExistsError('Completed audit exists; use --resume to verify')
  if old['manifest_sha256']!=manifest_sha or sha(old['applied_csv'])!=old['applied_csv_sha256']:raise ValueError('Completed audit bindings changed')
  print(json.dumps(old),flush=True);return
 checkpoint=out/'audit_checkpoints';checkpoint.mkdir(exist_ok=True)
 gt={}
 for line in (ROOT/'outputs/object_aware_crop_v1/review/human_approved_gt.jsonl').read_text().splitlines():
  e=json.loads(line)
  if e['status']=='VERIFIED_GT':gt[e['image_path']]=e['bbox']
 boxmap={}
 with (ROOT/'outputs/team_data_release_v2/MV_TEAM_DATA_RELEASE_v2/annotations/defect_boxes.csv').open() as stream:
  for row in csv.DictReader(stream):boxmap.setdefault(row['image_id'],[]).append([float(row[k]) for k in ['x0','y0','x1','y1']])
 cv2.setNumThreads(1)
 def audit(row):
  crop=[int(row['crop_'+k]) for k in ['x0','y0','x1','y1']];x0,y0,x1,y1=crop
  width,height=int(row['original_width']),int(row['original_height']);full=crop==[0,0,width,height]
  reasons=[];reference=gt.get(row['source_relative_path']);contained=None
  if reference:
   a,b,c,d=reference;contained=x0<=a and y0<=b and x1>=c and y1>=d
   if not contained:reasons.append('OBSERVED_PRODUCT_GT_BBOX_LOSS')
  total=kept=None;mask_state='MISSING';error=''
  if row['mask_path']:
   if full:
    # 기존 제공 마스크의 검증된 총 픽셀 수를 identity Crop에서만 재사용한다.
    total=int(float(row['original_positive_pixels']));kept=total;mask_state='PRESENT_POSITIVE' if total else 'PRESENT_EMPTY'
   else:
    mask=cv2.imread(str(args.data_root/row['mask_path']),cv2.IMREAD_UNCHANGED)
    if mask is None or mask.shape!=(height,width):
     error='MASK_DECODE_OR_SIZE_ERROR';mask_state='INVALID';reasons.append(error)
    else:
     total=int((mask>0).sum());kept=int((mask[y0:y1,x0:x1]>0).sum());mask_state='PRESENT_POSITIVE' if total else 'PRESENT_EMPTY'
     if kept<total:reasons.append('OBSERVED_DEFECT_MASK_LOSS')
  clipped=removed=0
  for a,b,c,d in boxmap.get(row['image_id'],[]):
   clipped+=not(x0<=a and y0<=b and x1>=c and y1>=d)
   removed+=min(x1,c)<=max(x0,a) or min(y1,d)<=max(y0,b)
  if clipped:reasons.append('OBSERVED_DEFECT_BBOX_CLIP')
  if removed:reasons.append('OBSERVED_DEFECT_BBOX_REMOVAL')
  if row['crop_review_status'] in ['PENDING','REJECTED']:reasons.append('PREVIOUS_MANUAL_'+row['crop_review_status'])
  if args.features_complete and row['crop_review_status']!='APPROVED_CROP' and row['automatic_feature_status'] in ['NOT_COMPUTED','COMPUTE_ERROR']:
   reasons.append('AUTOMATIC_FEATURE_COMPUTE_ERROR_OR_MISSING')
  acknowledged=(row['crop_review_status']=='APPROVED_CROP' and str(row.get('human_observed_loss_acknowledged','')).lower()=='true')
  product_ack=str(row.get('human_product_bbox_loss_acknowledged','')).lower()=='true'
  mask_ack=str(row.get('human_defect_mask_loss_acknowledged','')).lower()=='true'
  # 이미 같은 좌표에서 사람이 관측 손실을 명시적으로 확인한 경우 수치에는 남기되 같은 검수를 반복 요청하지 않는다.
  needs_review=bool(reasons) and not (acknowledged and all(
   product_ack if reason=='OBSERVED_PRODUCT_GT_BBOX_LOSS' else mask_ack if reason.startswith('OBSERVED_DEFECT_') else False
   for reason in reasons))
  result=dict(image_id=row['image_id'],image_path=row['source_relative_path'],selected_policy=row['selected_policy'],
   mask_status=mask_state,original_pixels=total,kept_pixels=kept,pixel_retention=kept/total if total else None,
   product_gt_available=reference is not None,product_bbox_contained=contained,clipped_boxes=int(clipped),removed_boxes=int(removed),
   confirmed_mask_loss=total is not None and kept is not None and kept<total,confirmed_product_loss=contained is False,
   requires_manual_review=needs_review,review_reasons=';'.join(reasons),error=error,
   human_observed_loss_acknowledged=acknowledged)
  result['automatic_features_pending']=row['automatic_feature_status']=='NOT_COMPUTED'
  recommended=(not full and row['crop_review_status']!='APPROVED_CROP' and row['auto_gate_status']=='REVIEW')
  required_queue=queue_record(row,reasons,0 if any(x.startswith('OBSERVED') for x in reasons) else 10,manifest_sha,reference) if needs_review else None
  recommended_queue=queue_record(row,['IMAGE_GATE_REVIEW_PRODUCT_CONTAINMENT_UNVERIFIED'],20,manifest_sha,reference) if recommended and not reasons else None
  return dict(audit=result,required=required_queue,recommended=recommended_queue)
 def parts():
  with source.open() as stream:
   chunk=[]
   for row in csv.DictReader(stream):
    chunk.append(row)
    if len(chunk)==500:yield chunk;chunk=[]
   if chunk:yield chunk
 for number,chunk in enumerate(parts()):
  dest=checkpoint/f'part_{number:05}.json'
  if dest.exists():
   if not args.resume:raise FileExistsError('Use --resume; preserve existing audit')
   existing=json.loads(dest.read_text())
   if existing['manifest_sha256']!=manifest_sha or existing['ids']!=[r['image_id'] for r in chunk]:raise ValueError('Audit resume input mismatch')
   continue
  results=[audit(row) for row in chunk]
  temp=dest.with_suffix('.tmp');temp.write_text(json.dumps(dict(manifest_sha256=manifest_sha,ids=[r['image_id'] for r in chunk],results=results),allow_nan=False));os.replace(temp,dest)
  print('audited',min((number+1)*500,151050),flush=True)
 fields=None;counts=dict(images=0,mask_loss_images=0,product_gt_loss_images=0,product_gt_images=0,required_review_images=0,recommended_review_images=0,positive_original_pixels=0,positive_kept_pixels=0,removed_boxes=0)
 # 중단된 내보내기 파일은 별도 폴더로 보존하고 완료 체크포인트에서 새로 출력한다.
 stale=[out/name for name in ['post_crop_loss_audit.csv','manual_review_required.csv','manual_review_recommended.csv','preprocessing_metadata_applied.csv'] if (out/name).exists()]
 if stale:
  if not args.resume:raise FileExistsError('Partial audit exports exist; use --resume')
  archive=out/('incomplete_audit_exports_'+str(time.time_ns()));archive.mkdir()
  for path in stale:path.rename(archive/path.name)
 handles={};writers={}
 def emit(name,row):
  if name not in writers:
   handles[name]=(out/name).open('x',newline='');writers[name]=csv.DictWriter(handles[name],fieldnames=list(row));writers[name].writeheader()
  writers[name].writerow(row)
 try:
  for part in sorted(checkpoint.glob('part_*.json')):
   for record in json.loads(part.read_text())['results']:
    row=record['audit'];emit('post_crop_loss_audit.csv',row);counts['images']+=1
    counts['mask_loss_images']+=row['confirmed_mask_loss'];counts['product_gt_loss_images']+=row['confirmed_product_loss'];counts['product_gt_images']+=row['product_gt_available']
    counts['positive_original_pixels']+=row['original_pixels'] or 0;counts['positive_kept_pixels']+=row['kept_pixels'] or 0;counts['removed_boxes']+=row['removed_boxes']
    for key,name in [('required','manual_review_required.csv'),('recommended','manual_review_recommended.csv')]:
     if record[key]:emit(name,record[key]);counts['required_review_images' if key=='required' else 'recommended_review_images']+=1
 finally:
  for h in handles.values():h.close()
 # 감사 결과를 최종 단일 CSV에도 연결한다. 적용 좌표는 그대로이며 이 파일이 전처리 진입점이다.
 applied=out/'preprocessing_metadata_applied.csv'
 with source.open() as src,(out/'post_crop_loss_audit.csv').open() as aud,applied.open('x',newline='') as dst:
  reader=csv.DictReader(src);auditor=csv.DictReader(aud);writer=None
  for row in reader:
   result=next(auditor)
   if row['image_id']!=result['image_id']:raise ValueError('Audit join image ID mismatch')
   row.update(manual_review_required=result['requires_manual_review'],manual_review_reasons=result['review_reasons'],
     observed_product_gt_loss=result['confirmed_product_loss'],observed_defect_mask_loss=result['confirmed_mask_loss'],
     product_gt_available=result['product_gt_available'],product_gt_fully_contained=result['product_bbox_contained'],
     crop_clipped_boxes=result['clipped_boxes'],crop_removed_boxes=result['removed_boxes'],
     cropped_positive_pixels=result['kept_pixels'],crop_mask_loss=result['confirmed_mask_loss'],
     crop_target_audit_status='POST_CROP_AUDITED' if not result['error'] else result['error'])
   if result['original_pixels'] and int(result['original_pixels'])>0 and result['kept_pixels'] and int(result['kept_pixels'])==0:
    row['crop_annotation_status']='INVALID_TARGET'
   elif not row['crop_annotation_status']:row['crop_annotation_status']=row['annotation_status']
   if writer is None:writer=csv.DictWriter(dst,fieldnames=list(row));writer.writeheader()
   writer.writerow(row)
  if next(auditor,None) is not None:raise ValueError('Extra audit rows')
 applied_sha=sha(applied)
 for name in ['manual_review_required.csv','manual_review_recommended.csv']:
  if name not in handles:continue
  path=out/name;temp=path.with_suffix('.tmp')
  with path.open() as src,temp.open('x',newline='') as dst:
   reader=csv.DictReader(src);writer=csv.DictWriter(dst,fieldnames=reader.fieldnames);writer.writeheader()
   for row in reader:row['base_manifest_sha256']=applied_sha;writer.writerow(row)
  os.replace(temp,path)
 counts.update(manifest_sha256=manifest_sha,coordinates_modified_by_audit=False,gt_masks_used_in_selection=False,
   applied_csv=str(applied),applied_csv_sha256=applied_sha,
   pixel_weighted_retention=counts['positive_kept_pixels']/counts['positive_original_pixels'] if counts['positive_original_pixels'] else None,
   output_sha256={name:sha(out/name) for name in handles})
 with (out/'post_crop_audit_validation.json').open('x') as stream:json.dump(counts,stream,indent=2)
 print(json.dumps(counts),flush=True)


if __name__=='__main__':main()
