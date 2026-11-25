"""실제 원본 표본으로 v2 세 입력 계약과 원본 좌표 복원을 검증한다. 모델 추론은 하지 않는다."""
from pathlib import Path
import numpy as np
import pandas as pd
import torch
from .team_release_v2 import TeamReleaseV2
from .datasets import FiveViewDataset
from .adapters import get_adapter, SPECS
from .collate import five_view_collate, detection_collate
from mv_analysis.experiments.geometry import restore_boxes, restore_map


def smoke_v2(root,data_root,figures=None):
    """30품목/OKNG/시점/Split/출처/43장 포함 그룹 표본을 구성하고 예측 아닌 주석 그림을 남긴다."""
    torch.set_num_threads(1)
    release=TeamReleaseV2(root,data_root);d=release.canonical
    chosen=set(d.groupby(['category','status']).first().product_id)
    for cols in [['split','status'],['mask_status'],['product_bbox_source'],['selected_policy']]:
        chosen.update(d.groupby(cols).first().product_id)
    changed=pd.read_csv(Path(root)/'validation/re_review_43.csv').image_id
    chosen.update(d[d.image_id.isin(changed)].product_id)
    ids=d[d.product_id.isin(chosen)].image_id
    result=dict(status='VERIFIED',release_version='MV_TEAM_DATA_RELEASE_v2',canonical_sha256=release.sha256,
                unique_images=len(ids),products=len(chosen),categories=d[d.image_id.isin(ids)].category.nunique(),
                modes={},model_forward='NOT_RUN',model_training='NOT_RUN',product_independent_evaluation='UNVERIFIED')
    raw_example=None
    for mode,task,policy in [('ANOMALY','anomaly','defect_only'),('D1','detection','defect_only'),('D2','detection','product_and_defect')]:
        ds=release.dataset(task=task,annotation_policy=policy,image_ids=ids)
        states={};full=0;objects=0
        for i,s in enumerate(ds):
            h,w=s['original_size'];image=s['image'];assert image.dtype==torch.float32 and 0<=image.min()<=image.max()<=1
            if task=='detection':
                assert image.shape==(3,h,w) and s['crop_xyxy']==(0,0,w,h)
                full+=1
            if s['mask'] is not None:assert s['mask'].shape[-2:]==image.shape[-2:]
            if s['status']=='NG' and s['mask_status'] in ('MISSING','PRESENT_EMPTY'):
                assert not s['detection_trainable'] and not s['defect_boxes_known']
            if s['detection_trainable']:detection_collate([s])
            if mode=='D1' and s['status']=='OK':assert len(s['boxes'])==0
            if mode=='D2':assert s['annotation_types'][0]=='PRODUCT'
            if raw_example is None and mode=='D2' and s['status']=='NG' and s['defect_boxes_known']:raw_example=s
            states[s['mask_status']]=states.get(s['mask_status'],0)+1;objects+=len(s['boxes'])
            if (i+1)%100==0:print(f'V2 SMOKE {mode} {i+1}/{len(ds)}',flush=True)
        adapter=get_adapter('EfficientAD-S' if task=='anomaly' else 'YOLO11')
        adapted=release.dataset(task=task,annotation_policy=policy,image_ids=ids,adapter=adapter)
        five=FiveViewDataset(adapted)
        # 모든 선택 그룹의 원본은 이미 읽었다. 대표 2그룹으로 고정 크기 배치 계약을 확인한다.
        batch=five_view_collate([five[0],five[1]])
        size=256 if task=='anomaly' else 640
        assert batch['images'].shape==(2,5,3,size,size)
        result['modes'][mode]=dict(images=len(ds),objects=objects,mask_states=states,original_full_images=full,
                                   five_view_groups=len(five),batch_shape=list(batch['images'].shape),splits=sorted(ds.data.split.unique()))
    roundtrip={}
    for name,spec in SPECS.items():
        if spec.task!='detection':continue
        out=get_adapter(name)(raw_example);m=out['metadata']
        b,keep,_=restore_boxes(out['boxes'].numpy(),original_hw=out['original_size'],crop_xyxy=out['crop_xyxy'],input_hw=out['image_size'],
                              scale_xy=m['resize_scale_xy'],padding_lrtb=m['padding_lrtb'],box_format=m['boxes_format'],normalized=m['boxes_normalized'])
        delta=float(np.max(np.abs(b-raw_example['boxes'].numpy()))) if len(b) else 0.
        assert keep.all() and delta<1e-3
        roundtrip[name]=dict(max_absolute_pixel_error=delta,input_shape=list(out['image'].shape),padding=m['padding_lrtb'],model_integration='UNVERIFIED')
    result['detector_adapter_roundtrip']=roundtrip
    # 새 분류 Head나 합성 예측을 만들지 않고 저장 GT 마스크의 좌표 복원만 확인한다.
    candidates=d[d.mask_status.eq('PRESENT_POSITIVE') & d.split.eq('test') & ~d.full_frame]
    if len(candidates):
        s=release.dataset(task='anomaly',image_ids=[candidates.iloc[0].image_id])[0]
        restored,observed=restore_map(s['mask'][0].numpy(),original_hw=s['original_size'],crop_xyxy=s['crop_xyxy'],input_hw=s['image_size'],categorical=True)
        assert restored.sum()==s['mask'].sum().item()
        result['anomaly_restore']=dict(image_id=s['image_id'],mask_pixels=int(restored.sum()),observed_pixels=int(observed.sum()),outside_crop_unobserved=True)
    if figures:
        result['figures']=draw_cases(release,Path(figures))
    return result


def draw_cases(release,folder):
    """내부 점검용. 원본/승인 Crop/D1·D2 좌표를 보여 주며 이 그림은 데이터 ZIP에 포함하지 않는다."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    folder.mkdir(parents=True,exist_ok=True)
    d=release.canonical
    picks=[]
    for condition in [d.status.eq('OK') & d.product_bbox_source.eq('HUMAN_VERIFIED_GT'),
                      d.status.eq('NG') & d.mask_status.eq('PRESENT_POSITIVE') & ~d.full_frame,
                      d.status.eq('NG') & d.mask_status.eq('MISSING'),
                      d.status.eq('OK') & d.product_bbox_source.eq('CROP_APPROXIMATION')]:
        if condition.any():picks.append(d[condition].iloc[0].image_id)
    files=[]
    for i,image_id in enumerate(dict.fromkeys(picks)):
        d1=release.dataset(task='detection',image_ids=[image_id])[0]
        d2=release.dataset(task='detection',annotation_policy='product_and_defect',image_ids=[image_id])[0]
        # Train NG를 이상탐지 학습 대상으로 선택하지 않도록 그림은 저장 좌표로 직접 자른다.
        r=release.by_id.loc[image_id];x0,y0,x1,y1=[int(r['crop_'+a]) for a in ('x0','y0','x1','y1')]
        rgb=d1['image'].permute(1,2,0).numpy()
        fig,axes=plt.subplots(1,3,figsize=(16,6))
        axes[0].imshow(rgb[y0:y1,x0:x1]);axes[0].set_title(f'Anomaly approved Crop\n{x1-x0} x {y1-y0} px')
        for ax,s,title in [(axes[1],d1,'D1 original / defects'),(axes[2],d2,'D2 original / product + defects')]:
            ax.imshow(rgb)
            for box,kind in zip(s['boxes'].tolist(),s['annotation_types']):
                a,b,c,e=box;ax.add_patch(plt.Rectangle((a,b),c-a,e-b,fill=False,color='cyan' if kind=='PRODUCT' else 'red',linewidth=1.5))
            ax.set_title(title+f'\n{s["image_size"][1]} x {s["image_size"][0]} px')
        fig.suptitle(f'ANNOTATION CHECK (not predictions) | n=1 | {r.category} {r.view} {r.status}\n{image_id} | {r.product_bbox_source} | {r.mask_status}',fontsize=10)
        for ax in axes:ax.set_xlabel('x (pixel)');ax.set_ylabel('y (pixel)')
        fig.tight_layout();path=folder/f'coordinate_case_{i:02}.png'
        if path.exists():raise FileExistsError(path)
        fig.savefig(path,dpi=120);plt.close(fig);files.append(path.name)
    return files
