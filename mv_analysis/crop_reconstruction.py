"""기존 좌표와 사람 승인 이력을 보존하며 배포용 Crop 행을 재구성한다.

자동 제안, 제품 GT, Crop 승인은 서로 다른 증거다. 결함 정답은 좌표 선택에 쓰지 않는다.
이 모듈은 원본 이미지나 승인 원장을 쓰지 않으며 파일 출력은 호출자가 새 경로에 수행한다.
"""
import json
import math

COORDS = ('crop_x0', 'crop_y0', 'crop_x1', 'crop_y1')
VERSION = 'crop-evidence-reconstruction-20261117-v1'


def checked_crop(values, width, height):
    """끝 좌표 exclusive인 원본 정수 좌표만 허용하며 자동 보정하지 않는다."""
    if isinstance(values, str):
        values = json.loads(values)
    if not isinstance(values, (list, tuple)) or len(values) != 4:
        raise ValueError('Expected four coordinates')
    if any(isinstance(x, bool) or not isinstance(x, (int, float)) or
           not math.isfinite(x) or int(x) != x for x in values):
        raise ValueError('Expected finite integer pixel coordinates')
    x0, y0, x1, y1 = map(int, values)
    if not (0 <= x0 < x1 <= width and 0 <= y0 < y1 <= height):
        raise ValueError('Crop outside original image')
    return [x0, y0, x1, y1]


def latest_reviews(events, base_hash):
    """원본 이력 순서가 서버의 최신 판정 기준이다. 승인 후 PENDING이면 과거 승인을 재활용하지 않는다."""
    latest = {}
    for event in events:
        if event['base_manifest_sha256'] != base_hash:
            raise ValueError('Review refers to another base manifest')
        if event['status'] not in ('APPROVED_CROP', 'PENDING', 'REJECTED'):
            raise ValueError('Unknown crop review state')
        if event['status'] == 'APPROVED_CROP':
            if event.get('human_ack') is not True or len(event.get('reviewer', '').strip()) < 2:
                raise ValueError('Explicit human acknowledgement and reviewer required')
            if event.get('preview_evaluation', {}).get('crop') != event['crop_xyxy']:
                raise ValueError('Approval preview and approved coordinates differ')
        latest[event['image_path']] = event
    return latest


def reconstruct_row(base, review=None, automatic=None, *, allow_cached_auto=False, reference_override=None):
    """수동 승인 > 명시적 보류/거부 > 선택적 저장된 자동 제안 > 원본 전체 순서.

    allow_cached_auto=True인 결과는 연구 후보이며 사람 승인/제품 보존 검증으로 승격되지 않는다.
    """
    row = dict(base)
    width, height = int(base['original_width']), int(base['original_height'])
    original = checked_crop([int(base[k]) for k in COORDS], width, height)
    full = [0, 0, width, height]
    crop, policy, provenance = full, 'C', 'FULL_FRAME_NO_COMPUTED_GATE'
    row.update(crop_review_status='UNREVIEWED', crop_reviewer='', crop_reviewed_utc='',
               manual_annotation_assisted=False, requires_evaluation_leakage_review=False,
               human_observed_loss_acknowledged=False,
               human_product_bbox_loss_acknowledged=False,human_defect_mask_loss_acknowledged=False,
               reference_confirmation_utc='',reference_confirmation_source='',reference_bbox_xyxy='')
    row['automatic_feature_status'] = 'CACHED_VERIFIED_SOURCE' if automatic else 'NOT_COMPUTED'
    row['auto_gate_status'] = automatic.get('gate_status', '') if automatic else ''
    row['auto_risk_codes'] = json.dumps(automatic.get('risk_codes', [])) if automatic else '[]'
    candidate = checked_crop(automatic['crop'], width, height) if automatic else None
    for key, value in zip(('auto_candidate_x0','auto_candidate_y0','auto_candidate_x1','auto_candidate_y1'), candidate or ['']*4):
        row[key] = value
    row['auto_candidate_policy'] = automatic.get('policy', '') if automatic else ''
    if automatic:
        provenance = 'FULL_FRAME_AUTOMATIC_CANDIDATE_NOT_APPLIED'
        if allow_cached_auto:
            crop = candidate
            policy = 'C' if crop == full else 'AUTO_CACHED_' + automatic['policy']
            provenance = 'CACHED_CALIBRATED_IMAGE_GATE_PRODUCT_UNVERIFIED'
    if review:
        if review['case_id'] != base['image_id'] or review['image_path'] != base['source_relative_path']:
            raise ValueError('Review image identity mismatch')
        if review['source_fingerprint'] != base['source_fingerprint']:
            raise ValueError('Review source fingerprint mismatch')
        row['crop_review_status'] = review['status']
        if review['status'] == 'APPROVED_CROP':
            crop = checked_crop(review['crop_xyxy'], width, height)
            policy = 'C' if crop == full else 'HUMAN_CROP'
            provenance = 'LATEST_EXPLICIT_HUMAN_CROP_APPROVAL'
            preview = review['preview_evaluation']
            row.update(crop_reviewer=review['reviewer'], crop_reviewed_utc=review['reviewed_utc'],
                       human_observed_loss_acknowledged=bool(review.get('risk_ack') and preview.get('observed_loss')),
                       human_product_bbox_loss_acknowledged=bool(review.get('risk_ack') and preview.get('product',{}).get('fully_contained') is False),
                       human_defect_mask_loss_acknowledged=bool(review.get('risk_ack') and preview.get('defect_mask',{}).get('retention') is not None and preview['defect_mask']['retention']<1),
                       manual_annotation_assisted=bool(preview.get('annotation_assisted')),
                       requires_evaluation_leakage_review=base['split']=='test' and bool(preview.get('annotation_assisted')))
        else:
            crop, policy, provenance = full, 'C', 'MANUAL_'+review['status']+'_FULL_FRAME'
    use_reference=bool(reference_override and (not review or review['reviewed_utc']<reference_override['confirmed_utc']))
    if use_reference:
        if (reference_override['image_id']!=base['image_id'] or reference_override['image_path']!=base['source_relative_path']
                or reference_override['source_fingerprint']!=base['source_fingerprint']):
            raise ValueError('Confirmed reference source mismatch')
        crop=checked_crop(reference_override['crop_xyxy'],width,height)
        policy='C' if crop==full else 'USER_REFERENCE_CROP'
        provenance='USER_CONFIRMED_EXISTING_PRODUCT_REFERENCE'
        row.update(crop_review_status='USER_CONFIRMED_REFERENCE_REUSE',crop_reviewer='',crop_reviewed_utc='',
                   human_observed_loss_acknowledged=False,
                   human_product_bbox_loss_acknowledged=False,human_defect_mask_loss_acknowledged=False,
                   reference_confirmation_utc=reference_override['confirmed_utc'],
                   reference_confirmation_source=reference_override['confirmation_source'],
                   reference_bbox_xyxy=json.dumps(reference_override['product_bbox_xyxy']),
                   manual_annotation_assisted=True,requires_evaluation_leakage_review=base['split']=='test')
    for key, value in zip(COORDS, crop):
        row[key] = value
    cw, ch = crop[2]-crop[0], crop[3]-crop[1]
    row.update(crop_width=cw,crop_height=ch,full_frame=crop==full,selected_policy=policy,
               geometric_gain=math.sqrt(width*height/(cw*ch)),gain_x=width/cw,gain_y=height/ch,
               crop_policy=policy,policy_version=VERSION,selection_provenance=provenance,
               coordinate_format='XYXY_EXCLUSIVE_ORIGINAL_PIXELS',additional_center_crop_allowed=False,
               crop_changed_from_input=crop!=original,approved_crop_present=bool(not use_reference and review and review['status']=='APPROVED_CROP'),
               product_preservation_validation='USER_CONFIRMED_REFERENCE_BBOX_NOT_PRODUCT_PIXEL_GT' if use_reference else
               'UNVERIFIED_AUTOMATIC_SCOPE' if policy.startswith('AUTO') else
               'HUMAN_CROP_REVIEW_NOT_PRODUCT_PIXEL_GT' if provenance.startswith('LATEST') else 'FULL_FRAME_IDENTITY',
               quality_status='USER_REFERENCE_REUSE_REQUIRES_POST_CROP_AUDIT' if use_reference else
               'AUTOMATIC_PRODUCT_UNVERIFIED' if policy.startswith('AUTO') else
               ('HUMAN_APPROVED_WITH_WARNING' if review['preview_evaluation'].get('requires_risk_ack') else 'HUMAN_APPROVED_CROP')
               if provenance.startswith('LATEST') else 'FULL_FRAME_FALLBACK',
               fallback_reason='' if crop!=full else provenance,
               processing_status='OK_COORDINATES_RECONSTRUCTED',
               source_crop_policy_version=base['policy_version'])
    return row
