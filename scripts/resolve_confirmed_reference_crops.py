"""사용자가 확인한 기존 제품 박스를 지정된 검수 큐 범위에서만 재사용한다.

실제 저장한 Crop 수정이 우선이다. 승인 원장에 가짜 승인이나 VERIFIED_GT를 추가하지 않는다.
"""
from pathlib import Path
import csv,json,sys,hashlib
from datetime import datetime,timezone
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from mv_analysis.crop_reconstruction import reconstruct_row
from mv_analysis.yolo_crop_geometry import square_crop
ROOT=Path(__file__).resolve().parents[1]


def sha(path):
 with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def main():
 root=ROOT/'outputs/adaptive_crop_applied_20261117_v1';preview=root/'preview_ready'
 queue=preview/'manual_review_required.csv';ledger=preview/'manual_crop_review_ledger.jsonl'
 source=preview/'preprocessing_metadata_applied.csv';gtledger=ROOT/'outputs/object_aware_crop_v1/review/human_approved_gt.jsonl'
 watched=[ledger,source,queue,gtledger];before={str(p):sha(p) for p in watched}
 latest={r['image_path']:r for r in map(json.loads,ledger.read_text().splitlines())}
 gt={r['image_path']:r for r in map(json.loads,gtledger.read_text().splitlines()) if r['status']=='VERIFIED_GT'}
 with queue.open() as stream:cases=list(csv.DictReader(stream))
 time=datetime.now(timezone.utc).isoformat();overrides={};manual=[]
 for row in cases:
  if latest.get(row['image_path'],{}).get('status')=='APPROVED_CROP':manual.append(row['image_path']);continue
  box=json.loads(row['reference_product_bbox'])
  if row['image_path'] not in gt or box!=gt[row['image_path']]['bbox']:raise ValueError('Reference is not the existing verified product box')
  overrides[row['image_path']]=dict(image_id=row['image_id'],image_path=row['image_path'],source_fingerprint=row['source_fingerprint'],
    product_bbox_xyxy=box,crop_xyxy=square_crop(box,.1),margin_each_side=.1,
    confirmed_utc=time,confirmation_source='USER_CONVERSATION_20261117_EXISTING_CYAN_REFERENCE_ACCEPTED',
    source_product_gt_ledger_sha256=sha(gtledger),source_product_gt_image_sha256=gt[row['image_path']]['source_sha256'])
 record=dict(scope='ONLY_REMAINING_IMAGES_OF_PREVIEW_REQUIRED_QUEUE',queue_sha256=sha(queue),
   confirmation_text='내가 봤는데 내가 일부만 했어 나머지는 이미 하늘색이 잘잡고있었어',
   saved_crop_approvals_take_priority=True,saved_manual_images=manual,overrides=overrides,
   created_utc=time,new_approval_events_written=0)
 policy=root/'user_confirmed_reference_overrides.json'
 with policy.open('x') as stream:json.dump(record,stream,ensure_ascii=False,indent=2,allow_nan=False)
 dest=root/'review_resolved_preview';dest.mkdir(exist_ok=False)
 columns_extra=['reference_confirmation_utc','reference_confirmation_source','reference_bbox_xyxy']
 seen=set()
 with source.open() as src,(dest/'preprocessing_metadata_final.csv').open('x',newline='') as dst:
  reader=csv.DictReader(src);columns=reader.fieldnames+[k for k in columns_extra if k not in reader.fieldnames];writer=csv.DictWriter(dst,fieldnames=columns);writer.writeheader()
  scope={r['image_path'] for r in cases}
  for base in reader:
   for field in columns_extra:base.setdefault(field,'')
   path=base['source_relative_path'];row=base
   if path in scope:
    # 13장에 대한 이번 명시적 확인만 적용한다. 다른 행의 자동 좌표는 그대로 둔다.
    data={**base,**{k:int(base[k]) for k in ['original_width','original_height','crop_x0','crop_y0','crop_x1','crop_y1']}}
    resolved=reconstruct_row(data,latest.get(path),reference_override=overrides.get(path))
    row={key:resolved.get(key,base.get(key,'')) for key in columns}
    for key in ['automatic_feature_status','auto_gate_status','auto_risk_codes','auto_candidate_policy','auto_candidate_x0','auto_candidate_y0','auto_candidate_x1','auto_candidate_y1']:
     row[key]=base[key]
    row['crop_target_audit_status']='REQUIRES_NEW_AUDIT';row['crop_annotation_status']=''
    row['manual_review_required']='';row['manual_review_reasons']=''
    row['crop_mask_loss']='';row['cropped_positive_pixels']='';row['crop_clipped_boxes']='';row['crop_removed_boxes']=''
    seen.add(path)
   writer.writerow(row)
 if seen!=scope:raise ValueError('Missing review image in source manifest')
 if before!={str(p):sha(p) for p in watched}:raise ValueError('Protected records changed')
 with (dest/'resolution.json').open('x') as f:json.dump(dict(manual_saved=len(manual),reference_reused=len(overrides),scoped_images=len(cases),
  original_ledgers_unchanged=True,source_sha256=sha(source),policy_sha256=sha(policy)),f,indent=2)
 print(json.dumps(dict(manual_saved=len(manual),reference_reused=len(overrides),output=str(dest)),ensure_ascii=False))


if __name__=='__main__':main()
