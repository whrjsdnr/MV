"""새 CSV에서 달라진 후보만 기존 마스크/제품 GT/BBox로 사후 감사한다. 좌표는 변경하지 않는다."""
from pathlib import Path
import argparse,csv,json,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import cv2
ROOT=Path(__file__).resolve().parents[1]


def main():
 p=argparse.ArgumentParser(description='재구성 Crop 후보 사후 감사');p.add_argument('--directory',required=True,type=Path);args=p.parse_args();out=args.directory
 gt={}
 for line in (ROOT/'outputs/object_aware_crop_v1/review/human_approved_gt.jsonl').read_text().splitlines():
  r=json.loads(line)
  if r['status']=='VERIFIED_GT':gt[r['image_path']]=r
 boxes={}
 with (ROOT/'outputs/team_data_release_v2/MV_TEAM_DATA_RELEASE_v2/annotations/defect_boxes.csv').open() as f:
  for r in csv.DictReader(f):boxes.setdefault(r['image_id'],[]).append([float(r[k]) for k in ['x0','y0','x1','y1']])
 results=[]
 with (out/'automatic_candidate_changes.csv').open() as f:
  for row in csv.DictReader(f):
   x0,y0,x1,y1=[int(row['crop_'+v]) for v in ['x0','y0','x1','y1']];r=dict(image_id=row['image_id'],image_path=row['source_relative_path'],mask_status='MISSING',original_pixels=None,kept_pixels=None,pixel_retention=None,mask_loss=False,product_gt_available=False,product_bbox_contained=None,boxes=len(boxes.get(row['image_id'],[])),clipped_boxes=0,removed_boxes=0)
   if row['mask_path']:
    mask=cv2.imread(str(ROOT/'dataset'/row['mask_path']),cv2.IMREAD_UNCHANGED)
    if mask is None or mask.shape!=(1024,1024):raise ValueError('Mask decode/size error')
    original=int((mask>0).sum());kept=int((mask[y0:y1,x0:x1]>0).sum());r.update(mask_status='PRESENT_POSITIVE' if original else 'PRESENT_EMPTY',original_pixels=original,kept_pixels=kept,pixel_retention=kept/original if original else None,mask_loss=kept<original)
   for a,b,c,d in boxes.get(row['image_id'],[]):
    if not(x0<=a and y0<=b and x1>=c and y1>=d):r['clipped_boxes']+=1
    if min(x1,c)<=max(x0,a) or min(y1,d)<=max(y0,b):r['removed_boxes']+=1
   if row['source_relative_path'] in gt:
    a,b,c,d=gt[row['source_relative_path']]['bbox'];r.update(product_gt_available=True,product_bbox_contained=x0<=a and y0<=b and x1>=c and y1>=d)
   results.append(r)
 with (out/'automatic_candidate_loss_audit.csv').open('x',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(results[0]));w.writeheader();w.writerows(results)
 original=sum(r['original_pixels'] or 0 for r in results);kept=sum(r['kept_pixels'] or 0 for r in results)
 summary=dict(changed_candidate_images=len(results),provided_positive_masks=sum(r['mask_status']=='PRESENT_POSITIVE' for r in results),mask_loss_images=sum(r['mask_loss'] for r in results),complete_mask_removal_images=sum(r['original_pixels'] is not None and r['original_pixels']>0 and r['kept_pixels']==0 for r in results),pixel_weighted_retention=kept/original if original else None,product_gt_images=sum(r['product_gt_available'] for r in results),product_gt_loss_images=sum(r['product_bbox_contained'] is False for r in results),clipped_boxes=sum(r['clipped_boxes'] for r in results),removed_boxes=sum(r['removed_boxes'] for r in results),crop_selection_used_masks=False,coordinates_changed_by_audit=False)
 with (out/'automatic_candidate_loss_audit.json').open('x') as f:json.dump(summary,f,indent=2)
 print(json.dumps(summary))

if __name__=='__main__':main()
