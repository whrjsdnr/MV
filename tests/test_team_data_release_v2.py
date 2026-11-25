"""v1 유지 + v2 이상탐지/원본 D1/D2 계약 검증. 합성 원본만 사용한다."""
import json
import pandas as pd
import numpy as np
import pytest
import torch
from test_team_data_release import release_data
from mv_analysis.data.team_release import TeamRelease, write_checksums, save_json, verify_release, extract_release
from mv_analysis.data.team_release_v2 import TeamReleaseV2, build_v2, export_v2
from mv_analysis.data.adapters import get_adapter, cxcywh_to_xyxy
from mv_analysis.data.datasets import FiveViewDataset
from mv_analysis.data.collate import five_view_collate, detection_collate
from mv_analysis.experiments.geometry import restore_boxes, restore_map


@pytest.fixture
def v2_data(release_data,tmp_path):
    """임시 v1의 검증 근거를 보완한 후 동일 build-v2 경로로 35장 패키지를 만든다."""
    root,raw,d=release_data
    r=json.loads((root/'release.json').read_text());r['release_id']='MV_TEAM_DATA_RELEASE_v1';save_json(root/'release.json',r)
    save_json(root/'validation/validation.json',{'approval_audit':{'synthetic':True}})
    for name in ['filename_class_resolution.csv','re_review_43.csv','evaluation_independence_risks.csv']:
        pd.DataFrame(columns=['image_id']).to_csv(root/'validation'/name,index=False)
    (root/'checksums/SHA256SUMS').unlink()  # 이 fixture의 임시 산출물만 다시 서명한다.
    write_checksums(root)
    template=tmp_path/'template.md';template.write_text('SYNTHETIC {{CANONICAL_SHA256}}')
    result=build_v2(root,tmp_path/'v2',template)
    new=tmp_path/'v2/MV_TEAM_DATA_RELEASE_v2'
    return new,raw,d,root,result


def test_v2_zip_and_v1_preserved(v2_data,tmp_path):
    root,raw,d,old,result=v2_data
    assert verify_release(old)['images']==35
    assert len(TeamRelease(old,raw).dataset())==35
    restored=extract_release(result['archive']['path'],tmp_path/'extracted',result['archive']['sha256'])
    assert verify_release(restored)['detection_input']=='ORIGINAL_FULL'
    with pytest.raises(ValueError,match='v2 requires'):TeamRelease(root,raw)


def test_anomaly_keeps_crop_and_mask(v2_data):
    root,raw,d,_,_=v2_data;r=TeamReleaseV2(root,raw)
    row=d[d.product_id.eq('sample/positive_eval/S1')].iloc[0]
    s=r.dataset(task='anomaly',image_ids=[row.image_id])[0]
    assert s['image'].shape==(3,56,56) and s['mask'].shape==(1,56,56)
    assert s['crop_xyxy']==(4,4,60,60)
    assert s['metadata']['source_annotation_coordinate_space']=='ORIGINAL_XYXY_EXCLUSIVE'
    assert s['metadata']['target_coordinate_space']=='APPROVED_CROP_XYXY_EXCLUSIVE'
    assert int(s['mask'].sum())==17
    values,observed=restore_map(s['mask'][0].float().numpy(),original_hw=(64,64),crop_xyxy=s['crop_xyxy'],input_hw=(56,56),categorical=True)
    assert values.shape==(64,64) and values[10,10] and values[20,30]
    assert not observed[0,0] and observed[4,4]


def test_d1_original_boxes_and_ok_empty(v2_data):
    root,raw,d,_,_=v2_data;r=TeamReleaseV2(root,raw)
    pos=d[d.product_id.eq('sample/positive/S1')].iloc[0]
    s=r.dataset(task='detection',image_ids=[pos.image_id])[0]
    assert s['image'].shape==(3,64,64) and s['crop_xyxy']==(0,0,64,64)
    assert s['metadata']['target_coordinate_space']=='ORIGINAL_XYXY_EXCLUSIVE'
    assert s['boxes'].tolist()==[[10.,10.,11.,11.],[30.,20.,34.,24.]]
    ok=r.dataset(task='detection',image_ids=[d.iloc[0].image_id])[0]
    assert ok['status']=='OK' and ok['boxes'].shape==(0,4)
    # 원래 Crop으로 완전히 잘리는 성분도 D1 원본 입력에서는 보존된다.
    cut=d[d.product_id.eq('sample/removed/S1')].iloc[0]
    full=r.dataset(task='detection',image_ids=[cut.image_id])[0]
    assert full['detection_trainable'] and full['boxes'].tolist()==[[1.,1.,2.,2.]]


def test_d2_product_and_defect_ids_provenance(v2_data):
    root,raw,d,_,_=v2_data;r=TeamReleaseV2(root,raw)
    ok=r.dataset(task='detection',annotation_policy='product_and_defect',image_ids=[d.iloc[0].image_id])[0]
    assert ok['status']=='OK' and ok['annotation_types']==['PRODUCT']
    assert ok['boxes'].tolist()==[[8.,8.,50.,50.]]
    assert ok['labels'].tolist()==[1] and ok['metadata']['product_human_verified']
    row=d[d.product_id.eq('sample/positive/S1')].iloc[0]
    s=r.dataset(task='detection',annotation_policy='product_and_defect',image_ids=[row.image_id])[0]
    assert s['labels'].tolist()==[1,0,0] and s['boxes'][0].tolist()==[4,4,60,60]
    assert s['metadata']['product_bbox_source']=='CROP_APPROXIMATION'
    assert not s['metadata']['product_human_verified'] and not s['metadata']['product_eval_independent']


def test_unknown_ng_never_joint_negative(v2_data):
    root,raw,d,_,_=v2_data;r=TeamReleaseV2(root,raw)
    row=d[d.product_id.eq('sample/missing/S1')].iloc[0]
    s=r.dataset(task='detection',annotation_policy='product_and_defect',image_ids=[row.image_id])[0]
    assert s['status']=='NG' and len(s['boxes'])==1 and not s['defect_boxes_known']
    assert not s['detection_trainable']
    with pytest.raises(ValueError):detection_collate([s])
    assert len(r.dataset(task='detection',split='train',annotation_policy='product_and_defect',eligible_only=True))==10


def test_product_pseudo_train_not_independent_eval(v2_data):
    root,raw,d,_,_=v2_data;r=TeamReleaseV2(root,raw)
    assert r.eligibility.detection_product_train_eligible.sum()==15
    assert r.eligibility.detection_joint_train_eligible.sum()==10
    assert not r.eligibility.detection_product_eval_eligible.any()
    assert len(r.dataset(task='detection',split='test',annotation_policy='product_and_defect',eligible_only=True))==0
    assert len(r.dataset(task='detection',annotation_policy='product_and_defect',allow_pseudo_products=False))==1


@pytest.mark.parametrize('task,policy',[('detection','approved_crop'),('anomaly','original_full')])
def test_wrong_input_policy_rejected(v2_data,task,policy):
    root,raw,*_=v2_data
    with pytest.raises(ValueError,match='policy'):TeamReleaseV2(root,raw).dataset(task=task,image_policy=policy)


@pytest.mark.parametrize('name',['YOLO11','Faster R-CNN','RT-DETRv2','YOLOS','ViTDet','RetinaNet'])
def test_detector_adapter_original_coordinate_roundtrip(v2_data,name):
    root,raw,d,*_=v2_data;r=TeamReleaseV2(root,raw)
    row=d[d.product_id.eq('sample/positive/S1')].iloc[0]
    native=r.dataset(task='detection',annotation_policy='product_and_defect',image_ids=[row.image_id])[0]
    out=get_adapter(name)(native);m=out['metadata']
    boxes,keep,_=restore_boxes(out['boxes'].numpy(),original_hw=out['original_size'],crop_xyxy=out['crop_xyxy'],input_hw=out['image_size'],scale_xy=m['resize_scale_xy'],padding_lrtb=m['padding_lrtb'],box_format=m['boxes_format'],normalized=m['boxes_normalized'])
    np.testing.assert_allclose(boxes,native['boxes'].numpy(),atol=1e-4)
    assert keep.all() and out['mask'].shape[-2:]==out['image'].shape[-2:]
    assert out['metadata']['image_policy']=='original_full'
    assert out['metadata']['source_annotation_coordinate_space']=='ORIGINAL_XYXY_EXCLUSIVE'


def test_d2_five_view_batch(v2_data):
    root,raw,*_=v2_data;r=TeamReleaseV2(root,raw)
    ds=r.dataset(task='detection',annotation_policy='product_and_defect',adapter=get_adapter('YOLO11'))
    five=FiveViewDataset(ds);batch=five_view_collate([five[0],five[1]])
    assert batch['images'].shape==(2,5,3,640,640)
    assert batch['views'][0]==['C1','C2','C3','C4','C5']


def test_original_yolo_coco_exports(v2_data,tmp_path):
    root,raw,d,*_=v2_data
    a=export_v2(root,tmp_path/'yolo',split='train',format='yolo')
    b=export_v2(root,tmp_path/'coco',split='train',format='coco',annotation_policy='product_and_defect')
    assert a['images']==b['images']==10 and a['objects']==10 and b['objects']==20
    assert (tmp_path/'yolo/labels'/(d.iloc[0].image_id+'.txt')).read_text()==''
    coco=json.loads((tmp_path/'coco/instances.json').read_text())
    assert all(i['width']==64 and not i['file_name'].startswith('virtual_crops') for i in coco['images'])
    assert {x['category_id'] for x in coco['annotations']}=={1,2}
    assert {x['annotation_type'] for x in coco['annotations']}=={'PRODUCT','DEFECT'}
