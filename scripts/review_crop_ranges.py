# 한글 안내: Crop 범위를 사람이 조정하고 보존 점검 후 승인하는 서버입니다. 원본과 기존 기록은 보존합니다.
# 재현 주의: 주석 변경도 소스 해시를 바꿉니다. 기존 체크포인트는 원래 설정/해시를 확인하고 새 실행과 구분하세요.
"""Human-only crop coordinate review, separate from product GT and frozen base metadata."""
import sys,json,hashlib,logging,threading,secrets,math,argparse,io,os
from pathlib import Path
from datetime import datetime,timezone
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib.parse import urlsplit,parse_qs
sys.path.insert(0,str(Path(__file__).resolve().parent));sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np,pandas as pd
from PIL import Image
from review_product_bboxes import ReviewStore,ReviewError,json_bytes,reject_constant,bbox,ROOT
BASE=ROOT/'outputs/adaptive_crop_full_v1';ASSETS=Path(__file__).parent;LOG=logging.getLogger('crop_range_review')

# pixel_crop: 이름에 해당하는 세부 처리를 수행하며 반환값과 예외는 아래 구현의 계약을 따릅니다.
# 입력 인수: value.
def pixel_crop(value):
 c=bbox(value)
 if any(int(v)!=v for v in c):raise ReviewError('Crop boundaries must be integer pixels (XYXY exclusive)')
 return list(map(int,c))

# CropReviewStore: 관련 입력과 상태를 묶어 관리하는 구성 요소입니다.
class CropReviewStore(ReviewStore):
 # __init__: 입력 설정과 필요한 상태를 준비합니다. 잘못된 조건은 본문의 검증 규칙을 따릅니다.
 # 입력 인수: queue, data_root, base_metadata, ledger.
 def __init__(self,queue,data_root,base_metadata,ledger=None):
  ledger=Path(ledger) if ledger else Path(queue).with_name('manual_crop_review_ledger.jsonl')
  super().__init__(queue,data_root,ledger,ledger);self.base_metadata=Path(base_metadata);self.base_hash=hashlib.sha256(self.base_metadata.read_bytes()).hexdigest();self.previews={}
  if not all(r['base_manifest_sha256']==self.base_hash for r in self.rows):raise ValueError('Queue refers to another base metadata version')
 # snapshot: 저장 이력에서 현재 상태를 읽어 구성합니다.
 def snapshot(self):
  states={};mapping={r['image_path']:r for r in self.rows}
  if not self.ledger.exists():return states
  for i,line in enumerate(self.ledger.read_text().splitlines(),1):
   try:
    e=json.loads(line,parse_constant=reject_constant);r=mapping[e['image_path']];assert e['case_id']==r['case_id'];assert e['base_manifest_sha256']==self.base_hash
    if e['status']=='APPROVED_CROP':assert e['human_ack'] is True;pixel_crop(e['crop_xyxy']);assert isinstance(e['reviewer'],str) and len(e['reviewer'].strip())>=2
    elif e['status'] not in ['PENDING','REJECTED']:raise ValueError('Crop review cannot create VERIFIED_GT')
    assert e['source_sha256']==self.source_hash(r);states[e['image_path']]=e
   except Exception as exc:LOG.error('Invalid crop ledger line%d: %s',i,exc);raise ReviewError('Invalid crop review history; inspect logs; history preserved',409) from exc
  return states
 # progress: 현재 처리 또는 검수 진행 건수를 집계합니다.
 # 입력 인수: states.
 def progress(self,states):
  counts={k:0 for k in ['PROPOSAL','PENDING','REJECTED','APPROVED_CROP']}
  for r in self.rows:counts[states.get(r['image_path'],{}).get('status','PROPOSAL')]+=1
  return dict(total=len(self.rows),verified=counts['APPROVED_CROP'],remaining=len(self.rows)-counts['APPROVED_CROP'],states=counts)
 # item: 해당 검수 항목의 상태와 표시 정보를 준비합니다.
 # 입력 인수: index.
 def item(self,index):
  r=super().item(index);event=self.snapshot().get(r['image_path']);r['approved_bbox']=event.get('crop_xyxy') if event and event['status']=='APPROVED_CROP' else json.loads(r['current_crop']);return r
 # _loaded: 이름에 해당하는 세부 처리를 수행하며 반환값과 예외는 아래 구현의 계약을 따릅니다.
 # 입력 인수: payload.
 def _loaded(self,payload):
  index=payload.get('index');r=self.row(index);token=payload.get('image_receipt');receipt=self.receipts.get(token) if isinstance(token,str) else None
  if not receipt or not receipt['served'] or receipt['index']!=index or payload.get('image_rendered') is not True:raise ReviewError('Load and display the original image first')
  if payload.get('case_id')!=r['case_id'] or payload.get('source_sha256')!=receipt['source_hash'] or receipt['source_hash']!=self.source_hash(r):raise ReviewError('Source changed; reload',409)
  return r,receipt
 # aux_path: 이름에 해당하는 세부 처리를 수행하며 반환값과 예외는 아래 구현의 계약을 따릅니다.
 # 입력 인수: value.
 def aux_path(self,value):
  p=(self.data_root/str(value).replace('\\','/')).resolve()
  if not p.is_relative_to(self.data_root) or not p.is_file():raise ReviewError('Invalid reference mask path')
  return p
 # mask_overlay: 이름에 해당하는 세부 처리를 수행하며 반환값과 예외는 아래 구현의 계약을 따릅니다.
 # 입력 인수: index.
 def mask_overlay(self,index):
  r=self.row(index);value=r.get('evaluation_mask_path')
  if not isinstance(value,str) or not value:raise ReviewError('No location mask provided',404)
  with Image.open(self.aux_path(value)) as im:m=np.asarray(im.convert('L'))>0
  rgba=np.zeros((*m.shape,4),np.uint8);rgba[m]=[255,0,255,120];stream=io.BytesIO();Image.fromarray(rgba).save(stream,format='PNG');return stream.getvalue()
 # preview: 저장 전에 후보 범위의 검증 결과를 계산합니다.
 # 입력 인수: payload.
 def preview(self,payload):
  r,receipt=self._loaded(payload);crop=pixel_crop(payload.get('bbox'));x0,y0,x1,y1=crop;reference=r.get('reference_product_bbox');product=None
  if isinstance(reference,str) and reference:
   b=bbox(reference);inter=max(0,min(x1,b[2])-max(x0,b[0]))*max(0,min(y1,b[3])-max(y0,b[1]));area=(b[2]-b[0])*(b[3]-b[1]);product=dict(status='REFERENCE_GT',area_recall=inter/area,fully_contained=x0<=b[0] and y0<=b[1] and x1>=b[2] and y1>=b[3])
  else:product=dict(status='UNVERIFIED',area_recall=None,fully_contained=None)
  value=r.get('evaluation_mask_path');mask=dict(status='NOT_PROVIDED',original_pixels=None,kept_pixels=None,retention=None)
  if isinstance(value,str) and value:
   with Image.open(self.aux_path(value)) as im:m=np.asarray(im.convert('L'))>0
   assert m.shape==(1024,1024);total=int(m.sum());kept=int(m[y0:y1,x0:x1].sum());mask=dict(status='PROVIDED_POSITIVE' if total else 'PROVIDED_EMPTY',original_pixels=total,kept_pixels=kept,retention=kept/total if total else None)
  observed_loss=product['fully_contained'] is False or (mask['retention'] is not None and mask['retention']<1)
  unknown=product['status']=='UNVERIFIED' or mask['status']!='PROVIDED_POSITIVE';token=secrets.token_urlsafe(24);result=dict(crop=crop,product=product,defect_mask=mask,observed_loss=bool(observed_loss),unverified_regions=bool(unknown),requires_risk_ack=bool(observed_loss or unknown),area_equivalent_gain=math.sqrt(1024**2/((x1-x0)*(y1-y0))),review_split=r['split'],annotation_assisted=product['status']=='REFERENCE_GT' or mask['status'].startswith('PROVIDED'),preview_receipt=token)
  if len(self.previews)>2048:
   for key in list(self.previews)[:1024]:del self.previews[key]
  self.previews[token]=dict(result=result,image_receipt=payload['image_receipt'],source_hash=receipt['source_hash']);return result
 # approve: 이미지 확인·사람 동의·검수자·미리보기·이력 리비전을 검증한 뒤 승인 기록만 추가합니다.
 # 입력 인수: payload.
 def approve(self,payload):
  r,receipt=self._loaded(payload);reviewer=payload.get('reviewer');status=payload.get('review_state','APPROVED_CROP')
  if not isinstance(reviewer,str) or len(reviewer.strip())<2:raise ReviewError('Reviewer name/id required')
  if status=='APPROVED_CROP':
   if payload.get('human_ack') is not True:raise ReviewError('Explicit human crop confirmation required')
   crop=pixel_crop(payload.get('bbox'));preview=self.previews.get(payload.get('preview_receipt',''))
   if not preview or preview['image_receipt']!=payload['image_receipt'] or preview['result']['crop']!=crop or preview['source_hash']!=receipt['source_hash']:raise ReviewError('Run crop preservation check after the last coordinate change')
   if preview['result']['requires_risk_ack'] and payload.get('risk_ack') is not True:raise ReviewError('Explicit acknowledgement of loss/unverified warnings required')
  elif status in ['PENDING','REJECTED']:
   if not str(payload.get('notes') or '').strip():raise ReviewError('Reason required')
   crop=None;preview=None
  else:raise ReviewError('This tool accepts crop review states only; never VERIFIED_GT')
  with self.write_lock():
   states=self.snapshot();old=states.get(r['image_path']);notes=str(payload.get('notes') or '')
   if old and old['status']==status and old.get('crop_xyxy')==crop and old['reviewer']==reviewer.strip() and old.get('notes','')==notes:return dict(saved=r['case_id'],status=status,duplicate=True,progress=self.progress(states))
   if payload.get('expected_revision')!=self.revision(old) or receipt['revision']!=self.revision(old):raise ReviewError('Another crop review changed this item; reload',409)
   if old and old['status']=='APPROVED_CROP' and payload.get('re_review_ack') is not True:raise ReviewError('Re-review acknowledgement required',409)
   event=dict(case_id=r['case_id'],image_path=r['image_path'],status=status,crop_xyxy=crop,reviewer=reviewer.strip(),human_ack=payload.get('human_ack') is True,risk_ack=payload.get('risk_ack') is True,reviewed_utc=datetime.now(timezone.utc).isoformat(),notes=notes,source_sha256=receipt['source_hash'],source_fingerprint=r['source_fingerprint'],base_manifest_sha256=self.base_hash,previous_revision=self.revision(old),preview_evaluation=preview['result'] if preview else None,not_product_gt=True)
   with self.ledger.open('a') as out:out.write(json_bytes(event).decode()+'\n');out.flush();os.fsync(out.fileno())
   states[r['image_path']]=event;return dict(saved=r['case_id'],status=status,duplicate=False,progress=self.progress(states))
 # export: 최신 유효 승인만 전체 기준 CSV에 반영해 새 버전 파일을 만들며 기존 CSV는 덮어쓰지 않습니다.
 # 입력 인수: directory.
 def export(self,directory=None):
  with self.write_lock():
   states=self.snapshot();approvals={r['case_id']:r for r in states.values() if r['status']=='APPROVED_CROP'}
   if hashlib.sha256(self.base_metadata.read_bytes()).hexdigest()!=self.base_hash:raise ReviewError('Base metadata changed',409)
   d=pd.read_csv(self.base_metadata,keep_default_na=False)
   # 자동 적용 CSV 위에서 일부만 재검수해도 이전 사람 승인/정답 참조 이력을 지우지 않는다.
   defaults=dict(crop_review_status='UNREVIEWED_BASELINE',crop_reviewer='',crop_reviewed_utc='',
    manual_annotation_assisted=False,requires_evaluation_leakage_review=False,
    geometric_gain_definition='SQRT_ORIGINAL_AREA_OVER_CROP_AREA',manual_crop_warning='')
   for name,value in defaults.items():
    if name not in d.columns:d[name]=value
   for i,r in d.iterrows():
    e=approvals.get(r.image_id)
    if not e:continue
    if e['image_path']!=r.source_relative_path or e['source_fingerprint']!=r.source_fingerprint:raise ReviewError('Approval source mismatch',409)
    x0,y0,x1,y1=pixel_crop(e['crop_xyxy']);full=[x0,y0,x1,y1]==[0,0,int(r.original_width),int(r.original_height)]
    fields=dict(crop_x0=x0,crop_y0=y0,crop_x1=x1,crop_y1=y1,crop_width=x1-x0,crop_height=y1-y0,full_frame=full,geometric_gain=math.sqrt(r.original_width*r.original_height/((x1-x0)*(y1-y0))),selected_policy='C' if full else 'HUMAN_CROP',quality_status='HUMAN_APPROVED_WITH_WARNING' if e['preview_evaluation']['requires_risk_ack'] else 'HUMAN_APPROVED_CROP',fallback_reason='HUMAN_CONFIRMED_FULL_FRAME' if full else '',policy_version=str(r.policy_version)+'+human-override-v1',policy_sha256=hashlib.sha256((str(r.policy_sha256)+self.revision(e)).encode()).hexdigest(),processing_status='OK_HUMAN_CROP_REVIEW',crop_review_status='APPROVED_CROP',manual_crop_warning='HUMAN_ACKNOWLEDGED_LOSS_OR_UNVERIFIED_REGION' if e['preview_evaluation']['requires_risk_ack'] else '',crop_reviewer=e['reviewer'],crop_reviewed_utc=e['reviewed_utc'],manual_annotation_assisted=e['preview_evaluation']['annotation_assisted'],requires_evaluation_leakage_review=r.split=='test' and e['preview_evaluation']['annotation_assisted'])
    # 재구성 CSV의 선택/감사 요약도 새 승인과 일치시킨다. 다른 행의 승인 기록은 유지한다.
    for key,value in dict(crop_policy=fields['selected_policy'],approved_crop_present=True,
     selection_provenance='LATEST_EXPLICIT_HUMAN_CROP_APPROVAL',manual_review_required=False,
     human_observed_loss_acknowledged=bool(e.get('risk_ack') and e['preview_evaluation'].get('observed_loss')),
     manual_review_reasons='',crop_target_audit_status='HUMAN_PREVIEW_CHECKED_REAUDIT_AFTER_EXPORT').items():
     if key in d.columns:fields[key]=value
    for key,value in fields.items():d.at[i,key]=value
   d['gain_x']=d.original_width/d.crop_width;d['gain_y']=d.original_height/d.crop_height
   directory=Path(directory) if directory else self.base_metadata.parent;directory.mkdir(exist_ok=True)
   version=1
   while (directory/f'preprocessing_metadata_reviewed_v{version}.csv').exists():version+=1
   dest=directory/f'preprocessing_metadata_reviewed_v{version}.csv';tmp=dest.with_suffix('.partial');d.to_csv(tmp,index=False);os.replace(tmp,dest)
   return dict(path=str(dest),rows=len(d),human_approved_rows=len(approvals),policy_counts=d.selected_policy.value_counts().to_dict(),base_metadata_unchanged=True,product_gt_ledger_modified=False)

# make_crop_server: 후속 처리가 사용할 객체나 결과를 생성합니다.
# 입력 인수: store, port.
def make_crop_server(store,port=0):
 # Handler: 관련 입력과 상태를 묶어 관리하는 구성 요소입니다.
 class Handler(BaseHTTPRequestHandler):
  # send: 이름에 해당하는 세부 처리를 수행하며 반환값과 예외는 아래 구현의 계약을 따릅니다.
  # 입력 인수: status, value, kind, headers.
  def send(self,status,value,kind='application/json; charset=utf-8',headers=None):
   try:data=value if isinstance(value,bytes) else json_bytes(value)
   except Exception:LOG.exception('JSON serialization failed');status=500;data=json_bytes(dict(error='JSON serialization failed'))
   self.send_response(status)
   for k,v in {'Content-Type':kind,'Content-Length':str(len(data)),'Cache-Control':'no-store','X-Content-Type-Options':'nosniff',**(headers or {})}.items():self.send_header(k,v)
   self.end_headers();self.wfile.write(data)
  # do_GET: 로컬 HTTP 요청을 검증하고 해당 응답 경로로 전달합니다.
  def do_GET(self):
   try:
    url=urlsplit(self.path)
    if url.path=='/':self.send(200,(ASSETS/'crop_range_review.html').read_bytes(),'text/html; charset=utf-8');return
    if url.path=='/review.js':self.send(200,(ASSETS/'crop_range_review.js').read_bytes(),'text/javascript; charset=utf-8');return
    parts=url.path.strip('/').split('/');index=int(parts[1]);store.row(index)
    if parts[0]=='next_pending':
     states=store.snapshot();order=list(range(index+1,len(store.rows)))+list(range(index+1));next_index=next((i for i in order if states.get(store.rows[i]['image_path'],{}).get('status')!='APPROVED_CROP'),None);self.send(200,dict(index=next_index))
    elif parts[0]=='item':self.send(200,store.item(index))
    elif parts[0]=='image':
     token=parse_qs(url.query).get('token',[None])[0];self.send(200,store.image(index,token),'image/jpeg',{'X-Review-Receipt':token or ''})
    elif parts[0]=='mask_overlay':self.send(200,store.mask_overlay(index),'image/png')
    else:raise ReviewError('Not found',404)
   except Exception as exc:self.send(exc.status if isinstance(exc,ReviewError) else 400,dict(error=str(exc)))
  # do_POST: 로컬 HTTP 요청을 검증하고 해당 응답 경로로 전달합니다.
  def do_POST(self):
   try:
    if self.headers.get('Content-Type','').split(';')[0]!='application/json':raise ReviewError('application/json required',415)
    origin=self.headers.get('Origin')
    if origin and origin!=f'http://{self.headers.get("Host")}':raise ReviewError('Cross-origin request rejected',403)
    n=int(self.headers.get('Content-Length',0))
    if not 0<n<=10000:raise ReviewError('Invalid payload size')
    payload=json.loads(self.rfile.read(n),parse_constant=reject_constant)
    if self.path=='/approve':r=store.approve(payload)
    elif self.path=='/preview_crop':r=store.preview(payload)
    elif self.path=='/export':r=store.export()
    else:raise ReviewError('Not found',404)
    self.send(200,r)
   except Exception as exc:LOG.warning('Crop request rejected: %s',exc);self.send(exc.status if isinstance(exc,ReviewError) else 400,dict(error=str(exc)))
 return ThreadingHTTPServer(('127.0.0.1',port),Handler)

# main: 명령행 인수를 읽고 본 파일의 처리 흐름을 실행합니다.
def main():
 p=argparse.ArgumentParser();p.add_argument('--queue',type=Path,default=BASE/'manual_crop_review.csv');p.add_argument('--metadata',type=Path,default=BASE/'preprocessing_metadata.csv');p.add_argument('--data-root',type=Path,default=ROOT/'dataset');p.add_argument('--ledger',type=Path);p.add_argument('--port',type=int,default=8769);p.add_argument('--check',action='store_true');a=p.parse_args();logging.basicConfig(level=logging.INFO);store=CropReviewStore(a.queue,a.data_root,a.metadata,a.ledger)
 if a.check:print(json_bytes(store.progress(store.snapshot())|dict(product_gt_modified=False)).decode());return
 server=make_crop_server(store,a.port);print(f'Human Crop review only: http://127.0.0.1:{server.server_port} /{len(store.rows)} cases. Product GT and base CSV are read-only.',flush=True)
 try:server.serve_forever()
 except KeyboardInterrupt:pass
 finally:server.server_close()
if __name__=='__main__':main()
