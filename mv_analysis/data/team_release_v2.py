"""v2: 이상탐지 승인 Crop / D1·D2 원본 전체. 기존 좌표·원장·로더는 보존한다."""
from pathlib import Path
from datetime import datetime, timezone
import json
import numpy as np
import pandas as pd
import torch

from .team_release import (TeamRelease, ReleasedSingleViewDataset, read_tables, eligibility_row,
                          validate_tables, verify_release, save_json, write_checksums, pack_release)
from .manifest import file_hash

RELEASE_V2 = 'MV_TEAM_DATA_RELEASE_v2'
V2_FLAGS = ['anomaly_train_eligible', 'anomaly_image_eval_eligible', 'anomaly_pixel_eval_eligible',
            'detection_defect_train_eligible', 'detection_defect_eval_eligible',
            'detection_product_train_eligible', 'detection_product_eval_eligible',
            'detection_joint_train_eligible', 'detection_joint_eval_eligible',
            'product_gt_diagnostic_eligible', 'detection_joint_diagnostic_eligible']


def eligibility_v2(row):
    """제품 Pseudo 학습, 결함 학습, 독립 평가를 분리한다. D2의 미주석 NG 전체 음성 학습을 막는다."""
    cropped = dict(row, annotation_status=row['crop_annotation_status'])
    result = eligibility_row(cropped)
    valid = bool(row['image_valid']) and bool(row['target_geometry_valid'])
    annotated = row['annotation_status'] in ('OK_NEGATIVE', 'SUPERVISED_VALID')
    supervised = valid and annotated
    train, evaluation = row['split'] == 'train', row['split'] in ('validation', 'test')
    product = valid and row['product_bbox_source'] in ('HUMAN_VERIFIED_GT','AUTOMATIC_PROPOSAL','CROP_APPROXIMATION')
    diagnostic = product and evaluation and row['product_bbox_source'] == 'HUMAN_VERIFIED_GT'
    # 기존 600 GT는 Crop 개발에 사용됐다. 독립 최종 제품 평가 적격으로 자동 승격하지 않는다.
    result.update(detection_train_eligible=supervised and train, detection_eval_eligible=supervised and evaluation,
                  detection_trainable=supervised,
                  detection_defect_train_eligible=supervised and train,
                  detection_defect_eval_eligible=supervised and evaluation,
                  detection_product_train_eligible=product and train,
                  detection_product_eval_eligible=False,
                  detection_joint_train_eligible=product and supervised and train,
                  detection_joint_eval_eligible=False,
                  product_gt_diagnostic_eligible=diagnostic,
                  detection_joint_diagnostic_eligible=diagnostic and supervised,
                  exclusion_reason='' if supervised else row['annotation_status'],
                  product_eval_exclusion_reason='DEVELOPMENT_GT_NOT_INDEPENDENT' if row['product_bbox_source']=='HUMAN_VERIFIED_GT' else 'PSEUDO_LABEL_NOT_EVALUATION_GT',
                  anomaly_exclusion_reason=eligibility_row(cropped)['exclusion_reason'])
    return result


def class_map_v2(old, categories):
    """기존 결함 ID 0..N-1은 고정. 새 제품 ID만 명시적 사전순 카테고리 목록으로 추가한다."""
    mapping = json.loads(json.dumps(old))
    products = {f'product_{name}': i for i,name in enumerate(sorted(categories))}
    d2 = {f'defect_{name}': i for name,i in old['yolo'].items()}
    d2.update({name:i+len(old['yolo']) for name,i in products.items()})
    mapping.update(product_categories={'yolo':products,'coco':{k:v+1 for k,v in products.items()}},
                   D1={'yolo':{f'defect_{k}':v for k,v in old['yolo'].items()}, 'coco':{f'defect_{k}':v for k,v in old['coco'].items()}},
                   D2={'yolo':d2,'coco':{k:v+1 for k,v in d2.items()}},
                   product_id_policy='New categories sorted; existing defect IDs preserved; image OK/NG separate')
    return mapping


def validate_v2(root):
    """v1 좌표/참조 검증을 재사용하고 v2 정책·제품 우선순위·클래스 공간을 추가 검사한다."""
    result = validate_tables(root, eligibility_calculator=eligibility_v2)
    d,e,b,p,c = read_tables(root)
    for key,value in [('anomaly_image_policy','approved_crop'),('detection_image_policy','original_full'),
                      ('annotation_coordinate_space','ORIGINAL_XYXY_EXCLUSIVE'),('release_version',RELEASE_V2)]:
        if not d[key].eq(value).all():raise ValueError('Invalid v2 policy: '+key)
    if c != class_map_v2({k:c[k] for k in c if k not in ['product_categories','D1','D2','product_id_policy']},d.category.unique()):
        raise ValueError('v2 class IDs conflict')
    selected = p[p.selected_for_d2]
    if selected.image_id.duplicated().any() or set(selected.image_id)!=set(d.image_id):
        raise ValueError('D2 must select exactly one provenance-tracked product proposal per image')
    if not p.human_verified.eq(p.source_type.eq('HUMAN_VERIFIED_GT')).all():
        raise ValueError('Pseudo product falsely human verified')
    quality = p.source_type.map({'HUMAN_VERIFIED_GT':'HUMAN_VERIFIED_DEVELOPMENT_GT',
                                'AUTOMATIC_PROPOSAL':'PSEUDO_AUTOMATIC_UNVERIFIED',
                                'CROP_APPROXIMATION':'PSEUDO_CROP_WITH_BACKGROUND'})
    if not p.annotation_quality.eq(quality).all() or not p.coordinate_space.eq('ORIGINAL_XYXY_EXCLUSIVE').all():
        raise ValueError('Invalid product annotation provenance/coordinates')
    priorities={'HUMAN_VERIFIED_GT':0,'AUTOMATIC_PROPOSAL':1,'CROP_APPROXIMATION':2}
    best=p.assign(priority=p.source_type.map(priorities)).sort_values('priority').drop_duplicates('image_id').set_index('image_id')
    if not selected.set_index('image_id').source_type.sort_index().equals(best.source_type.sort_index()):
        raise ValueError('D2 source-priority mismatch')
    if not d.image_id.map(selected.set_index('image_id').source_type).eq(d.product_bbox_source).all():
        raise ValueError('Selected product source differs from canonical')
    proxy=p[p.source_type.eq('CROP_APPROXIMATION')]
    crop=d.set_index('image_id').loc[proxy.image_id,['crop_x0','crop_y0','crop_x1','crop_y1']].to_numpy()
    if not np.array_equal(crop,proxy[['x0','y0','x1','y1']].to_numpy()):raise ValueError('Crop proxy differs from saved crop')
    result.update(release_version=RELEASE_V2, eligibility={k:int(e[k].sum()) for k in V2_FLAGS},
                  selected_product_sources=selected.source_type.value_counts().to_dict(),
                  detection_input='ORIGINAL_FULL', anomaly_input='APPROVED_CROP',
                  product_independent_evaluation='UNVERIFIED_NO_UNUSED_PRODUCT_GT')
    return result


class TeamReleaseV2(TeamRelease):
    """v1와 같은 저장물을 읽되 입력 정책을 명시한다. Detection에서 승인 Crop을 실행하지 않는다."""
    def __init__(self, root, data_root):
        if json.loads((Path(root)/'release.json').read_text()).get('release_id')!=RELEASE_V2:
            raise ValueError('TeamReleaseV2 requires a v2 package')
        super().__init__(root,data_root)
        self.selected_products=self.products[self.products.selected_for_d2].set_index('image_id')

    def dataset(self, *, task, split=None, image_policy=None, annotation_policy=None, adapter=None,
                image_ids=None, eligible_only=False, allow_pseudo_products=True, evaluation_mode='independent'):
        """D2는 명시적으로 선택하며, 독립 평가와 개발 GT 진단용 조회를 분리한다."""
        if task not in ('anomaly','detection'):raise ValueError('Explicit anomaly/detection task required for v2')
        expected='approved_crop' if task=='anomaly' else 'original_full'
        image_policy=image_policy or expected
        annotation_policy=annotation_policy or 'defect_only'
        if image_policy!=expected:raise ValueError('Task/image policy mismatch; detection must use original_full')
        if annotation_policy not in ('defect_only','product_and_defect') or (task=='anomaly' and annotation_policy!='defect_only'):
            raise ValueError('Unsupported annotation policy')
        if evaluation_mode not in ('independent','diagnostic'):raise ValueError('Unknown evaluation mode')
        d=self.canonical
        if split is not None:
            if split not in ('train','validation','test'):raise ValueError('Unknown split')
            d=d[d.split.eq(split)]
        if image_ids is not None:
            if not set(image_ids)<=set(self.canonical.image_id):raise ValueError('Unknown image ID')
            d=d[d.image_id.isin(image_ids)]
        if eligible_only:
            if split is None:raise ValueError('Specify split for eligibility filtering')
            if task=='anomaly':key='anomaly_train_eligible' if split=='train' else 'anomaly_image_eval_eligible'
            elif annotation_policy=='defect_only':key='detection_defect_train_eligible' if split=='train' else 'detection_defect_eval_eligible'
            else:key='detection_joint_train_eligible' if split=='train' else ('detection_joint_diagnostic_eligible' if evaluation_mode=='diagnostic' else 'detection_joint_eval_eligible')
            d=d[d.image_id.map(self.eligible_by_id[key]).eq(True)]
        if annotation_policy=='product_and_defect' and not allow_pseudo_products:
            d=d[d.product_bbox_source.eq('HUMAN_VERIFIED_GT')]
        index=self.index(d.image_id)
        if task=='detection':
            # 승인 CSV는 그대로 두고, 기존 기하 로더에 전달하는 메모리 행만 전체 프레임으로 설정한다.
            for name,value in [('crop_x0',0),('crop_y0',0),('crop_x1',index.data.original_width),
                               ('crop_y1',index.data.original_height),('crop_width',index.data.original_width),
                               ('crop_height',index.data.original_height),('full_frame',True),('selected_policy','ORIGINAL_FULL')]:
                index.data[name]=value
        return ReleasedDatasetV2(index,release=self,task=task,adapter=adapter,image_policy=image_policy,
                                 annotation_policy=annotation_policy,evaluation_mode=evaluation_mode)


class ReleasedDatasetV2(ReleasedSingleViewDataset):
    """원본 SHA 확인·결함 마스크 검사는 재사용. D2 제품 Target은 모델 Adapter 적용 전에 추가한다."""
    def __init__(self,index,*,release,task,adapter,image_policy,annotation_policy,evaluation_mode):
        super().__init__(index,release=release,task=task,adapter=None)
        self.output_adapter=adapter
        self.image_policy=image_policy;self.annotation_policy=annotation_policy;self.evaluation_mode=evaluation_mode

    def __getitem__(self,item):
        s=super().__getitem__(item)
        row=self.release.by_id.loc[s['image_id']]
        s['metadata'].update(data_release_id=RELEASE_V2,image_policy=self.image_policy,annotation_policy=self.annotation_policy,
                             approved_crop_xyxy=[int(row['crop_'+a]) for a in ('x0','y0','x1','y1')],
                             experiment_group='ANOMALY' if self.task=='anomaly' else ('D1' if self.annotation_policy=='defect_only' else 'D2'),
                             source_annotation_coordinate_space='ORIGINAL_XYXY_EXCLUSIVE',
                             target_coordinate_space='APPROVED_CROP_XYXY_EXCLUSIVE' if self.task=='anomaly' else 'ORIGINAL_XYXY_EXCLUSIVE',
                             evaluation_mode=self.evaluation_mode)
        s['defect_boxes_known']=s['detection_status'] in ('OK_NEGATIVE','SUPERVISED_VALID')
        s['annotation_types']=['DEFECT']*len(s['boxes'])
        if self.annotation_policy=='product_and_defect':
            product=self.release.selected_products.loc[s['image_id']]
            box=torch.tensor([[product[a] for a in ('x0','y0','x1','y1')]],dtype=torch.float32)
            label=self.release.classes['D2']['yolo']['product_'+s['category']]
            s['boxes']=torch.cat([box,s['boxes']])
            s['labels']=torch.cat([torch.tensor([label],dtype=torch.int64),s['labels']])
            s['annotation_types']=['PRODUCT']+s['annotation_types']
            s['metadata'].update(product_bbox_source=product.source_type,product_annotation_quality=product.annotation_quality,
                                 product_human_verified=bool(product.human_verified),product_eval_independent=False,
                                 product_gt_used_for_crop_development=bool(product.human_verified))
            # NG 미주석은 제품 박스가 있어도 결함을 배경으로 학습시키는 일반 검출 Loss에 통과시키지 않는다.
            s['detection_trainable']=bool(s['detection_trainable'] and s['defect_boxes_known'])
            s['detection_defect_status']=s['detection_status']
            if s['detection_trainable']:
                s['detection_status']='SUPERVISED_VALID'
                s['metadata']['detection_status']='SUPERVISED_VALID'
        s['metadata']['eligibility'].update({k:bool(self.release.eligible_by_id.loc[s['image_id'],k]) for k in V2_FLAGS})
        if self.output_adapter:
            s=self.output_adapter(s)
            s['metadata']['target_coordinate_space']='MODEL_INPUT'
        return s


def build_v2(source,output,template):
    """검증된 v1 산출물만 정규화하여 새 v2 생성. JPG/PNG 재분석이나 승인 좌표 변경은 없다."""
    source,output=Path(source),Path(output)
    verified=verify_release(source)
    if json.loads((source/'release.json').read_text()).get('release_id')!='MV_TEAM_DATA_RELEASE_v1':raise ValueError('Expected verified v1 source')
    package=output/RELEASE_V2
    if package.exists() or (output/(RELEASE_V2+'.zip')).exists():raise FileExistsError(package)
    d,e,b,p,c=read_tables(source)
    source_hash=file_hash(source/'manifests/canonical.csv')
    c=class_map_v2(c,d.category.unique())
    p['bbox_source']=p.source_type
    p['annotation_quality']=p.source_type.map({'HUMAN_VERIFIED_GT':'HUMAN_VERIFIED_DEVELOPMENT_GT','AUTOMATIC_PROPOSAL':'PSEUDO_AUTOMATIC_UNVERIFIED','CROP_APPROXIMATION':'PSEUDO_CROP_WITH_BACKGROUND'})
    p['human_verified']=p.is_ground_truth
    p['coordinate_space']='ORIGINAL_XYXY_EXCLUSIVE'
    p['bbox_xyxy']=[json.dumps(list(map(float,x))) for x in p[['x0','y0','x1','y1']].to_numpy()]
    best=p.assign(priority=p.source_type.map({'HUMAN_VERIFIED_GT':0,'AUTOMATIC_PROPOSAL':1,'CROP_APPROXIMATION':2})).sort_values('priority').drop_duplicates('image_id')
    p['selected_for_d2']=p.annotation_id.isin(best.annotation_id)
    p['d2_class_id']=p.category.map(lambda k:c['D2']['yolo']['product_'+k])
    p['independent_evaluation_verified']=False
    b['coordinate_space']='ORIGINAL_XYXY_EXCLUSIVE';b['d1_class_id']=b.class_id;b['d2_class_id']=b.class_id
    d['product_bbox_source']=d.image_id.map(best.set_index('image_id').source_type)
    d['crop_annotation_status']=d.annotation_status
    d['annotation_status']=np.select([d.status.eq('OK')&d.image_valid,d.mask_status.eq('PRESENT_POSITIVE')&d.source_box_count.gt(0)&d.native_bbox_table_match,
                                     d.status.eq('NG')&d.mask_status.eq('MISSING'),d.status.eq('NG')&d.mask_status.eq('PRESENT_EMPTY')],
                                    ['OK_NEGATIVE','SUPERVISED_VALID','MISSING_ANNOTATION','EMPTY_NG_REVIEW'],default='INVALID_TARGET')
    for key,value in [('release_version',RELEASE_V2),('source_manifest_sha256',source_hash),('anomaly_image_policy','approved_crop'),
                      ('detection_image_policy','original_full'),('detection_annotation_policy','EXPLICIT_D1_OR_D2'),('annotation_coordinate_space','ORIGINAL_XYXY_EXCLUSIVE')]:d[key]=value
    e=d[['image_id','product_id','category','view','split','status','mask_status','annotation_status']].copy()
    needed=['image_valid','target_geometry_valid','crop_mask_loss','crop_removed_boxes','annotation_status','crop_annotation_status','split','status','mask_status','product_bbox_source']
    e=pd.concat([e,pd.DataFrame([eligibility_v2(r) for r in d[needed].to_dict('records')])],axis=1)
    for folder in ['manifests','annotations','schemas','validation','checksums']:(package/folder).mkdir(parents=True,exist_ok=False)
    d.to_csv(package/'manifests/canonical.csv',index=False);e.to_csv(package/'manifests/eligibility.csv',index=False)
    b.to_csv(package/'annotations/defect_boxes.csv',index=False);p.to_csv(package/'annotations/product_boxes.csv',index=False)
    save_json(package/'schemas/class_mapping.json',c)
    schema=json.loads((source/'schemas/annotation_schema.json').read_text())
    schema.update(schema_version='mv-team-data-v2',anomaly_image_policy='approved_crop',detection_image_policy='original_full',
                  D1='defect_only original pixels',D2='product_and_defect original pixels; separate product/defect metrics',
                  normal_defect_class=None,product_selection='HUMAN_VERIFIED_GT > AUTOMATIC_PROPOSAL > CROP_APPROXIMATION',
                  d2_unknown_ng_policy='Default joint loss/eval excluded; product-only training would require a separately implemented partial-annotation loss',
                  columns={name:{col:str(t) for col,t in frame.dtypes.items()} for name,frame in [('canonical',d),('eligibility',e),('defect_boxes',b),('product_boxes',p)]})
    save_json(package/'schemas/annotation_schema.json',schema)
    for name,group in [('split',['split']),('category_split',['category','split']),('view_split',['view','split'])]:
        e.groupby(group).agg(images=('image_id','size'),**{k:(k,'sum') for k in V2_FLAGS}).reset_index().to_csv(package/'validation'/(name+'_eligibility.csv'),index=False)
    # 과거 근거는 복사만 하며 승인 원장 자체는 포함하지 않는다.
    for name in ['filename_class_resolution.csv','re_review_43.csv','evaluation_independence_risks.csv']:
        (package/'validation'/name).write_bytes((source/'validation'/name).read_bytes())
    measured=validate_v2(package)
    measured.update(source_v1_validation=verified,source_validation_reused=True,source_masks_reprocessed=False,
                    source_approval_audit=json.loads((source/'validation/validation.json').read_text())['approval_audit'],
                    model_training='NOT_RUN',source_crop_changed=False,split_changed=False)
    save_json(package/'validation/validation.json',measured)
    release=dict(release_id=RELEASE_V2,created_utc=datetime.now(timezone.utc).isoformat(),images=len(d),canonical_sha256=file_hash(package/'manifests/canonical.csv'),
                 source_manifest_sha256=source_hash,source_release_sha256=file_hash(source/'release.json'),
                 distribution='PRIVATE_TEAM_ONLY',anomaly_image_policy='approved_crop',detection_image_policy='original_full',
                 detection_annotation_policy=['defect_only','product_and_defect'],annotation_coordinate_space='ORIGINAL_XYXY_EXCLUSIVE',
                 includes_original_images=False,includes_masks=False,includes_weights=False,includes_approval_ledgers=False,
                 product_evaluation_status='NO_INDEPENDENT_GT; existing 600 human boxes were used in development',
                 requires_new_tools='MV_TEAM_DATA_TOOLS_v2; no Git Commit/Push performed')
    save_json(package/'release.json',release)
    (package/'README_DATA.md').write_text(Path(template).read_text().replace('{{CANONICAL_SHA256}}',release['canonical_sha256']))
    write_checksums(package);archive=pack_release(package,output/(RELEASE_V2+'.zip'))
    save_json(output/'build_result.json',dict(archive=archive,validation=measured))
    return dict(archive=archive,validation=measured)


def export_v2(root,destination,*,split,format,annotation_policy='defect_only',evaluation_mode='independent'):
    """D1/D2 주석을 원본 좌표로 내보낸다. 일반 D2 평가에는 독립 GT가 없어 기본 0행이다."""
    root,destination=Path(root),Path(destination)
    if destination.exists():raise FileExistsError(destination)
    if format not in ('yolo','coco') or split not in ('train','validation','test'):raise ValueError('Invalid export')
    if annotation_policy not in ('defect_only','product_and_defect') or evaluation_mode not in ('independent','diagnostic'):raise ValueError('Invalid annotation/evaluation policy')
    verify_release(root);d,e,b,p,c=read_tables(root)
    joint=annotation_policy=='product_and_defect'
    key=('detection_joint_train_eligible' if split=='train' else ('detection_joint_diagnostic_eligible' if evaluation_mode=='diagnostic' else 'detection_joint_eval_eligible')) if joint else ('detection_defect_train_eligible' if split=='train' else 'detection_defect_eval_eligible')
    selected=d[d.split.eq(split)].merge(e[['image_id',key,'exclusion_reason','product_eval_exclusion_reason']],on='image_id',validate='one_to_one')
    allowed=selected[selected[key]]
    destination.mkdir(parents=True);selected[~selected[key]].to_csv(destination/'excluded.csv',index=False)
    if format=='yolo':(destination/'labels').mkdir()
    groups={k:g.to_dict('records') for k,g in b.groupby('image_id')}
    products=p[p.selected_for_d2].set_index('image_id').to_dict('index')
    images,annotations,quality=[],[],[]
    for number,r in enumerate(allowed.to_dict('records'),1):
        objects=[dict(bbox=[v[a] for a in ('x0','y0','x1','y1')],class_id=v['class_id'],annotation_type='DEFECT',bbox_source='PROVIDED_MASK_8CC',human_verified=False,annotation_quality='DATASET_PIXEL_ANNOTATION') for v in groups.get(r['image_id'],[])]
        if joint:
            q=products[r['image_id']]
            objects.insert(0,dict(bbox=[q[a] for a in ('x0','y0','x1','y1')],class_id=q['d2_class_id'],annotation_type='PRODUCT',bbox_source=q['source_type'],human_verified=q['human_verified'],annotation_quality=q['annotation_quality']))
        lines=[]
        for obj in objects:
            x0,y0,x1,y1=obj['bbox'];w,h=r['original_width'],r['original_height']
            xywh=[(x0+x1)/2/w,(y0+y1)/2/h,(x1-x0)/w,(y1-y0)/h]
            if not all(0<=v<=1 for v in xywh) or min(xywh[2:])<=0:raise ValueError('Invalid original normalized box')
            lines.append(str(int(obj['class_id']))+' '+' '.join(f'{v:.12g}' for v in xywh))
            annotations.append(dict(id=len(annotations)+1,image_id=number,category_id=int(obj['class_id'])+1,bbox=[x0,y0,x1-x0,y1-y0],
                                    area=(x1-x0)*(y1-y0),iscrowd=0,**{k:v for k,v in obj.items() if k not in ('bbox','class_id')}))
        if format=='yolo':(destination/'labels'/(r['image_id']+'.txt')).write_text('\n'.join(lines)+('\n' if lines else ''))
        images.append(dict(id=number,image_id=r['image_id'],file_name=r['image_path'],width=r['original_width'],height=r['original_height']))
        quality.append(dict(image_id=r['image_id'],original_path=r['image_path'],objects=objects,image_status=r['status'],coordinate_space='ORIGINAL_XYXY_EXCLUSIVE'))
    if format=='coco':
        save_json(destination/'instances.json',dict(info={'coordinate_space':'ORIGINAL_XYXY_EXCLUSIVE','image_policy':'original_full','experiment':'D2' if joint else 'D1','product_independent_eval':False},images=images,annotations=annotations,categories=[dict(id=v,name=k) for k,v in c['D2' if joint else 'D1']['coco'].items()]))
    with (destination/'annotation_provenance.jsonl').open('w') as f:
        for q in quality:f.write(json.dumps(q,ensure_ascii=False,allow_nan=False)+'\n')
    result=dict(images=len(allowed),objects=len(annotations),excluded=len(selected)-len(allowed),format=format,split=split,
                image_policy='original_full',annotation_policy=annotation_policy,coordinate_space='ORIGINAL_XYXY_EXCLUSIVE',
                evaluation_mode=evaluation_mode,product_independent_evaluation=False,images_written=False)
    save_json(destination/'export.json',result)
    return result
