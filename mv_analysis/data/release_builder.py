"""승인 원장을 읽기 전용으로 대조하고 v2 데이터 계약을 별도 경로에 고정한다."""
from pathlib import Path
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import inspect
import json
import os
import time

import cv2
import numpy as np
import pandas as pd

from .manifest import file_hash, geometry_errors, group_audit
from .targets import read_mask, crop_targets
from .team_release import RELEASE_ID, ELIGIBILITY, relative_path, eligibility_row, save_json, validate_tables, write_checksums, pack_release

BOX_COLUMNS = ['bbox_id', 'image_id', 'image_path', 'product_id', 'category', 'view', 'split',
               'defect_type', 'class_id', 'component_id', 'component_area', 'x0', 'y0', 'x1', 'y1',
               'crop_bbox_x0', 'crop_bbox_y0', 'crop_bbox_x1', 'crop_bbox_y1', 'kept_after_crop', 'clipped', 'annotation_type']


def load_events(path):
    """중복 승인은 지우지 않고 최신 이벤트를 선택한다. 비표준 JSON은 거부한다."""
    def reject(value):
        raise ValueError('Nonstandard ledger JSON: '+value)
    events = [json.loads(line, parse_constant=reject) for line in Path(path).read_text().splitlines() if line.strip()]
    latest = {}
    for event in events:
        if not event.get('reviewed_utc'):
            raise ValueError('Missing review timestamp')
        datetime.fromisoformat(event['reviewed_utc'].replace('Z', '+00:00'))
        previous = latest.get(event['image_path'])
        if previous and event['reviewed_utc'] < previous['reviewed_utc']:
            raise ValueError('Review history out of timestamp order')
        latest[event['image_path']] = event
    return events, latest


def approval_audit(base, v1, final, crop_events, product_events, proposals, data_root, changed_expected):
    """43장·1,594개 최신 Crop 승인·600개 제품 GT를 각각 대조한다. GT를 Crop 승인으로 쓰지 않는다."""
    for d in (base, v1, final):
        if len(geometry_errors(d)):
            raise ValueError('Invalid source crop geometry')
        group_audit(d, True)
    base, v1, final = [d.set_index('image_id', drop=False).sort_index() for d in (base, v1, final)]
    keys = ['image_id', 'product_id', 'category', 'view', 'split', 'source_relative_path', 'original_width', 'original_height']
    if not base[keys].equals(final[keys]) or not v1[keys].equals(final[keys]):
        raise ValueError('Source identities or split changed')
    coordinates = ['crop_x0', 'crop_y0', 'crop_x1', 'crop_y1']
    changed = set(final.index[(final[coordinates] != v1[coordinates]).any(axis=1)])
    if changed != set(changed_expected) or len(changed) != 43:
        raise ValueError('Final CSV does not match the documented 43-image re-review')
    by_path = final.set_index('source_relative_path', drop=False)
    latest = {e['image_path']: e for e in crop_events}
    approved = {path: e for path, e in latest.items() if e['status'] == 'APPROVED_CROP'}
    if set(final.loc[final.crop_review_status.eq('APPROVED_CROP'), 'source_relative_path']) != set(approved):
        raise ValueError('CSV manual approvals and ledger IDs differ')
    base_hashes = {e['base_manifest_sha256'] for e in crop_events}
    if len(base_hashes) != 1:
        raise ValueError('Crop ledger mixes base manifests')
    verified_bytes = {}
    def check_source(path, expected):
        if path not in verified_bytes:
            verified_bytes[path] = file_hash(Path(data_root)/relative_path(path))
        if verified_bytes[path] != expected:
            raise ValueError('Approval image SHA mismatch: '+path)
    for path, event in approved.items():
        r = by_path.loc[path]
        if event['case_id'] != r.image_id or not event.get('human_ack') or len(str(event.get('reviewer', '')).strip()) < 2:
            raise ValueError('Invalid explicit crop approval')
        if event.get('not_product_gt') is not True or event['source_fingerprint'] != r.source_fingerprint:
            raise ValueError('Crop approval source contract mismatch')
        if r[coordinates].tolist() != event['crop_xyxy'] or r.crop_reviewed_utc != event['reviewed_utc'] or r.crop_reviewer != event['reviewer']:
            raise ValueError('Approved crop was not exported exactly')
        revision = hashlib.sha256(json.dumps(event, ensure_ascii=False, allow_nan=False).encode()).hexdigest()
        expected_policy = hashlib.sha256((str(base.loc[r.image_id, 'policy_sha256'])+revision).encode()).hexdigest()
        if r.policy_sha256 != expected_policy:
            raise ValueError('Approval policy revision mismatch')
        check_source(path, event['source_sha256'])
    untouched = ~final.source_relative_path.isin(approved)
    if not final.loc[untouched, coordinates].equals(base.loc[untouched, coordinates]):
        raise ValueError('Unapproved crop modification')
    proposal = proposals.set_index('image_path')
    gt = {e['image_path']: e for e in product_events}
    for path, event in gt.items():
        if event['status'] != 'VERIFIED_GT' or event.get('human_ack') is not True or len(str(event.get('reviewer', '')).strip()) < 2:
            raise ValueError('Invalid product GT approval')
        if path not in proposal.index or event['case_id'] != proposal.loc[path, 'case_id']:
            raise ValueError('Product approval not in review proposals')
        box = np.asarray(event['bbox'], dtype=float)
        row = by_path.loc[path]
        if box.shape != (4,) or not np.isfinite(box).all() or (box[:2] < 0).any() or (box[2:] <= box[:2]).any() or box[2] > row.original_width or box[3] > row.original_height:
            raise ValueError('Invalid approved product box')
        check_source(path, event['source_sha256'])
    return dict(latest_crop_approvals=len(approved), crop_ledger_events=len(crop_events),
                pending_crop_reviews=sum(e['status'] == 'PENDING' for e in latest.values()),
                product_gt=len(gt), product_gt_events=len(product_events), re_review_changed_images=len(changed),
                re_review_image_ids=sorted(changed), approval_sources_content_verified=len(verified_bytes),
                unapproved_coordinate_changes=0, evaluation_independence='NOT_GUARANTEED_ANNOTATION_ASSISTED_CROPS_RECORDED')


def audit_image(args):
    """JPG 검증 캐시를 조건부 재사용하고, 제공된 PNG는 모두 다시 읽어 8연결 성분을 확인한다."""
    row, previous, old_boxes, old_labels, data_root, class_map = args
    out = dict(image_id=row['image_id'], image_valid=False, target_geometry_valid=True,
               image_verification='', image_error='', mask_status='MISSING', mask_sha256='',
               source_sha256=previous.get('source_sha256', ''), source_bytes=0, mask_bytes=0,
               annotation_status='INVALID_TARGET', source_box_count=0, crop_clipped_boxes=0,
               crop_removed_boxes=0, original_positive_pixels=0, cropped_positive_pixels=0,
               crop_mask_loss=False, native_bbox_table_match=True, component_boxes='[]')
    try:
        path = Path(data_root)/relative_path(row['source_relative_path'])
        current = path.stat()
        out['source_bytes'] = current.st_size
        fingerprint = f'stat-v1:{current.st_size}:{current.st_mtime_ns}'
        cache_ok = bool(previous.get('image_decoded')) and previous.get('source_fingerprint_match') is True and fingerprint == row['source_fingerprint']
        if cache_ok:
            out['image_verification'] = 'REUSED_PRIOR_FULL_DECODE_AND_SHA_WITH_CURRENT_STAT_MATCH'
        else:
            data = path.read_bytes()
            digest = hashlib.sha256(data).hexdigest()
            im = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
            if digest != out['source_sha256'] or im is None or im.shape[:2] != (row['original_height'], row['original_width']):
                raise ValueError('Image content or decoding differs from canonical source')
            out['image_verification'] = 'CURRENT_CONTENT_SHA_AND_FULL_DECODE'
        out['image_valid'] = True
        mask = None
        if row['has_mask']:
            mp = Path(data_root)/relative_path(row['mask_path'])
            before = mp.stat()
            mask, state, error = read_mask(mp, (row['original_height'], row['original_width']))
            out.update(mask_status=state, mask_error=error.split(':')[0] if error else '', mask_sha256=file_hash(mp), mask_bytes=before.st_size)
            after = mp.stat()
            if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                raise ValueError('Mask changed while validating')
        else:
            state, error = 'MISSING', ''
        generated, labels, components = [], [], []
        if mask is not None:
            _, _, statistics, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), connectivity=8)
            for component_id, (x, y, w, h, area) in enumerate(statistics[1:], 1):
                generated.append([int(x), int(y), int(x+w), int(y+h)])
                labels.append(class_map[row['defect_type']] if row['status'] == 'NG' else -1)
                components.append((component_id, int(area)))
        native = Counter((tuple(map(float, b)), int(c)) for b, c in zip(old_boxes, old_labels))
        actual = Counter((tuple(map(float, b)), int(c)) for b, c in zip(generated, labels))
        out['native_bbox_table_match'] = native == actual
        t = crop_targets(row, generated, labels, mask, state, error)
        for name in ('source_box_count', 'crop_clipped_boxes', 'crop_removed_boxes', 'original_positive_pixels', 'cropped_positive_pixels', 'crop_mask_loss'):
            out[name] = t[name] if t[name] is not None else 0
        out['annotation_status'] = t['detection_status'] if native == actual else 'INVALID_TARGET'
        bx = []
        x0, y0, x1, y1 = [int(row['crop_'+v]) for v in ('x0', 'y0', 'x1', 'y1')]
        for box, label, (component_id, area) in zip(generated, labels, components):
            local = [max(0, min(x1-x0, box[0]-x0)), max(0, min(y1-y0, box[1]-y0)),
                     max(0, min(x1-x0, box[2]-x0)), max(0, min(y1-y0, box[3]-y0))]
            keep = local[2] > local[0] and local[3] > local[1]
            bx.append(dict(bbox_id=f"{row['image_id']}:cc:{component_id}", image_id=row['image_id'],
                           image_path=row['source_relative_path'], product_id=row['product_id'], category=row['category'],
                           view=row['view'], split=row['split'], defect_type=row['defect_type'], class_id=label,
                           component_id=component_id, component_area=area, **dict(zip(('x0', 'y0', 'x1', 'y1'), box)),
                           **dict(zip(('crop_bbox_x0', 'crop_bbox_y0', 'crop_bbox_x1', 'crop_bbox_y1'), local)),
                           kept_after_crop=keep, clipped=local != [box[0]-x0, box[1]-y0, box[2]-x0, box[3]-y0], annotation_type='DEFECT'))
        out['component_boxes'] = json.dumps(bx)
    except Exception as exc:
        # 개인 절대 경로가 예외 문자열에 들어갈 수 있으므로 배포용 오류에는 유형만 기록한다.
        out['image_error'] = type(exc).__name__
        out['image_valid'] = False
        out['annotation_status'] = 'INVALID_TARGET'
    return out


def product_annotations(d, gt_events, proposals):
    """제품 GT·자동 제안·Crop 근사치를 별도 출처로 모두 유지하고 기본 검출에서는 사용하지 않는다."""
    rows = []
    by_path = d.set_index('image_path')
    def add(row, box, source, status, reference, confidence):
        rows.append(dict(annotation_id=f"{row['image_id']}:{source}", image_id=row['image_id'],
                         product_id=row['product_id'], category=row['category'], view=row['view'], split=row['split'],
                         image_status=row['status'], source_type=source, verification_status=status,
                         is_ground_truth=source == 'HUMAN_VERIFIED_GT', confidence_status=confidence,
                         default_detection_target=False, annotation_type='PRODUCT_REGION' if source != 'CROP_APPROXIMATION' else 'CROP_REGION_PROXY',
                         source_reference=reference, **dict(zip(('x0', 'y0', 'x1', 'y1'), box))))
    for path, event in {e['image_path']: e for e in gt_events}.items():
        add(by_path.loc[path], event['bbox'], 'HUMAN_VERIFIED_GT', 'VERIFIED_GT', 'human_product_review', 'HUMAN_VERIFIED_NOT_PROBABILITY')
    for proposal in proposals.to_dict('records'):
        add(by_path.loc[proposal['image_path']], json.loads(proposal['proposal_bbox']), 'AUTOMATIC_PROPOSAL', 'PROPOSAL', proposal['proposal_method'], 'UNVERIFIED')
    for row in d.to_dict('records'):
        add(row, [row['crop_'+v] for v in ('x0', 'y0', 'x1', 'y1')], 'CROP_APPROXIMATION', 'NOT_PRODUCT_GT', 'saved_crop_coordinates', 'UNVERIFIED')
    return pd.DataFrame(rows)


def build_release(workspace, data_root, output, workers=2, max_batches=None):
    """재개 가능한 PNG 전수 검증 뒤 배포 디렉터리와 ZIP을 새로 만든다. 기존 원장은 수정하지 않는다."""
    workspace, data_root, output = map(lambda p: Path(p).resolve(), (workspace, data_root, output))
    if not 1 <= workers <= 4:
        raise ValueError('Use 1..4 CPU workers')
    package = output/RELEASE_ID
    if package.exists():
        raise FileExistsError('Completed/partial package exists; preserve it and choose a new output directory')
    output.mkdir(parents=True, exist_ok=True)
    work = output/'private_build';work.mkdir(exist_ok=True)
    paths = dict(final=workspace/'outputs/adaptive_crop_full_v1/preprocessing_metadata_reviewed_v2.csv',
                 base=workspace/'outputs/adaptive_crop_full_v1/preprocessing_metadata.csv',
                 prior=workspace/'outputs/adaptive_crop_full_v1/preprocessing_metadata_reviewed_v1.csv',
                 labels=workspace/'outputs/filename_class_resolution_v1/image_metadata_with_split.csv',
                 boxes=workspace/'outputs/filename_class_resolution_v1/defect_bboxes.csv',
                 classes=workspace/'outputs/spatial_20261111_v7/classes.json',
                 crop_ledger=workspace/'outputs/adaptive_crop_full_v1/manual_crop_review_ledger.jsonl',
                 product_ledger=workspace/'outputs/object_aware_crop_v1/review/human_approved_gt.jsonl',
                 proposals=workspace/'outputs/object_aware_crop_v1/review/product_bbox_proposals.csv',
                 previous_decode=workspace/'outputs/data_loader_validation_v1/per_image_decode_validation.csv',
                 previous_decode_config=workspace/'outputs/data_loader_validation_v1/decode_config.json',
                 previous_decode_fingerprint=workspace/'outputs/data_loader_validation_v1/manifest_fingerprint.json',
                 changed=workspace/'outputs/team_collaboration_docs_20261113_v1/reviewed_v2_changed_mask_audit.csv',
                 conflicts=workspace/'outputs/filename_class_resolution_v1/class_resolution_audit.csv',
                 mask_policy=workspace/'outputs/spatial_20261111_v7/mask_policy.json')
    hashes = {k: file_hash(p) for k, p in paths.items()}
    descriptor = json.loads((workspace/'configs/data/canonical_manifest.release.json').read_text())
    for key, name in [('manifest', 'final'), ('annotations', 'labels'), ('bboxes', 'boxes'), ('classes', 'classes')]:
        if hashes[name] != descriptor['files'][key]['sha256']:
            raise ValueError('Source does not match approved release descriptor: '+name)
    mask_policy = json.loads(paths['mask_policy'].read_text())
    if not mask_policy.get('validated') or mask_policy['threshold'] != 0:
        raise ValueError('Existing nonzero mask policy not validated')
    prior_config = json.loads(paths['previous_decode_config'].read_text())
    prior_fp = json.loads(paths['previous_decode_fingerprint'].read_text())
    if prior_config['manifest_sha256'] != hashes['prior'] or prior_fp['manifest_sha256'] != hashes['prior'] or not prior_config['full_jpg_decode']:
        raise ValueError('Prior image decode provenance mismatch')
    worker_hash = hashlib.sha256((inspect.getsource(audit_image)+inspect.getsource(read_mask)+inspect.getsource(crop_targets)).encode()).hexdigest()
    config = dict(source_sha256=hashes, worker_sha256=worker_hash, mask_threshold=0, connectivity=8, min_area_filter=None, data_root=str(data_root))
    cfg = work/'config.json'
    if cfg.exists() and json.loads(cfg.read_text()) != config:
        raise ValueError('Checkpoint configuration differs; use a new output directory')
    if not cfg.exists():save_json(cfg, config)
    read = lambda name: pd.read_csv(paths[name], keep_default_na=False)
    d, base, prior, labels, boxes, proposals = [read(n) for n in ['final', 'base', 'prior', 'labels', 'boxes', 'proposals']]
    classes = json.loads(paths['classes'].read_text())
    crop_events, _ = load_events(paths['crop_ledger']);gt_events, _ = load_events(paths['product_ledger'])
    changed = read('changed');approvals = approval_audit(base, prior, d, crop_events, gt_events, proposals, data_root, changed.image_id)
    if {e['base_manifest_sha256'] for e in crop_events} != {hashes['base']}:
        raise ValueError('Approval ledger base hash mismatch')
    save_json(work/'approval_audit.json', approvals)
    print('Approval audit:', json.dumps({k: v for k, v in approvals.items() if k != 're_review_image_ids'}), flush=True)
    for column in ['product_id', 'category', 'view', 'split']:
        mapped = d.source_relative_path.map(labels.set_index('image_path')[column])
        if not mapped.eq(d[column]).all():raise ValueError('Annotation identity mismatch: '+column)
    if labels.image_path.duplicated().any() or set(labels.image_path) != set(d.source_relative_path):
        raise ValueError('Source annotation IDs mismatch')
    conflicts = read('conflicts');label_index = labels.set_index('image_path')
    if len(conflicts) != 10 or not conflicts.resolved_defect_type.eq('QS').all() or not conflicts.class_id.eq(classes['yolo']['QS']).all():
        raise ValueError('Unexpected filename class-resolution policy')
    for row in conflicts.to_dict('records'):
        if label_index.loc[row['image_path'], 'defect_type'] != row['resolved_defect_type'] or row['filename_defect_type'] != row['resolved_defect_type']:
            raise ValueError('Filename class resolution not applied')
    d = d.merge(labels[['image_path', 'status', 'defect_type', 'has_mask', 'mask_path']], left_on='source_relative_path', right_on='image_path', validate='one_to_one')
    previous = read('previous_decode')
    if previous.image_id.duplicated().any() or set(previous.image_id) != set(d.image_id) or not previous.image_decoded.eq(True).all():
        raise ValueError('Incomplete prior full-JPG decoding evidence')
    prev_by_id = previous.set_index('image_id').to_dict('index')
    old_boxes = {k: (g[['x0', 'y0', 'x1', 'y1']].to_numpy(), g.class_id.to_numpy()) for k, g in boxes.groupby('image_path')}
    del base, prior, labels
    cv2.setNumThreads(1)
    parts = work/'checkpoints';parts.mkdir(exist_ok=True)
    start = time.perf_counter();part_paths = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for first in range(0, len(d), 1000):
            chunk = d.iloc[first:first+1000];dest = parts/f'part_{first//1000:05}.parquet';part_paths.append(dest)
            if dest.exists():
                cached = pd.read_parquet(dest)
                if cached.image_id.tolist() != chunk.image_id.tolist():raise ValueError('Checkpoint IDs mismatch')
            else:
                jobs = []
                for row in chunk.to_dict('records'):
                    b, ids = old_boxes.get(row['image_path'], ([], []))
                    jobs.append((row, prev_by_id[row['image_id']], b, ids, data_root, classes['yolo']))
                cached = pd.DataFrame(pool.map(audit_image, jobs));tmp = dest.with_suffix('.partial')
                cached.to_parquet(tmp, index=False);os.replace(tmp, dest)
            print(f'RELEASE AUDIT {first+len(chunk)}/{len(d)} categories={",".join(chunk.category.unique())} elapsed={time.perf_counter()-start:.1f}s', flush=True)
            if max_batches and len(part_paths) >= max_batches:return None
    audited = pd.concat([pd.read_parquet(p) for p in part_paths], ignore_index=True)
    defect_boxes = pd.DataFrame([b for raw in audited.component_boxes for b in json.loads(raw)], columns=BOX_COLUMNS)
    audited = audited.drop(columns='component_boxes')
    keep = ['image_id', 'product_id', 'category', 'view', 'split', 'image_path', 'source_relative_path',
            'original_width', 'original_height', 'crop_x0', 'crop_y0', 'crop_x1', 'crop_y1', 'crop_width', 'crop_height',
            'selected_policy', 'quality_status', 'crop_review_status', 'full_frame', 'policy_version', 'policy_sha256',
            'source_fingerprint', 'coordinate_format', 'additional_center_crop_allowed', 'status', 'defect_type',
            'has_mask', 'mask_path', 'manual_annotation_assisted', 'requires_evaluation_leakage_review']
    canonical = d[keep].merge(audited, on='image_id', validate='one_to_one')
    canonical['original_path'] = canonical.image_path
    canonical['defect_class'] = canonical.defect_type.where(canonical.status.eq('NG'), '')
    canonical['release_version'] = RELEASE_ID
    canonical['crop_policy'] = canonical.selected_policy
    latest_state = {e['case_id']: e['status'] for e in crop_events}
    canonical['latest_review_state'] = canonical.image_id.map(latest_state).fillna('NO_REVIEW_EVENT')
    eligibility = canonical[['image_id', 'product_id', 'category', 'view', 'split', 'status', 'mask_status', 'annotation_status']].copy()
    flags = pd.DataFrame([eligibility_row(row) for row in canonical.to_dict('records')])
    eligibility = pd.concat([eligibility, flags], axis=1)
    products = product_annotations(canonical, gt_events, proposals)
    for folder in ['manifests', 'annotations', 'schemas', 'validation', 'checksums']:(package/folder).mkdir(parents=True, exist_ok=False)
    canonical.to_csv(package/'manifests/canonical.csv', index=False)
    eligibility.to_csv(package/'manifests/eligibility.csv', index=False)
    defect_boxes.to_csv(package/'annotations/defect_boxes.csv', index=False)
    products.to_csv(package/'annotations/product_boxes.csv', index=False)
    save_json(package/'schemas/class_mapping.json', classes)
    schema = dict(schema_version='mv-team-data-v1', coordinates='XYXY_EXCLUSIVE_ORIGINAL_PIXELS',
                  defect_box_original_columns=['x0', 'y0', 'x1', 'y1'], defect_box_crop_columns=['crop_bbox_x0', 'crop_bbox_y0', 'crop_bbox_x1', 'crop_bbox_y1'],
                  image_status=['OK', 'NG'], mask_status=['PRESENT_POSITIVE', 'PRESENT_EMPTY', 'MISSING', 'INVALID'],
                  category_values=sorted(canonical.category.unique()), normal_defect_class=None,
                  missing_ng_is_negative=False, mask_threshold='grayscale > 0', connectivity=8, component_area_filter=None,
                  product_annotations_default_training=False, product_confidence='CATEGORICAL_PROVENANCE_NOT_NUMERIC_PROBABILITY',
                  columns={name:{col:str(dtype) for col,dtype in frame.dtypes.items()} for name,frame in [('canonical',canonical),('eligibility',eligibility),('defect_boxes',defect_boxes),('product_boxes',products)]})
    save_json(package/'schemas/annotation_schema.json', schema)
    for name, group in [('split', ['split']), ('category_split', ['category', 'split']), ('view_split', ['view', 'split'])]:
        summary = eligibility.groupby(group).agg(images=('image_id', 'size'), **{k:(k, 'sum') for k in ELIGIBILITY}).reset_index()
        summary.to_csv(package/'validation'/(name+'_eligibility.csv'), index=False)
    canonical.groupby(['category', 'status', 'split']).agg(images=('image_id', 'size'), declared_products=('product_id', 'nunique')).reset_index().to_csv(package/'validation/category_status_split.csv', index=False)
    canonical[canonical.requires_evaluation_leakage_review].drop(columns=['source_fingerprint']).to_csv(package/'validation/evaluation_independence_risks.csv', index=False)
    canonical[canonical.image_id.isin(approvals['re_review_image_ids'])][['image_id','crop_x0','crop_y0','crop_x1','crop_y1','original_positive_pixels','cropped_positive_pixels','crop_mask_loss']].to_csv(package/'validation/re_review_43.csv', index=False)
    conflicts.to_csv(package/'validation/filename_class_resolution.csv', index=False)
    measured = validate_tables(package)
    measured.update(approval_audit=approvals, source_class_resolution_images=10,
                    source_bbox_matches=int(canonical.native_bbox_table_match.sum()),
                    jpeg_verification=canonical.image_verification.value_counts().to_dict(),
                    current_png_decodes=int(canonical.has_mask.sum()), errors=int((~canonical.image_valid).sum()),
                    invalid_masks=int(canonical.mask_status.eq('INVALID').sum()),
                    invalid_targets=int(canonical.annotation_status.eq('INVALID_TARGET').sum()),
                    mask_threshold_policy='REUSED_VERIFIED_NONZERO_POLICY', split_recreated=False,
                    source_files_written=False, all_jpegs_decoded_again=False,
                    source_jpeg_cache_limit='Current size+mtime matched prior full decode/content SHA. This is not a fresh full-byte audit. Recipient loader verifies SHA before first use.',
                    test_annotation_assisted_crops=int(canonical.requires_evaluation_leakage_review.sum()),
                    category_conditional_anomaly=True, category_required_for_detection=False,
                    final_model_training='NOT_RUN')
    if any(file_hash(p) != hashes[k] for k,p in paths.items()):raise ValueError('Source changed during build')
    save_json(package/'validation/validation.json', measured)
    payload = dict(release_id=RELEASE_ID, distribution='PRIVATE_TEAM_ONLY_NO_PUBLIC_REDISTRIBUTION',
                   public_redistribution_permission='UNVERIFIED', created_utc=datetime.now(timezone.utc).isoformat(),
                   images=len(canonical), canonical_sha256=file_hash(package/'manifests/canonical.csv'),
                   source_artifacts={k:dict(path=p.relative_to(workspace).as_posix(),sha256=hashes[k]) for k,p in paths.items()},
                   includes_original_images=False, includes_masks=False, includes_weights=False, includes_approval_ledgers=False,
                   reviewers_redacted=True, original_paths_relative=True, approval_records_unchanged=True,
                   mask_policy={'threshold':0,'connectivity':8,'area_filter':None},
                   label_policy='OK is image status, not defect object class. Product boxes are experimental and excluded from default detection.',
                   eligibility_policy='Exclude missing/empty NG and any crop annotation loss from baseline detection; preserve image NG status.',
                   code_requirement='New uncommitted team_release modules and CLI must be distributed/reviewed separately; existing c4b4a46 alone lacks this entry point.')
    save_json(package/'release.json', payload)
    template = workspace/'docs/data/archive/README_DATA_v1.md'
    (package/'README_DATA.md').write_text(template.read_text().replace('{{CANONICAL_SHA256}}',payload['canonical_sha256']))
    write_checksums(package)
    archive = pack_release(package, output/(RELEASE_ID+'.zip'))
    save_json(output/'build_result.json', dict(archive=archive, validation=measured))
    print(json.dumps(dict(archive=archive, images=len(canonical), boxes=len(defect_boxes), eligible=measured['eligibility']), ensure_ascii=False, indent=2), flush=True)
    return package
