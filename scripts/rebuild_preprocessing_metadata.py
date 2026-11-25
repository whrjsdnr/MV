"""Crop 원장·v2 배포·YOLO·Quality Gate를 읽기 전용 대조하여 새 전처리 CSV를 만든다.

전수 자동 특징이 없는 이미지는 NOT_COMPUTED로 남긴다. 저장된 제안을 전수 실행으로 과장하지 않는다.
기존 CSV/릴리스/원장/모델 학습 설정은 변경하지 않는다.
"""
from pathlib import Path
import argparse
import collections
import csv
import hashlib
import json
import math
import os
import sys
import sqlite3
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from mv_analysis.crop_reconstruction import COORDS, VERSION, checked_crop, latest_reviews, reconstruct_row

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'outputs/adaptive_crop_full_v1'
CANONICAL=ROOT/'outputs/team_data_release_v2/MV_TEAM_DATA_RELEASE_v2/manifests/canonical.csv'


class FeatureIndex:
    """전수 특징의 큰 중첩 dict는 RAM 대신 새 출력의 SQLite 인덱스에 저장한다."""
    def __init__(self,path):
        self.db=sqlite3.connect(path)
        self.db.execute('CREATE TABLE features (path TEXT PRIMARY KEY, record TEXT NOT NULL)')
    def add(self,record):
        self.db.execute('INSERT INTO features VALUES (?,?)',(record['image_path'],json.dumps(record,allow_nan=False)))
    def __contains__(self,path):
        return self.db.execute('SELECT 1 FROM features WHERE path=?',(path,)).fetchone() is not None
    def __getitem__(self,path):
        return json.loads(self.db.execute('SELECT record FROM features WHERE path=?',(path,)).fetchone()[0])
    def __len__(self):
        return self.db.execute('SELECT COUNT(*) FROM features').fetchone()[0]
    def items(self):
        for path,record in self.db.execute('SELECT path,record FROM features'):
            yield path,json.loads(record)


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def rows(path):
    with Path(path).open(newline='') as stream:
        yield from csv.DictReader(stream)


def jsonlines(path):
    with Path(path).open() as stream:
        for line in stream:
            if line.strip():yield json.loads(line,parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))


def write_json(path,data):
    with path.open('x') as stream:json.dump(data,stream,ensure_ascii=False,indent=2,allow_nan=False)


def frozen_auto(feature,thresholds,policy,category,view,*,use_frozen=True):
    """이전 min_side/proxy 규칙을 그대로 적용한다. GT나 이미지 상태는 인수에 없다."""
    from mv_analysis.adaptive_crop_gate import decide,contains,CENTER,FULL
    gate=decide(feature,thresholds,category,view)
    selected,crop=gate['research_selected_policy'],gate['research_selected_crop']
    candidate=policy['research_candidate']
    if use_frozen and selected=='A' and (feature['crop_side']<candidate['min_side'] or
        (candidate['require_proxy_containment'] and not all(contains(crop,b,8) for b in feature['other_boxes'].values()))):
        selected='B' if gate['center896_image_check'] else 'C'
        crop=CENTER if selected=='B' else FULL
    return dict(policy=selected,crop=crop,gate_status=gate['image_quality_status'],risk_codes=gate['image_risk_codes'])


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--data-root',type=Path,default=ROOT/'dataset')
    p.add_argument('--apply-auto',action='store_true',help='사람 승인 우선 + 자동 선택을 새 최종 CSV에 반영. 위험은 별도 검수로 분리')
    p.add_argument('--rule',choices=['frozen','image_gate'],default='frozen',help='image_gate는 기존 A/B/C 이미지 규칙을 적용한 별도 검수용 정책')
    p.add_argument('--review-overlay',nargs=2,action='append',default=[],metavar=('LEDGER','BASE_CSV'),
                   help='새 검수 화면에서 저장한 별도 원장과 해당 화면 기준 CSV. 자동 좌표를 승인으로 취급하지 않음')
    p.add_argument('--reference-overrides',type=Path,help='사용자가 기존 하늘색 제품 박스를 사용하도록 확인한 별도 정책 기록(JSON)')
    p.add_argument('--additional-features',nargs='+',type=Path,default=[],
                   help='compute_missing_crop_features.py가 생성한 디렉터리. 기존 캐시와 합쳐 새 출력 생성')
    args=p.parse_args();out=args.output.resolve()
    args.additional_features=[directory.resolve() for directory in args.additional_features]
    out.mkdir(parents=True,exist_ok=False)
    inputs=[CANONICAL,BASE/'preprocessing_metadata.csv',BASE/'preprocessing_metadata_reviewed_v2.csv',
            BASE/'manual_crop_review_ledger.jsonl',BASE/'policy.json',
            ROOT/'outputs/adaptive_crop_gate_v1/checkpoints/features.jsonl',
            ROOT/'outputs/adaptive_crop_gate_v1/thresholds.json',
            ROOT/'outputs/yolo11_dynamic_crop_v1/inference_checkpoint.jsonl',
            ROOT/'outputs/object_aware_crop_v1/review/human_approved_gt.jsonl']
    for directory in args.additional_features:
        inputs.extend([directory/'config.json',directory/'features.jsonl'])
    for ledger,base_csv in args.review_overlay:inputs.extend([Path(ledger).resolve(),Path(base_csv).resolve()])
    if args.reference_overrides:inputs.append(args.reference_overrides.resolve())
    before={str(path.relative_to(ROOT)):sha(path) for path in inputs}
    events=list(jsonlines(BASE/'manual_crop_review_ledger.jsonl'))
    reviews=latest_reviews(events,sha(BASE/'preprocessing_metadata.csv'))
    reference_overrides=json.loads(args.reference_overrides.read_text())['overrides'] if args.reference_overrides else {}
    for ledger,base_csv in args.review_overlay:
        overlay_events=list(jsonlines(ledger))
        overlay=latest_reviews(overlay_events,sha(base_csv))
        for path,event in overlay.items():
            if path not in reviews or event['reviewed_utc']>=reviews[path]['reviewed_utc']:reviews[path]=event
        events.extend(overlay_events)
    reviewed={r['image_id']:r for r in rows(BASE/'preprocessing_metadata_reviewed_v2.csv') if r['crop_review_status']=='APPROVED_CROP'}
    features=FeatureIndex(out/'feature_index.sqlite')
    for record in jsonlines(inputs[5]):features.add(record)
    original_cache_count=len(features)
    feature_errors=[]
    for directory in args.additional_features:
        config=json.loads((directory/'config.json').read_text())
        if (config['source_manifest_sha256']!=before[str(CANONICAL.relative_to(ROOT))]
                or config['existing_cache_sha256']!=sha(inputs[5])
                or config['feature_extractor_sha256']!=sha(ROOT/'mv_analysis/adaptive_crop_gate.py')
                or config['object_helper_sha256']!=sha(ROOT/'mv_analysis/object_aware_crop.py')
                or config['segmentation_sha256']!=sha(ROOT/'mv_analysis/background_brightness.py')
                or Path(config['data_root']).resolve()!=args.data_root.resolve()):
            raise ValueError('Additional feature cache bindings mismatch')
        for record in jsonlines(directory/'features.jsonl'):
            if record['image_path'] in features:raise ValueError('Duplicate additional feature cache image')
            if record.get('error') or record.get('features') is None:
                feature_errors.append(record['image_path'])
            else:features.add(record)
    features.db.commit()
    feature_error_paths=set(feature_errors)
    detections={r['image_path']:r for r in jsonlines(inputs[7])}
    thresholds=json.loads(inputs[6].read_text());policy=json.loads(inputs[4].read_text())
    # 쓰기 전 사용되는 표본 파일들의 실제 바이트 해시를 확인한다. 동일 경로도 내용이 다르면 캐시 제외.
    verified={};source_errors=[]
    expected={path:{r.get('source_sha256')} for path,r in reviews.items()}
    for path,r in features.items():
        # 신규 작업자가 디코딩 시 저장한 SHA와 stat를 연결한다. 기존 캐시는 바이트 해시를 재확인한다.
        if r.get('source_fingerprint'):
            stat=(args.data_root/path).stat()
            if r['source_fingerprint']!=f'stat-v1:{stat.st_size}:{stat.st_mtime_ns}':
                source_errors.append(dict(image_path=path,error='NEW_FEATURE_SOURCE_STAT_CHANGED'))
        else:expected.setdefault(path,set()).add(r['source_hash'])
    for path,hashes in expected.items():
        try:
            actual=sha(args.data_root/path)
            verified[path]=actual
            if any(value and value!=actual for value in hashes):source_errors.append(dict(image_path=path,error='SOURCE_HASH_MISMATCH'))
        except OSError as exc:source_errors.append(dict(image_path=path,error=repr(exc)))
    if source_errors:
        write_json(out/'source_errors.json',source_errors)
        raise ValueError('Source identity mismatch: original records preserved')
    counts=collections.Counter();auto_counts=collections.Counter();groups={};ids=set();paths=set();approvals_seen=set()
    selection_rows=[];yolo_rows=[];changed_rows=[];manual_errors=[];reviewed_reference_differences=[];exists_fail=[];summary_category=collections.Counter();summary_view=collections.Counter()
    coordnames=['auto_candidate_x0','auto_candidate_y0','auto_candidate_x1','auto_candidate_y1']
    handles={};writers={}
    try:
        for i,base in enumerate(rows(CANONICAL)):
            image_id=base['image_id'];path=base['source_relative_path']
            if image_id in ids or path in paths:raise ValueError('Duplicate canonical image')
            ids.add(image_id);paths.add(path)
            if not (args.data_root/path).is_file():exists_fail.append(path)
            full=[0,0,int(base['original_width']),int(base['original_height'])]
            old=checked_crop([int(base[k]) for k in COORDS],full[2],full[3])
            # 원본/기준 좌표와 제품/Split은 그대로 연결한다. 상태/마스크는 Gate 함수에 전달하지 않는다.
            event=reviews.get(path);auto=None
            if path in features:
                if int(base['original_width'])!=1024 or int(base['original_height'])!=1024:
                    raise ValueError('Cached feature extractor requires original 1024x1024')
                auto=frozen_auto(features[path]['features'],thresholds,policy,base['category'],base['view'],use_frozen=args.rule=='frozen')
            layouts=([('preprocessing_metadata_final.csv',True),('preprocessing_metadata_human_only_baseline.csv',False)] if args.apply_auto else
                     [('preprocessing_metadata_final.csv',False),('preprocessing_metadata_cached_adaptive_candidate.csv',True)])
            for name,allow in layouts:
                row=reconstruct_row(base,event,auto,allow_cached_auto=allow,
                    reference_override=reference_overrides.get(path) if allow else None)
                row['selection_rule']=args.rule
                row['automatic_crop_authorized_for_review']=args.apply_auto
                if path in feature_error_paths:
                    row['automatic_feature_status']='COMPUTE_ERROR'
                    row['processing_status']='ERROR_FEATURE_FULL_FRAME' if not row['approved_crop_present'] else 'HUMAN_APPROVED_FEATURE_ERROR_RECORDED'
                    if not row['approved_crop_present']:row['fallback_reason']='FEATURE_COMPUTE_ERROR_FULL_FRAME'
                row['policy_version']=VERSION+'+'+args.rule+('+auto-review' if args.apply_auto else '+human-only')
                row['source_canonical_sha256']=before[str(CANONICAL.relative_to(ROOT))]
                row['reconstruction_policy_sha256']=hashlib.sha256(json.dumps(dict(source_policy=policy,
                    rule=args.rule,apply_auto=args.apply_auto),sort_keys=True).encode()).hexdigest()
                # 기존 Canonical의 Crop 후 감사값을 새 자동 후보에 그대로 복사하지 않는다.
                if row['crop_changed_from_input']:
                    for col in ['crop_clipped_boxes','crop_removed_boxes','cropped_positive_pixels','crop_mask_loss','crop_annotation_status']:
                        row[col]=''
                    row['crop_target_audit_status']='REQUIRES_NEW_AUDIT'
                else:row['crop_target_audit_status']='UNCHANGED_REUSED_V2_AUDIT'
                if name not in writers:
                    handle=(out/name).open('x',newline='');handles[name]=handle
                    writer=csv.DictWriter(handle,fieldnames=list(row));writer.writeheader();writers[name]=writer
                writers[name].writerow(row)
                if allow:
                    auto_counts[row['selected_policy']]+=1
                    if row['crop_changed_from_input']:changed_rows.append({k:row[k] for k in ['image_id','source_relative_path',*COORDS,'selected_policy','split','category','view','mask_path']})
                else:
                    counts[row['selected_policy']]+=1;summary_category[(row['category'],row['selected_policy'])]+=1;summary_view[(row['view'],row['selected_policy'])]+=1
                    if event and event['status']=='APPROVED_CROP':
                        approvals_seen.add(path)
                        if [row[k] for k in COORDS]!=event['crop_xyxy']:manual_errors.append(path)
                        previous=reviewed.get(image_id)
                        if previous is None or [int(previous[k]) for k in COORDS]!=event['crop_xyxy']:reviewed_reference_differences.append(path)
            g=groups.setdefault(base['product_id'],dict(split=base['split'],views=[]))
            if g['split']!=base['split'] or base['view'] in g['views']:raise ValueError('Product group leakage/duplicate view')
            g['views'].append(base['view'])
            if auto:
                selection_rows.append(dict(image_id=image_id,image_path=path,category=base['category'],view=base['view'],
                    automatic_policy=auto['policy'],automatic_crop=json.dumps(auto['crop']),gate_status=auto['gate_status'],
                    risk_codes=json.dumps(auto['risk_codes']),human_crop_approval=bool(event and event['status']=='APPROVED_CROP'),
                    product_preservation='UNVERIFIED_OUTSIDE_REVIEWED_PRODUCT_GT',candidate_only=True))
            if path in detections:
                from mv_analysis.yolo_crop_geometry import select_box,square_crop
                det=detections[path]
                # YOLO 캐시의 size/mtime도 확인하고 원본이 바뀐 검출은 사용하지 않는다.
                stat=(args.data_root/path).stat()
                valid=stat.st_size==det['input_bytes'] and stat.st_mtime_ns==det['input_mtime_ns']
                box,status=select_box(det['detections'],'confidence',full[2],full[3]) if valid else (None,'STALE_SOURCE')
                crop=square_crop(box,.3,full[2],full[3]) if box else None
                yolo_rows.append(dict(image_id=image_id,image_path=path,detection_count=len(det['detections']),
                    yolo_status=status,source_matches=valid,bbox=json.dumps(box),crop_margin30=json.dumps(crop),
                    application='PROPOSAL_ONLY_NOT_VERIFIED_PRODUCT',manual_priority=bool(event and event['status']=='APPROVED_CROP')))
            if i%25000==0:print('reconstructed',i,flush=True)
    finally:
        for handle in handles.values():handle.close()
    if exists_fail or manual_errors:raise ValueError('Source missing or approval mismatch')
    if set(reviews)-paths:raise ValueError('Review image missing from canonical')
    if len(approvals_seen)!=sum(e['status']=='APPROVED_CROP' for e in reviews.values()):raise ValueError('Approval coverage mismatch')
    if any(sorted(g['views'])!=['C1','C2','C3','C4','C5'] for g in groups.values()):raise ValueError('Incomplete views')
    def table(name,records,fields=None):
        with (out/name).open('x',newline='') as stream:
            writer=csv.DictWriter(stream,fieldnames=fields or list(records[0]));writer.writeheader();writer.writerows(records)
    table('cached_adaptive_candidates.csv',selection_rows)
    table('yolo_crop_candidates.csv',yolo_rows)
    table('automatic_candidate_changes.csv',changed_rows,['image_id','source_relative_path',*COORDS,'selected_policy','split','category','view','mask_path'])
    # 별도 CSV는 전체 미계산 이미지도 포함한다. 확정 손실과 미평가를 구분한다.
    queue=[]
    for row in rows(out/'preprocessing_metadata_final.csv'):
        if row['crop_review_status']!='APPROVED_CROP':
            queue.append({k:row[k] for k in ['image_id','source_relative_path','category','view','split',*COORDS,*coordnames,'auto_candidate_policy','automatic_feature_status','crop_review_status']})
    table('manual_review_or_uncomputed_images.csv',queue)
    table('summary_by_category.csv',[dict(category=c,selected_policy=p,images=n) for (c,p),n in sorted(summary_category.items())])
    after={str(path.relative_to(ROOT)):sha(path) for path in inputs}
    if before!=after:raise ValueError('Protected input changed during reconstruction')
    result=dict(status='VERIFIED_COORDINATES_AWAITING_MANUAL_RISK_REVIEW' if len(selection_rows)==len(ids) else 'PARTIAL_AUTOMATIC_FEATURES_COORDINATES_COMPLETE',images=len(ids),products=len(groups),
        canonical_source_sha256=before[str(CANONICAL.relative_to(ROOT))],human_history_events=len(events),
        latest_review_items=len(reviews),human_crop_approvals=len(approvals_seen),approval_mismatches=manual_errors,
        previous_reviewed_csv_differences=reviewed_reference_differences,
        final_policy_counts=dict(auto_counts if args.apply_auto else counts),human_only_policy_counts=dict(counts),cached_candidate_policy_counts=dict(auto_counts),
        cached_gate_images=len(selection_rows),uncomputed_gate_images=len(ids)-len(selection_rows),
        yolo_cached_images=len(yolo_rows),new_yolo_inference=0,new_grabcut_images=0,
        additional_feature_images=len(features)-original_cache_count,additional_feature_errors=feature_errors,
        changed_cached_candidate_images=len(changed_rows),missing_sources=exists_fail,
        product_group_errors=0,coordinate_errors=0,protected_inputs_unchanged=before==after,
        protected_input_sha256=before,manual_review_or_uncomputed_images=len(queue),
        entire_dataset_adaptive_crop='FEATURES_COMPLETE' if len(selection_rows)==len(ids) else 'PARTIAL_FEATURES',
        candidate_auto_application='USER_AUTHORIZED_APPLIED_WITH_MANUAL_REVIEW' if args.apply_auto else 'NOT_APPLIED_TO_FINAL',
        existing_release_modified=False,training_configs_modified=False,
        output_sha256={p.name:sha(p) for p in out.glob('*.csv')})
    write_json(out/'validation.json',result)
    write_json(out/'policy.json',dict(version=VERSION,human_priority=True,
        final_csv='preprocessing_metadata_final.csv',
        baseline_csv='preprocessing_metadata_human_only_baseline.csv' if args.apply_auto else 'preprocessing_metadata_cached_adaptive_candidate.csv',
        auto_rule=args.rule,automatic_application=args.apply_auto,
        yolo='existing detections retained as proposals; no COCO box is assumed to be verified product',
        masks='not used for selection; changed candidate masks require separate audit',
        full_execution_estimate_hours_serial=35.9,default_auto_application=False))
    print(json.dumps({k:v for k,v in result.items() if k not in ('protected_input_sha256','output_sha256')},ensure_ascii=False),flush=True)


if __name__=='__main__':main()
