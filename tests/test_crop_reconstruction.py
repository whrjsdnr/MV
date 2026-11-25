"""수동 검수와 자동 제안을 혼동하거나 이전 승인을 되살리는 오류를 차단한다."""
import copy
import pytest
from mv_analysis.crop_reconstruction import checked_crop,latest_reviews,reconstruct_row,COORDS


def base():
    return dict(image_id='i',source_relative_path='category/image.jpg',source_fingerprint='stat-v1:1:2',
        split='test',policy_version='old',original_width=1024,original_height=1024,
        crop_x0=0,crop_y0=0,crop_x1=1024,crop_y1=1024)


def approval(crop=None):
    crop=crop or [100,200,900,800]
    return dict(case_id='i',image_path='category/image.jpg',source_fingerprint='stat-v1:1:2',
        base_manifest_sha256='base',status='APPROVED_CROP',crop_xyxy=crop,human_ack=True,
        reviewer='human',reviewed_utc='2026-11-17T00:00:00Z',
        preview_evaluation=dict(crop=crop,annotation_assisted=True,requires_risk_ack=False))


def automatic():
    return dict(crop=[64,64,960,960],policy='B',gate_status='REVIEW',risk_codes=['METHOD_DISAGREEMENT'])


def test_manual_approval_always_overrides_automatic():
    e=approval();a=automatic();r=reconstruct_row(base(),e,a,allow_cached_auto=True)
    assert [r[k] for k in COORDS]==e['crop_xyxy']
    assert r['selected_policy']=='HUMAN_CROP'
    assert r['crop_review_status']=='APPROVED_CROP'
    assert r['requires_evaluation_leakage_review']


def test_confirmed_full_frame_is_not_replaced_by_automatic():
    r=reconstruct_row(base(),approval([0,0,1024,1024]),automatic(),allow_cached_auto=True)
    assert r['full_frame'] and r['selected_policy']=='C'


def test_latest_re_review_coordinates_win():
    first=approval();second=approval([80,90,1000,950])
    latest=latest_reviews([first,second],'base')
    assert latest[first['image_path']]['crop_xyxy']==second['crop_xyxy']


def test_pending_supersedes_old_approval_and_blocks_auto():
    first=approval();pending=dict(first,status='PENDING')
    latest=latest_reviews([first,pending],'base')
    r=reconstruct_row(base(),latest[first['image_path']],automatic(),allow_cached_auto=True)
    assert r['full_frame'] and not r['approved_crop_present']
    assert r['crop_review_status']=='PENDING'


def test_unknown_images_are_not_computed_not_fake_pass():
    r=reconstruct_row(base())
    assert r['automatic_feature_status']=='NOT_COMPUTED'
    assert r['full_frame'] and not r['approved_crop_present']
    assert r['auto_candidate_x0']==''


def test_automatic_candidate_remains_explicitly_unverified():
    r=reconstruct_row(base(),automatic=automatic(),allow_cached_auto=True)
    assert r['selected_policy']=='AUTO_CACHED_B'
    assert r['product_preservation_validation']=='UNVERIFIED_AUTOMATIC_SCOPE'
    assert not r['approved_crop_present']


def test_default_retains_candidate_but_does_not_promote_to_approval():
    r=reconstruct_row(base(),automatic=automatic())
    assert r['full_frame'] and r['auto_candidate_x0']==64
    assert r['crop_review_status']=='UNREVIEWED'


@pytest.mark.parametrize('crop',[[0,0,1025,1024],[1,1,1,20],[0,0,float('nan'),20],[True,0,20,20],[.5,0,20,20]])
def test_invalid_coordinates_not_repaired(crop):
    with pytest.raises(ValueError):checked_crop(crop,1024,1024)


@pytest.mark.parametrize('mutation',[{'human_ack':False},{'reviewer':''},{'base_manifest_sha256':'other'},
    {'preview_evaluation':{'crop':[0,0,1024,1024]}}])
def test_invalid_approval_is_rejected(mutation):
    e=approval();e.update(mutation)
    with pytest.raises(ValueError):latest_reviews([e],'base')


def test_source_binding_not_bypassed():
    e=approval();e['source_fingerprint']='other'
    with pytest.raises(ValueError):reconstruct_row(base(),e)


def test_no_source_data_mutation_and_no_label_based_policy():
    b=base();b.update(status='OK',has_mask=False,defect_type='NORMAL');original=copy.deepcopy(b)
    a=reconstruct_row(b,automatic=automatic(),allow_cached_auto=True)
    assert b==original
    b.update(status='NG',has_mask=True,defect_type='QS')
    c=reconstruct_row(b,automatic=automatic(),allow_cached_auto=True)
    assert [a[k] for k in COORDS]==[c[k] for k in COORDS]


def test_image_gate_application_does_not_silently_keep_old_1024_minimum(monkeypatch):
    from scripts.rebuild_preprocessing_metadata import frozen_auto
    from mv_analysis import adaptive_crop_gate
    monkeypatch.setattr(adaptive_crop_gate,'decide',lambda *a,**k:dict(research_selected_policy='A',
        research_selected_crop=[100,100,900,900],center896_image_check=False,
        image_quality_status='PASS',image_risk_codes=[]))
    f=dict(crop_side=800,other_boxes={})
    policy={'research_candidate':{'min_side':1024,'require_proxy_containment':True}}
    assert frozen_auto(f,{},policy,'cat','C1',use_frozen=True)['policy']=='C'
    assert frozen_auto(f,{},policy,'cat','C1',use_frozen=False)['policy']=='A'


def test_feature_index_duplicate_and_disk_roundtrip(tmp_path):
    import sqlite3
    from scripts.rebuild_preprocessing_metadata import FeatureIndex
    db=FeatureIndex(tmp_path/'features.sqlite');record={'image_path':'a.jpg','features':{'crop_side':800}}
    db.add(record);db.db.commit()
    assert 'a.jpg' in db and len(db)==1 and db['a.jpg']==record
    assert list(db.items())==[('a.jpg',record)]
    with pytest.raises(sqlite3.IntegrityError):db.add(record)


def test_applied_audit_requests_manual_review_without_rewriting_crop(tmp_path,monkeypatch):
    import csv,json,hashlib
    import cv2
    import numpy as np
    from scripts import audit_applied_crop_and_prepare_review as audit
    root=tmp_path/'root';out=tmp_path/'output';raw=tmp_path/'raw';out.mkdir();raw.mkdir()
    gt=root/'outputs/object_aware_crop_v1/review/human_approved_gt.jsonl';gt.parent.mkdir(parents=True)
    gt.write_text(json.dumps(dict(status='VERIFIED_GT',image_path='ng.jpg',bbox=[20,20,900,900]))+'\n')
    boxes=root/'outputs/team_data_release_v2/MV_TEAM_DATA_RELEASE_v2/annotations/defect_boxes.csv';boxes.parent.mkdir(parents=True)
    boxes.write_text('image_id,x0,y0,x1,y1\ni,10,10,20,20\n')
    mask=np.zeros((1024,1024),np.uint8);mask[10:20,10:20]=255;cv2.imwrite(str(raw/'mask.png'),mask)
    row=dict(image_id='i',source_relative_path='ng.jpg',original_path=str(raw/'ng.jpg'),product_id='product',
        category='category',view='C1',split='validation',crop_x0=64,crop_y0=64,crop_x1=960,crop_y1=960,
        original_width=1024,original_height=1024,mask_path='mask.png',original_positive_pixels=100,
        selected_policy='AUTO_CACHED_B',crop_review_status='UNREVIEWED',automatic_feature_status='CACHED_VERIFIED_SOURCE',
        auto_gate_status='REVIEW',policy_version='image-gate-test',source_fingerprint='test',crop_annotation_status='',
        annotation_status='SUPERVISED_VALID')
    source=out/'preprocessing_metadata_final.csv'
    with source.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(row));w.writeheader();w.writerow(row)
    before=source.read_bytes()
    monkeypatch.setattr(audit,'ROOT',root)
    monkeypatch.setattr('sys.argv',['audit','--directory',str(out),'--data-root',str(raw)])
    audit.main()
    assert source.read_bytes()==before
    result=json.loads((out/'post_crop_audit_validation.json').read_text())
    assert result['required_review_images']==1 and result['mask_loss_images']==1 and result['product_gt_loss_images']==1
    with (out/'preprocessing_metadata_applied.csv').open() as f:r=next(csv.DictReader(f))
    assert [int(r[k]) for k in COORDS]==[64,64,960,960]
    assert r['manual_review_required']=='True' and r['crop_annotation_status']=='INVALID_TARGET'
    with (out/'manual_review_required.csv').open() as f:q=next(csv.DictReader(f))
    assert q['base_manifest_sha256']==hashlib.sha256((out/'preprocessing_metadata_applied.csv').read_bytes()).hexdigest()
    assert 'OBSERVED_PRODUCT_GT_BBOX_LOSS' in q['review_reasons']
    applied=(out/'preprocessing_metadata_applied.csv').read_bytes()
    monkeypatch.setattr('sys.argv',['audit','--directory',str(out),'--data-root',str(raw),'--resume'])
    audit.main()
    assert (out/'preprocessing_metadata_applied.csv').read_bytes()==applied
    # 내보내기 도중 중단된 상황: 기존 출력은 삭제 대신 보관하고 체크포인트에서 복구한다.
    receipt=out/'post_crop_audit_validation.json';receipt.rename(out/'receipt_before_interruption.json')
    audit.main()
    assert (out/'preprocessing_metadata_applied.csv').read_bytes()==applied
    assert list(out.glob('incomplete_audit_exports_*'))


def confirmed_reference():
    return dict(image_id='i',image_path='category/image.jpg',source_fingerprint='stat-v1:1:2',
        product_bbox_xyxy=[100,100,900,900],crop_xyxy=[20,20,980,980],
        confirmed_utc='2026-11-17T01:00:00Z',confirmation_source='EXPLICIT_USER_REFERENCE_REUSE')


def test_confirmed_reference_is_not_fabricated_per_image_approval():
    r=reconstruct_row(base(),approval(),reference_override=confirmed_reference())
    assert r['selected_policy']=='USER_REFERENCE_CROP'
    assert r['crop_review_status']=='USER_CONFIRMED_REFERENCE_REUSE'
    assert not r['approved_crop_present'] and r['manual_annotation_assisted']
    assert r['reference_confirmation_source']=='EXPLICIT_USER_REFERENCE_REUSE'
    assert r['requires_evaluation_leakage_review']


def test_later_explicit_crop_edit_overrides_confirmed_reference():
    e=approval();e['reviewed_utc']='2026-11-17T02:00:00Z'
    r=reconstruct_row(base(),e,reference_override=confirmed_reference())
    assert r['selected_policy']=='HUMAN_CROP' and r['approved_crop_present']
    assert [r[k] for k in COORDS]==e['crop_xyxy']
