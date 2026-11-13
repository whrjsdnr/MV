"""팀 배포 계약의 합성 회귀 검사. 실제 승인 원장이나 원본 데이터에는 쓰지 않는다."""
import hashlib
import json
import os
from pathlib import Path
import zipfile

import cv2
import numpy as np
import pandas as pd
import pytest
import torch

from mv_analysis.data.manifest import file_hash
from mv_analysis.data.release_builder import audit_image, product_annotations, BOX_COLUMNS
from mv_analysis.data.team_release import (RELEASE_ID, TeamRelease, eligibility_row, save_json,
    validate_tables, write_checksums, verify_release, pack_release, extract_release, export_targets, torchvision_target)
from mv_analysis.data.datasets import FiveViewDataset
from mv_analysis.data.adapters import get_adapter
from mv_analysis.data.collate import five_view_collate, detection_collate


@pytest.fixture
def release_data(tmp_path):
    """모든 상태를 포함한 35장/7제품. 1픽셀 성분과 부분·완전 잘림을 포함한다."""
    torch.set_num_threads(1)
    root, raw = tmp_path/RELEASE_ID, tmp_path/'raw'
    for folder in ['manifests', 'annotations', 'schemas', 'validation', 'checksums']:
        (root/folder).mkdir(parents=True)
    rows, boxes = [], []
    classes = {'yolo': {'QS': 0}, 'coco': {'QS': 1}, 'classification': {'OK': 0, 'NG': 1}}
    for kind, split in [('ok', 'train'), ('positive', 'train'), ('missing', 'train'),
                        ('empty', 'validation'), ('partial', 'test'), ('removed', 'test'), ('positive_eval', 'test')]:
        status = 'OK' if kind == 'ok' else 'NG'
        product = 'sample/'+kind+'/S1'
        for view in ['C1', 'C2', 'C3', 'C4', 'C5']:
            relative = product+'/'+view+'.jpg'
            path = raw/relative;path.parent.mkdir(parents=True, exist_ok=True)
            assert cv2.imwrite(str(path), np.full((64,64,3), 150, np.uint8))
            s = path.stat();has_mask = kind not in ('ok', 'missing')
            mask_path = relative[:-4]+'.png' if has_mask else ''
            m = np.zeros((64,64), np.uint8)
            if kind in ('positive', 'positive_eval'):m[20:24,30:34]=255;m[10,10]=1
            if kind == 'partial':m[2:8,10:13]=32
            if kind == 'removed':m[1,1]=255
            if has_mask:assert cv2.imwrite(str(raw/mask_path), m)
            _, _, stats, _ = cv2.connectedComponentsWithStats((m>0).astype(np.uint8), connectivity=8)
            old = [[x,y,x+w,y+h] for x,y,w,h,_ in stats[1:]]
            row = dict(image_id=hashlib.sha256(relative.encode()).hexdigest()[:16], product_id=product,
                       category='sample', view=view, split=split, image_path=relative, source_relative_path=relative,
                       original_path=relative, original_width=64, original_height=64, crop_x0=4,crop_y0=4,crop_x1=60,crop_y1=60,
                       crop_width=56,crop_height=56, full_frame=False, selected_policy='HUMAN_CROP',
                       coordinate_format='XYXY_EXCLUSIVE_ORIGINAL_PIXELS', policy_version='synthetic-v1', policy_sha256='synthetic',
                       source_fingerprint=f'stat-v1:{s.st_size}:{s.st_mtime_ns}', additional_center_crop_allowed=False,
                       status=status, defect_type='OK' if status=='OK' else 'QS', defect_class='' if status=='OK' else 'QS',
                       has_mask=has_mask,mask_path=mask_path,crop_review_status='SYNTHETIC_ONLY',
                       manual_annotation_assisted=False, requires_evaluation_leakage_review=False)
            previous = dict(image_decoded=True, source_fingerprint_match=True, source_sha256=file_hash(path))
            audited = audit_image((row, previous, old, [0]*len(old), raw, classes['yolo']))
            assert audited['image_valid']
            boxes.extend(json.loads(audited.pop('component_boxes')))
            rows.append({**row, **audited})
    d = pd.DataFrame(rows)
    e = pd.DataFrame([dict(image_id=r['image_id'], **eligibility_row(r)) for r in rows])
    gt = [dict(image_path=d.iloc[0].image_path, bbox=[8,8,50,50])]
    proposals = pd.DataFrame([dict(image_path=d.iloc[0].image_path,proposal_bbox='[7,7,51,51]',proposal_method='SYNTHETIC')])
    products = product_annotations(d, gt, proposals)
    d.to_csv(root/'manifests/canonical.csv', index=False)
    e.to_csv(root/'manifests/eligibility.csv', index=False)
    pd.DataFrame(boxes, columns=BOX_COLUMNS).to_csv(root/'annotations/defect_boxes.csv', index=False)
    products.to_csv(root/'annotations/product_boxes.csv', index=False)
    save_json(root/'schemas/class_mapping.json', classes)
    save_json(root/'schemas/annotation_schema.json', {'synthetic':True})
    save_json(root/'validation/validation.json', {'synthetic':True})
    save_json(root/'release.json', {'images':len(d), 'canonical_sha256':file_hash(root/'manifests/canonical.csv')})
    (root/'README_DATA.md').write_text('SYNTHETIC test package')
    write_checksums(root)
    return root, raw, d


def test_release_zip_roundtrip_and_hashes(release_data, tmp_path):
    root, _, _ = release_data
    result = pack_release(root, tmp_path/'team.zip')
    extracted = extract_release(result['path'], tmp_path/'unpacked', result['sha256'])
    v = verify_release(extracted)
    assert v['images']==35 and v['products']==7 and v['defect_boxes']==30
    with zipfile.ZipFile(result['path']) as z:
        assert z.testzip() is None and not any(n.endswith(('.jpg','.png','.pt','.jsonl')) for n in z.namelist())


def test_checksum_tamper_rejected(release_data):
    root, _, _ = release_data
    (root/'README_DATA.md').write_text('changed')
    with pytest.raises(ValueError, match='Checksum'):verify_release(root)


def test_archive_external_hash_mismatch(release_data, tmp_path):
    root, _, _ = release_data
    z = tmp_path/'team.zip';pack_release(root,z)
    with pytest.raises(ValueError, match='SHA-256'):extract_release(z,tmp_path/'out','0'*64)


@pytest.mark.parametrize('name', ['../escape', '/absolute', RELEASE_ID+'/../escape', 'C:/file', RELEASE_ID+'\\file'])
def test_zip_path_escape_rejected(tmp_path, name):
    z = tmp_path/'unsafe.zip'
    with zipfile.ZipFile(z,'w') as f:f.writestr(name,'bad')
    with pytest.raises(ValueError):extract_release(z,tmp_path/'out')


def test_no_overwrite_of_release_or_export(release_data,tmp_path):
    root, _, _ = release_data
    z=tmp_path/'a.zip';pack_release(root,z)
    with pytest.raises(FileExistsError):pack_release(root,z)
    with pytest.raises(FileExistsError):extract_release(z,tmp_path)
    with pytest.raises(FileExistsError):export_targets(root,tmp_path,split='train',format='yolo')


def test_ng_missing_empty_and_loss_eligibility(release_data):
    root, raw, _ = release_data
    release = TeamRelease(root,raw)
    def take(kind):return release.canonical[release.canonical.product_id.eq('sample/'+kind+'/S1')].iloc[0]
    for kind in ['missing','empty','partial','removed']:
        r=take(kind);e=release.eligible_by_id.loc[r.image_id]
        assert not e.detection_trainable
        assert r.status=='NG'
    assert release.eligible_by_id.loc[take('empty').image_id].anomaly_image_eval_eligible
    assert not release.eligible_by_id.loc[take('empty').image_id].anomaly_pixel_eval_eligible
    assert release.eligible_by_id.loc[take('positive_eval').image_id].anomaly_pixel_eval_eligible
    assert len(release.dataset(split='train', task='anomaly', eligible_only=True))==5
    assert len(release.dataset(split='train', task='detection', eligible_only=True))==10


def test_small_component_and_crop_transform(release_data):
    root, raw, _ = release_data
    r=TeamRelease(root,raw)
    boxes=r.boxes[r.boxes.image_path.str.contains('/positive/')]
    tiny=boxes[boxes.component_area.eq(1)].iloc[0]
    assert [tiny.crop_bbox_x0,tiny.crop_bbox_y0,tiny.crop_bbox_x1,tiny.crop_bbox_y1]==[6,6,7,7]
    partial=r.canonical[r.canonical.product_id.str.contains('/partial/')]
    assert partial.original_positive_pixels.eq(18).all() and partial.cropped_positive_pixels.eq(12).all()
    assert partial.crop_mask_loss.all()


def test_ok_empty_yolo_and_coco_ng_exclusions(release_data,tmp_path):
    root, raw, _ = release_data
    r=TeamRelease(root,raw)
    y,c=tmp_path/'yolo',tmp_path/'coco'
    assert export_targets(root,y,split='train',format='yolo')==dict(images=10,objects=10,excluded=5)
    export_targets(root,c,split='train',format='coco')
    ok=r.canonical[r.canonical.status.eq('OK')].iloc[0]
    assert (y/'labels'/(ok.image_id+'.txt')).read_text()==''
    coco=json.loads((c/'instances.json').read_text())
    assert coco['info']['images_are_virtual_crops']
    assert all(a['category_id']==1 for a in coco['annotations'])
    for p in (y/'labels').glob('*.txt'):
        for line in p.read_text().splitlines():
            values=list(map(float,line.split()));assert values[0]==0 and all(0<=v<=1 for v in values[1:])
    assert not list(y.rglob('*.jpg'))


def test_torchvision_labels_and_empty_shape(release_data):
    root,raw,d=release_data;r=TeamRelease(root,raw)
    ok=d[d.status.eq('OK')].iloc[0]
    assert torchvision_target(r,ok.image_id)['boxes'].shape==(0,4)
    pos=d[d.product_id.eq('sample/positive/S1')].iloc[0]
    t=torchvision_target(r,pos.image_id);assert t['labels'].tolist()==[1,1]
    missing=d[d.product_id.eq('sample/missing/S1')].iloc[0]
    with pytest.raises(ValueError):torchvision_target(r,missing.image_id)


def test_product_provenance_not_default_defect_target(release_data):
    root,_,_=release_data
    p=pd.read_csv(root/'annotations/product_boxes.csv')
    assert p.source_type.value_counts().to_dict()==dict(CROP_APPROXIMATION=35,HUMAN_VERIFIED_GT=1,AUTOMATIC_PROPOSAL=1)
    assert not p.default_detection_target.any() and p.is_ground_truth.sum()==1
    p.loc[p.source_type.eq('CROP_APPROXIMATION'),'is_ground_truth']=True
    p.to_csv(root/'annotations/product_boxes.csv',index=False)
    with pytest.raises(ValueError,match='GT'):validate_tables(root)


@pytest.mark.parametrize('change', ['duplicate','split','coordinate','class','approval'])
def test_semantic_corruption_rejected(release_data,change):
    root,_,_=release_data
    path=root/'manifests/canonical.csv';d=pd.read_csv(path,keep_default_na=False)
    if change=='duplicate':d.loc[1,'image_id']=d.loc[0,'image_id']
    if change=='split':d.loc[0,'split']='test'
    if change=='coordinate':d.loc[0,'crop_x1']=65
    if change=='class':d.loc[5,'defect_class']='unknown'
    if change=='approval':d.loc[0,'crop_x0']=5;d.loc[0,'crop_width']=55
    d.to_csv(path,index=False)
    # 승인된 좌표의 배포 해시가 달라지면 로더는 자동 보정 없이 거부한다.
    with pytest.raises(ValueError):verify_release(root)
    if change!='approval':
        with pytest.raises(ValueError):validate_tables(root)


def test_copied_files_with_changed_mtime_load_and_content_tamper_fails(release_data):
    root,raw,d=release_data;r=TeamRelease(root,raw)
    row=d.iloc[0];p=raw/row.image_path;s=p.stat();os.utime(p,ns=(s.st_atime_ns,s.st_mtime_ns+10000000))
    ds=r.dataset(image_ids=[row.image_id]);sample=ds[0]
    assert sample['image'].shape==(3,56,56) and sample['metadata']['content_hash_checked']
    assert file_hash(root/'manifests/canonical.csv')==r.sha256
    p.write_bytes(b'changed original')
    with pytest.raises(ValueError,match='SHA-256'):ds[0]


def test_single_five_view_loader_and_collate(release_data):
    root,raw,d=release_data;r=TeamRelease(root,raw)
    native=r.dataset();missing=native[10]
    assert missing['status']=='NG' and missing['mask'] is None and not missing['detection_trainable']
    with pytest.raises(ValueError):detection_collate([missing])
    assert not native[20]['detection_trainable']  # 부분 주석 손실은 새 배포 계약에서 제외한다.
    ds=r.dataset(adapter=get_adapter('EfficientAD-S'))
    five=FiveViewDataset(ds);batch=five_view_collate([five[0],five[1]])
    assert batch['images'].shape==(2,5,3,256,256)
    assert batch['views'][0]==['C1','C2','C3','C4','C5']
    assert batch['metadata'][0]['manifest_sha256']==r.sha256


def test_current_bad_mask_is_invalid_not_missing(release_data):
    _,raw,d=release_data;row=d.iloc[5].to_dict();(raw/row['mask_path']).write_bytes(b'bad mask')
    prior=dict(image_decoded=True,source_fingerprint_match=True,source_sha256=row['source_sha256'])
    out=audit_image((row,prior,[],[],raw,{'QS':0}))
    assert out['mask_status']=='INVALID' and out['annotation_status']=='INVALID_TARGET'
    assert str(raw) not in json.dumps(out)
