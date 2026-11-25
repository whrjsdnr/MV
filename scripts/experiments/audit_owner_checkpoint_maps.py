"""학습 없이 Teacher/Student/AE/입력/맵 통계 수집. 저장된 기존 가중치만 읽는다."""
from pathlib import Path
import sys,json,csv,time
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import torch,numpy as np
from mv_analysis.data.team_release_v2 import TeamReleaseV2
from models.anomaly.efficientad_s.backend import Backend
from models._shared.data import datasets
from models.detection.retinanet.preprocessing import prepare_batch
from mv_analysis.experiments.contracts import file_sha256
import argparse
parser=argparse.ArgumentParser(description='기존 체크포인트 두 개와 원래 순서의 첫 40 Target을 읽기 전용으로 감사')
parser.add_argument('--source-run',required=True);parser.add_argument('--output',required=True)
args=parser.parse_args();old=Path(args.source_run).resolve();out=Path(args.output).resolve()
if out.is_relative_to(old):raise ValueError('Source run is read-only')
out.mkdir(parents=True,exist_ok=False)
plan=json.loads((old/'plan.json').read_text());torch.set_num_threads(4)
r=TeamReleaseV2(plan['release_source'],plan['data_root'])
def stats(t):
 t=t.detach().double().cpu(); finite=torch.isfinite(t);v=t[finite]
 return dict(shape=list(t.shape),finite=int(finite.sum()),nonfinite=int((~finite).sum()),min=float(v.min()) if len(v) else None,max=float(v.max()) if len(v) else None,mean=float(v.mean()) if len(v) else None,std=float(v.std(unbiased=False)) if len(v) else None)
res={'release_sha256':r.sha256,'checkpoints':[]};cfg=plan['settings']['efficientad_s'];b=Backend(cfg,r.classes['yolo'],'cpu');data=datasets(r,cfg,category='audiojack');val=data['validation'];ids=[]
for view in ['C1','C2','C3','C4','C5']:
 ids+=val.data.index[val.data.status.eq('OK')&val.data.view.eq(view)].tolist()[:3]
res['validation_counts']=val.data.groupby(['status','view']).size().to_dict().__str__()
for p in sorted((old/'efficientad_s/audiojack').glob('checkpoint_*.json')):
 if p.name=='checkpoint_latest.json':continue
 ref=json.loads(p.read_text());cp=p.parent/ref['checkpoint_path'];assert file_sha256(cp)==ref['sha256'];state=torch.load(cp,map_location='cpu',weights_only=True)
 b.model.load_state_dict(state['model']);b.model.eval(); item={'path':str(cp),'sha256':ref['sha256'],'progress':state['progress'],'state_fields':list(state),'quantiles':b.model.quantiles.tolist(),'teacher_std':stats(b.model.teacher_std),'images':[]};maps=[[],[]]
 with torch.no_grad():
  for i in ids:
   s=val[i];x=b.input(s);t=b.model.teacher(x);st=b.model.student(x);ae=b.model.autoencoder(x);a,c=b.model.raw_maps(x)
   item['images'].append({'image_id':s['image_id'],'view':s['view'],**{k:stats(v) for k,v in [('input',x),('teacher',t),('student',st),('autoencoder',ae),('map_st',a),('map_ae',c)]}});maps[0].append(a.flatten());maps[1].append(c.flatten())
 item['map_quantiles']={k:torch.quantile(torch.cat(v).double(),torch.tensor([0.,.5,.9,.995,1.],dtype=torch.float64)).tolist() for k,v in zip(['st','ae'],maps)}
 res['checkpoints'].append(item);print('checkpoint',state['progress'],item['map_quantiles'],flush=True)
(out/'efficientad_readonly.json').write_text(json.dumps(res,indent=2))
cfg=plan['settings']['retinanet'];ds=r.dataset(task='detection',split='train',eligible_only=True)
order=torch.randperm(len(ds),generator=torch.Generator().manual_seed(cfg['seed'])).tolist()[:40]; rows=[]
for step,i in enumerate(order,1):
 s=ds[i];images,targets=prepare_batch([s],'cpu');boxes=targets[0]['boxes'];w,h=s['original_size'][1],s['original_size'][0]
 valid=bool(torch.isfinite(boxes).all() and (boxes[:,2:]>boxes[:,:2]).all() and (boxes>=0).all() and (boxes[:,[0,2]]<=w).all() and (boxes[:,[1,3]]<=h).all())
 rows.append(dict(step=step,index=i,image_id=s['image_id'],status=s['status'],width=w,height=h,box_count=len(boxes),valid=valid,labels=targets[0]['labels'].tolist(),boxes=boxes.tolist()))
(out/'retina_target_audit.json').write_text(json.dumps(rows,indent=2));print('target audit',len(rows),all(x['valid'] for x in rows),flush=True)
