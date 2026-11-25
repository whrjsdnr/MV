# 한글 안내: 합성·임시 자료로 해당 기능의 계약과 오류 처리를 검사하는 테스트입니다.
# 재현 주의: 주석 변경도 소스 해시를 바꿉니다. 기존 체크포인트는 원래 설정/해시를 확인하고 새 실행과 구분하세요.
import sys,json,hashlib
from pathlib import Path
import numpy as np,pandas as pd,pytest
from PIL import Image
sys.path.insert(0,str(Path('scripts').resolve()))
from review_crop_ranges import CropReviewStore,pixel_crop,make_crop_server
from generate_full_crop_manifest import process_source

# store: 이름에 해당하는 세부 처리를 수행하며 반환값과 예외는 아래 구현의 계약을 따릅니다.
# 입력 인수: tmp_path.
@pytest.fixture
def store(tmp_path):
 rows=[]
 for name in ['a.png','b.png']:
  Image.new('RGB',(1024,1024),'white').save(tmp_path/name)
  r=dict(image_path=name,product_id='synthetic/product',category='synthetic',view='C1',split='validation',width=1024,height=1024)
  rows.append(process_source((r,dict(production_mode='FULL_FRAME_UNVERIFIED_SCOPES',approved_scopes={},policy_version='test-safe'),'test-policy',tmp_path,None,{})))
 base=tmp_path/'base.csv';pd.DataFrame(rows).to_csv(base,index=False);digest=hashlib.sha256(base.read_bytes()).hexdigest();m=np.zeros((1024,1024),np.uint8);m[500:520,500:520]=255;Image.fromarray(m).save(tmp_path/'mask.png')
 q=pd.DataFrame([dict(case_id=rows[0]['image_id'],image_id=rows[0]['image_id'],image_path='a.png',product_id='synthetic/product',category='synthetic',view='C1',split='validation',status='CROP_REVIEW_REQUIRED',current_crop='[0,0,1024,1024]',proposal_bbox='[100,100,900,900]',reference_product_bbox='[100,100,900,900]',evaluation_mask_path='mask.png',mask_available=True,source_fingerprint=rows[0]['source_fingerprint'],base_manifest_sha256=digest)]);queue=tmp_path/'queue.csv';q.to_csv(queue,index=False)
 return CropReviewStore(queue,tmp_path,base,tmp_path/'temporary_crop_ledger.jsonl')

# payload: 이름에 해당하는 세부 처리를 수행하며 반환값과 예외는 아래 구현의 계약을 따릅니다.
# 입력 인수: store, crop.
def payload(store,crop):
 i=store.item(0);store.image(0,i['image_token']);p=dict(index=0,case_id=i['case_id'],source_sha256=i['source_sha256'],image_receipt=i['image_token'],image_rendered=True,bbox=crop,reviewer='synthetic-tester',human_ack=True,expected_revision=i['review_revision'],review_state='APPROVED_CROP');return p

# test_crop_preview_no_write_and_mask_overlay: 정상·오류 상황을 검증하는 회귀 테스트입니다.
# 입력 인수: store.
def test_crop_preview_no_write_and_mask_overlay(store):
 p=payload(store,[100,100,900,900]);r=store.preview(p);assert r['product']['fully_contained'] and r['defect_mask']['retention']==1 and not r['observed_loss'];assert not store.ledger.exists();assert store.mask_overlay(0).startswith(b'\x89PNG')

# test_human_crop_requires_preview_and_confirmation: 정상·오류 상황을 검증하는 회귀 테스트입니다.
# 입력 인수: store.
def test_human_crop_requires_preview_and_confirmation(store):
 p=payload(store,[100,100,900,900])
 with pytest.raises(ValueError):store.approve(p)
 r=store.preview(p);p['preview_receipt']=r['preview_receipt'];p['human_ack']=False
 with pytest.raises(ValueError):store.approve(p)
 assert not store.ledger.exists()

# test_changed_coordinates_invalidate_preview: 정상·오류 상황을 검증하는 회귀 테스트입니다.
# 입력 인수: store.
def test_changed_coordinates_invalidate_preview(store):
 p=payload(store,[100,100,900,900]);p['preview_receipt']=store.preview(p)['preview_receipt'];p['bbox']=[90,90,910,910]
 with pytest.raises(ValueError):store.approve(p)
 assert not store.ledger.exists()

# test_observed_loss_requires_separate_explicit_ack: 정상·오류 상황을 검증하는 회귀 테스트입니다.
# 입력 인수: store.
def test_observed_loss_requires_separate_explicit_ack(store):
 p=payload(store,[600,600,900,900]);r=store.preview(p);assert r['observed_loss'] and r['defect_mask']['retention']==0;p['preview_receipt']=r['preview_receipt']
 with pytest.raises(ValueError):store.approve(p)
 assert not store.ledger.exists()
 p['risk_ack']=True;store.approve(p);assert store.snapshot()['a.png']['preview_evaluation']['observed_loss']

# test_export_only_approved_rows_preserves_base_and_never_creates_product_gt: 정상·오류 상황을 검증하는 회귀 테스트입니다.
# 입력 인수: store, tmp_path.
def test_export_only_approved_rows_preserves_base_and_never_creates_product_gt(store,tmp_path):
 before=store.base_metadata.read_bytes();p=payload(store,[100,100,900,900]);p['preview_receipt']=store.preview(p)['preview_receipt'];r=store.approve(p);assert r['status']=='APPROVED_CROP';assert store.approve(p)['duplicate'];assert len(store.ledger.read_text().splitlines())==1
 out=store.export();d=pd.read_csv(out['path']);assert out['rows']==2 and out['human_approved_rows']==1;assert d.iloc[0].selected_policy=='HUMAN_CROP' and d.iloc[0].crop_width==800 and d.iloc[1].selected_policy=='C' and d.iloc[1].crop_width==1024;assert store.base_metadata.read_bytes()==before;assert 'VERIFIED_GT' not in store.ledger.read_text();assert not (tmp_path/'human_approved_gt.jsonl').exists()
 second=store.export();assert second['path']!=out['path'] and Path(out['path']).exists()

# test_product_gt_or_automatic_approval_state_forbidden: 정상·오류 상황을 검증하는 회귀 테스트입니다.
# 입력 인수: store, status.
@pytest.mark.parametrize('status',['VERIFIED_GT','APPROVED_BY_AI'])
def test_product_gt_or_automatic_approval_state_forbidden(store,status):
 p=payload(store,[0,0,1024,1024]);p['review_state']=status
 with pytest.raises(ValueError):store.approve(p)
 assert not store.ledger.exists()

# test_crop_re_review_and_pending_preserve_history: 정상·오류 상황을 검증하는 회귀 테스트입니다.
# 입력 인수: store.
def test_crop_re_review_and_pending_preserve_history(store):
 p=payload(store,[100,100,900,900]);p['preview_receipt']=store.preview(p)['preview_receipt'];store.approve(p);new=payload(store,[0,0,1024,1024]);new['preview_receipt']=store.preview(new)['preview_receipt']
 with pytest.raises(ValueError):store.approve(new)
 new['re_review_ack']=True;store.approve(new);assert len(store.ledger.read_text().splitlines())==2
 pending=payload(store,[0,0,1024,1024]);pending.update(review_state='PENDING',notes='needs another reviewer',re_review_ack=True);store.approve(pending);assert store.progress(store.snapshot())['verified']==0
 assert pd.read_csv(store.export()['path']).selected_policy.eq('C').all()

# test_fractional_crop_and_cross_image_receipts_rejected: 정상·오류 상황을 검증하는 회귀 테스트입니다.
# 입력 인수: store.
def test_fractional_crop_and_cross_image_receipts_rejected(store):
 with pytest.raises(ValueError):pixel_crop([.1,0,100,100])
 p=payload(store,[0,0,1024,1024]);p['image_rendered']=False
 with pytest.raises(ValueError):store.preview(p)

# test_loopback_ui_preview_approval_and_export_use_only_temporary_data: 정상·오류 상황을 검증하는 회귀 테스트입니다.
# 입력 인수: store.
def test_loopback_ui_preview_approval_and_export_use_only_temporary_data(store):
 import threading,urllib.request
 from review_product_bboxes import reject_constant
 server=make_crop_server(store,0);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();base=f'http://127.0.0.1:{server.server_port}'
 # call: 이름에 해당하는 세부 처리를 수행하며 반환값과 예외는 아래 구현의 계약을 따릅니다.
 # 입력 인수: path, p.
 def call(path,p=None):
  req=urllib.request.Request(base+path,data=json.dumps(p).encode() if p is not None else None,headers={'Content-Type':'application/json'} if p is not None else {})
  with urllib.request.urlopen(req,timeout=10) as r:return r.status,r.headers,r.read()
 try:
  assert call('/')[0]==200 and call('/review.js')[0]==200
  _,_,data=call('/item/0');item=json.loads(data,parse_constant=reject_constant);assert item['review_state']=='PROPOSAL'
  assert call('/image/0?token='+item['image_token'])[0]==200;assert call('/mask_overlay/0')[2].startswith(b'\x89PNG')
  p=dict(index=0,case_id=item['case_id'],source_sha256=item['source_sha256'],image_receipt=item['image_token'],image_rendered=True,bbox=[100,100,900,900],reviewer='temporary-http-tester',human_ack=True,expected_revision=item['review_revision'],review_state='APPROVED_CROP')
  p['preview_receipt']=json.loads(call('/preview_crop',p)[2])['preview_receipt'];assert json.loads(call('/approve',p)[2])['status']=='APPROVED_CROP'
  e=json.loads(call('/export',{})[2]);assert e['rows']==2 and e['human_approved_rows']==1 and Path(e['path']).is_relative_to(store.base_metadata.parent)
 finally:server.shutdown();server.server_close();thread.join(timeout=3)

# test_rectangular_manual_crop_exports_separate_axis_gains: 정상·오류 상황을 검증하는 회귀 테스트입니다.
# 입력 인수: store.
def test_rectangular_manual_crop_exports_separate_axis_gains(store):
 p=payload(store,[100,100,1000,950]);p['preview_receipt']=store.preview(p)['preview_receipt'];store.approve(p);d=pd.read_csv(store.export()['path']);r=d.iloc[0];assert r.crop_width==900 and r.crop_height==850;assert r.gain_x==pytest.approx(1024/900) and r.gain_y==pytest.approx(1024/850);assert r.geometric_gain==pytest.approx((1024**2/(900*850))**.5)

# test_loader_findings_filtered_review_preserves_full_export_and_history: 정상·오류 상황을 검증하는 회귀 테스트입니다.
# 입력 인수: store.
def test_loader_findings_filtered_review_preserves_full_export_and_history(store):
 from review_loader_findings import FindingsStore
 selection={'indices':[0],'initial_revisions':{'0':store.revision(None)}}
 filtered=FindingsStore(store,selection)
 assert filtered.item(0)['total']==1
 assert filtered.progress(filtered.snapshot())['verified']==0
 with pytest.raises(ValueError):filtered.row(1)
 p=payload(store,[100,100,900,900]);p['preview_receipt']=filtered.preview(p)['preview_receipt']
 result=filtered.approve(p);assert result['progress']['verified']==1
 assert len(store.ledger.read_text().splitlines())==1
 out=filtered.export();assert len(pd.read_csv(out['path']))==2
 assert store.base_metadata.exists()


def test_partial_review_export_preserves_other_existing_human_approval(store,tmp_path):
 """새 위험 큐의 일부만 승인해도 기존 승인된 다른 행의 검수자를 지우지 않는다."""
 d=pd.read_csv(store.base_metadata)
 d['crop_review_status']=['UNREVIEWED','APPROVED_CROP'];d['crop_reviewer']=['','previous-human']
 d['crop_reviewed_utc']=['','2026-11-17T00:00:00Z']
 d.to_csv(store.base_metadata,index=False)
 q=pd.read_csv(store.proposals);q['base_manifest_sha256']=hashlib.sha256(store.base_metadata.read_bytes()).hexdigest()
 queue=tmp_path/'new_queue.csv';q.to_csv(queue,index=False)
 new=CropReviewStore(queue,tmp_path,store.base_metadata,tmp_path/'new_ledger.jsonl')
 p=payload(new,[100,100,900,900]);p['preview_receipt']=new.preview(p)['preview_receipt'];new.approve(p)
 exported=pd.read_csv(new.export()['path'])
 assert exported.iloc[1].crop_review_status=='APPROVED_CROP'
 assert exported.iloc[1].crop_reviewer=='previous-human'
 assert exported.iloc[1].crop_reviewed_utc=='2026-11-17T00:00:00Z'
