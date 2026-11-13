"""팀 내부 배포 테이블·ZIP·기존 로더 연결. 저장 Crop과 Split은 변경하지 않는다."""
from pathlib import Path, PurePosixPath
import hashlib
import json
import os
import re
import stat
import zipfile

import numpy as np
import pandas as pd
import torch

from .manifest import ManifestIndex, file_hash, geometry_errors, group_audit
from .datasets import SingleViewDataset, FiveViewDataset

RELEASE_ID = 'MV_TEAM_DATA_RELEASE_v1'
ELIGIBILITY = ['anomaly_train_eligible', 'anomaly_image_eval_eligible',
               'anomaly_pixel_eval_eligible', 'detection_train_eligible', 'detection_eval_eligible']
REQUIRED_FILES = {'README_DATA.md', 'release.json', 'manifests/canonical.csv',
                  'manifests/eligibility.csv', 'annotations/defect_boxes.csv',
                  'annotations/product_boxes.csv', 'schemas/class_mapping.json',
                  'schemas/annotation_schema.json', 'validation/validation.json',
                  'checksums/SHA256SUMS'}


def save_json(path, value):
    """JSON은 비표준 NaN 없이 저장하고, 기존 완료 결과의 교체는 호출자가 통제한다."""
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False,
                                    default=lambda x: x.item() if isinstance(x, np.generic) else str(x))+'\n')


def relative_path(value):
    """배포 경로는 POSIX 상대 경로만 허용한다. Windows 절대 경로와 탈출 경로도 거부한다."""
    value = str(value)
    p = PurePosixPath(value)
    if not value or '\\' in value or ':' in value or p.is_absolute() or '..' in p.parts or p.as_posix() != value:
        raise ValueError('Unsafe relative path: '+value)
    return value


def eligibility_row(row):
    """Split별 적격성과 타깃 유효성을 분리한다. 부분 주석 손실도 기본 계약에서 제외한다."""
    valid = bool(row['image_valid']) and bool(row['target_geometry_valid'])
    loss = bool(row['crop_mask_loss']) or int(row['crop_removed_boxes']) > 0
    annotation = row['annotation_status']
    detection = valid and not loss and annotation in ('OK_NEGATIVE', 'SUPERVISED_VALID')
    image_eval = valid and row['split'] in ('validation', 'test')
    pixel = image_eval and not loss and (row['status'] == 'OK' and annotation == 'OK_NEGATIVE'
                                         or row['mask_status'] == 'PRESENT_POSITIVE' and annotation == 'SUPERVISED_VALID')
    reasons = []
    if not valid:
        reasons.append('FILE_OR_GEOMETRY_INVALID')
    if loss:
        reasons.append('CROP_ANNOTATION_LOSS')
    if annotation not in ('OK_NEGATIVE', 'SUPERVISED_VALID'):
        reasons.append(annotation)
    return dict(anomaly_train_eligible=valid and row['status'] == 'OK' and annotation == 'OK_NEGATIVE' and row['split'] == 'train',
                anomaly_image_eval_eligible=image_eval, anomaly_pixel_eval_eligible=pixel,
                detection_train_eligible=detection and row['split'] == 'train',
                detection_eval_eligible=detection and row['split'] in ('validation', 'test'),
                detection_trainable=detection, exclusion_reason=';'.join(reasons))


def read_tables(root):
    """개인 원본 경로를 추측하지 않고 ZIP 안의 상대 테이블만 읽는다."""
    root = Path(root)
    read = lambda name: pd.read_csv(root/name, keep_default_na=False)
    return (read('manifests/canonical.csv'), read('manifests/eligibility.csv'),
            read('annotations/defect_boxes.csv'), read('annotations/product_boxes.csv'),
            json.loads((root/'schemas/class_mapping.json').read_text()))


def validate_tables(root, eligibility_calculator=eligibility_row):
    """해시 검사와 별개로 좌표·참조·클래스·5시점·적격성의 의미를 전수 확인한다."""
    d, e, b, products, classes = read_tables(root)
    errors = geometry_errors(d)
    if len(errors):
        raise ValueError('Invalid canonical geometry: '+errors.head().to_json())
    group_audit(d, require_complete=True)
    ids = set(d.image_id)
    if e.image_id.duplicated().any() or set(e.image_id) != ids:
        raise ValueError('Eligibility IDs do not match canonical')
    if not d.status.isin(['OK', 'NG']).all() or not d.mask_status.isin(['MISSING', 'PRESENT_EMPTY', 'PRESENT_POSITIVE', 'INVALID']).all():
        raise ValueError('Unknown label state')
    for col in ['image_path', 'original_path', 'source_relative_path']:
        for value in d[col].unique():
            relative_path(value)
    if not d.image_path.eq(d.source_relative_path).all() or not d.original_path.eq(d.image_path).all():
        raise ValueError('Canonical paths must refer to the same relative image')
    for value in d.loc[d.has_mask, 'mask_path'].unique():
        relative_path(value)
    if not d.has_mask.isin([True, False]).all() or not d.has_mask.eq(d.mask_path.ne('')).all():
        raise ValueError('has_mask/path mismatch')
    if not d.has_mask.eq(d.mask_status.ne('MISSING')).all():
        raise ValueError('Mask availability mismatch')
    mapping = classes['yolo']
    if sorted(mapping.values()) != list(range(len(mapping))) or classes['coco'] != {k: v+1 for k, v in mapping.items()}:
        raise ValueError('Canonical class IDs or COCO offsets invalid')
    if not d.loc[d.status.eq('NG'), 'defect_class'].isin(mapping).all() or not d.loc[d.status.eq('OK'), 'defect_class'].eq('').all():
        raise ValueError('Defect class and image status are mixed')
    for col in ['source_sha256', 'mask_sha256']:
        values = d[col] if col == 'source_sha256' else d.loc[d.has_mask, col]
        if not values.str.fullmatch('[0-9a-f]{64}').all():
            raise ValueError('Missing content hashes: '+col)
    if b.bbox_id.duplicated().any() or not set(b.image_id) <= ids:
        raise ValueError('Dangling/duplicate defect BBox')
    indexed = d.set_index('image_id')
    if len(b):
        identity = indexed.loc[b.image_id]
        if not np.array_equal(identity.image_path, b.image_path) or not identity.status.eq('NG').all():
            raise ValueError('BBox identity or OK negative violation')
        if not np.array_equal(identity.defect_class.map(mapping), b.class_id):
            raise ValueError('BBox class conflicts with canonical filename-resolved label')
        if not identity.mask_status.eq('PRESENT_POSITIVE').all():
            raise ValueError('Non-positive mask cannot supply defect boxes')
        bounds = b[['x0', 'y0', 'x1', 'y1']].to_numpy(float)
        limits = identity[['original_width', 'original_height']].to_numpy(float)
        if not np.isfinite(bounds).all() or (bounds[:, :2] < 0).any() or (bounds[:, 2:] > limits).any() or (bounds[:, 2:] <= bounds[:, :2]).any():
            raise ValueError('Original boxes outside image')
        crop = identity[['crop_x0', 'crop_y0', 'crop_x1', 'crop_y1']].to_numpy(float)
        local = bounds-crop[:, [0, 1, 0, 1]]
        local[:, [0, 2]] = np.clip(local[:, [0, 2]], 0, (crop[:, 2]-crop[:, 0])[:, None])
        local[:, [1, 3]] = np.clip(local[:, [1, 3]], 0, (crop[:, 3]-crop[:, 1])[:, None])
        expected_keep = np.all(local[:, 2:] > local[:, :2], axis=1)
        if not np.array_equal(local, b[['crop_bbox_x0', 'crop_bbox_y0', 'crop_bbox_x1', 'crop_bbox_y1']].to_numpy(float)) or not np.array_equal(expected_keep, b.kept_after_crop):
            raise ValueError('Incorrect crop-origin/clip conversion')
    if products.annotation_id.duplicated().any() or not set(products.image_id) <= ids:
        raise ValueError('Product annotation references invalid')
    if not products.source_type.isin(['HUMAN_VERIFIED_GT', 'AUTOMATIC_PROPOSAL', 'CROP_APPROXIMATION']).all():
        raise ValueError('Unknown product annotation provenance')
    if not products.is_ground_truth.eq(products.source_type.eq('HUMAN_VERIFIED_GT')).all():
        raise ValueError('Proposal/crop must never become GT')
    if not products.default_detection_target.eq(False).all():
        raise ValueError('Products cannot enter baseline defect detection targets')
    if len(products):
        p = products[['x0', 'y0', 'x1', 'y1']].to_numpy(float)
        wh = indexed.loc[products.image_id, ['original_width', 'original_height']].to_numpy(float)
        if not np.isfinite(p).all() or (p[:, :2] < 0).any() or (p[:, 2:] > wh).any() or (p[:, 2:] <= p[:, :2]).any():
            raise ValueError('Invalid product annotation bounds')
    es = e.set_index('image_id').loc[d.image_id]
    needed = ['image_id', 'image_valid', 'target_geometry_valid', 'crop_mask_loss', 'crop_removed_boxes', 'annotation_status', 'split', 'status', 'mask_status']
    needed += [k for k in ['crop_annotation_status', 'product_bbox_source'] if k in d]
    for row, actual in zip(d[needed].to_dict('records'), es.to_dict('records')):
        expected = eligibility_calculator(row)
        if any(actual[k] != v for k, v in expected.items()):
            raise ValueError('Eligibility policy mismatch: '+row['image_id'])
    counts = b.groupby('image_id').size()
    if not d.source_box_count.eq(d.image_id.map(counts).fillna(0).astype(int)).all():
        raise ValueError('Defect component count mismatch')
    if not d.loc[d.status.eq('OK'), 'source_box_count'].eq(0).all():
        raise ValueError('OK must have zero defect objects')
    return dict(images=len(d), products=d.product_id.nunique(), categories=d.category.nunique(),
                status_counts=d.status.value_counts().to_dict(), mask_counts=d.mask_status.value_counts().to_dict(),
                defect_boxes=len(b), product_box_sources=products.source_type.value_counts().to_dict(),
                eligibility={k: int(e[k].sum()) for k in ELIGIBILITY},
                crop_mask_loss_images=int(d.crop_mask_loss.sum()), annotation_status=d.annotation_status.value_counts().to_dict())


def write_checksums(root):
    """원본 데이터 없이 배포 파일 자체를 식별한다. SHA256SUMS는 자기 자신을 포함하지 않는다."""
    root = Path(root)
    dest = root/'checksums/SHA256SUMS'
    if dest.exists():
        raise FileExistsError(dest)
    files = sorted(p for p in root.rglob('*') if p.is_file())
    dest.parent.mkdir(exist_ok=True)
    dest.write_text(''.join(f'{file_hash(p)}  {p.relative_to(root).as_posix()}\n' for p in files))


def verify_release(root):
    """모든 파일 해시와 정확한 파일 집합을 검사한다. 해시는 서명이 아니므로 ZIP 해시는 별도 전달한다."""
    root = Path(root).resolve()
    seen = set()
    for line in (root/'checksums/SHA256SUMS').read_text().splitlines():
        digest, name = line.split('  ', 1)
        relative_path(name)
        path = root/name
        if name in seen or path.is_symlink() or not path.resolve().is_relative_to(root) or not path.is_file() or file_hash(path) != digest:
            raise ValueError('Checksum/path validation failed: '+name)
        seen.add(name)
    actual = {p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file()}
    if actual != seen | {'checksums/SHA256SUMS'} or not REQUIRED_FILES <= actual:
        raise ValueError('Unexpected/missing release files')
    release = json.loads((root/'release.json').read_text())
    if release['canonical_sha256'] != file_hash(root/'manifests/canonical.csv'):
        raise ValueError('Canonical release hash mismatch')
    if release.get('release_id') == 'MV_TEAM_DATA_RELEASE_v2':
        from .team_release_v2 import validate_v2
        result = validate_v2(root)
    else:
        result = validate_tables(root)
    if result['images'] != release['images']:
        raise ValueError('Release row count mismatch')
    return dict(status='VERIFIED', files=len(actual), **result)


def pack_release(root, destination):
    """이미지·가중치·원장 없는 승인된 배포 파일만 새 ZIP으로 만든다."""
    root, destination = Path(root), Path(destination)
    verify_release(root)
    if destination.exists():
        raise FileExistsError(destination)
    temporary = destination.with_suffix('.zip.partial')
    with zipfile.ZipFile(temporary, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for p in sorted(root.rglob('*')):
            if not p.is_file():
                continue
            if p.suffix not in {'.md', '.csv', '.json', ''} or 'ledger' in p.name.lower() or p.is_symlink():
                raise ValueError('File is not permitted in team ZIP: '+p.name)
            archive.write(p, root.name+'/'+p.relative_to(root).as_posix())
    with zipfile.ZipFile(temporary) as archive:
        if archive.testzip() is not None:
            raise ValueError('Generated ZIP CRC failed')
    os.replace(temporary, destination)
    return dict(path=str(destination), bytes=destination.stat().st_size, sha256=file_hash(destination))


def extract_release(archive, destination, expected_sha256=None):
    """탈출 경로·중복 이름·링크·과대 압축 해제를 거부하고 새 폴더에만 해제한다."""
    archive, destination = Path(archive), Path(destination)
    if expected_sha256 is not None and file_hash(archive) != expected_sha256:
        raise ValueError('ZIP SHA-256 does not match trusted sender value')
    if destination.exists():
        raise FileExistsError(destination)
    with zipfile.ZipFile(archive) as z:
        names = z.namelist()
        if len(names) != len(set(names)) or sum(v.file_size for v in z.infolist()) > 2_000_000_000:
            raise ValueError('Duplicate or oversized ZIP')
        roots = {PurePosixPath(n).parts[0] for n in names}
        if len(roots) != 1 or not roots <= {RELEASE_ID, 'MV_TEAM_DATA_RELEASE_v2'}:
            raise ValueError('Unexpected ZIP root')
        for item in z.infolist():
            relative_path(item.filename.rstrip('/'))
            if stat.S_ISLNK(item.external_attr >> 16):
                raise ValueError('Unexpected ZIP root/symlink')
        if z.testzip() is not None:
            raise ValueError('ZIP CRC failed')
        destination.mkdir(parents=True)
        z.extractall(destination)
    root = destination/next(iter(roots))
    verify_release(root)
    return root


class TeamRelease:
    """통합 canonical을 기존 ManifestIndex의 두 입력으로 분리하는 읽기 전용 연결 계층."""
    def __init__(self, root, data_root):
        self.root = Path(root).resolve()
        if type(self) is TeamRelease and json.loads((self.root/'release.json').read_text()).get('release_id') == 'MV_TEAM_DATA_RELEASE_v2':
            raise ValueError('v2 requires TeamReleaseV2 with explicit anomaly/detection policies')
        self.validation = verify_release(self.root)
        self.data_root = Path(data_root).resolve()
        self.canonical, self.eligibility, self.boxes, self.products, self.classes = read_tables(self.root)
        self.sha256 = file_hash(self.root/'manifests/canonical.csv')
        self.by_id = self.canonical.set_index('image_id')
        self.eligible_by_id = self.eligibility.set_index('image_id')

    def index(self, image_ids=None):
        """기존 merge 계약의 status/has_mask/mask_path 중복 컬럼을 제거한다."""
        d = self.canonical
        if image_ids is not None:
            ids = set(image_ids)
            if not ids <= set(d.image_id):
                raise ValueError('Unknown requested image ID')
            d = d[d.image_id.isin(ids)].copy()
        label_cols = ['image_path', 'product_id', 'category', 'view', 'split', 'status', 'has_mask', 'mask_path']
        labels = d[label_cols].copy()
        geometry = d.drop(columns=['image_path', 'status', 'has_mask', 'mask_path'])
        index = ManifestIndex(geometry, labels, self.boxes[self.boxes.image_id.isin(d.image_id)], self.classes, data_root=self.data_root)
        # DataFrame 직렬화 해시 대신 배포 canonical 원본 파일의 SHA를 실험 기록에 사용한다.
        index.sha256 = self.sha256
        return index

    def dataset(self, *, split=None, task='all', adapter=None, image_ids=None, eligible_only=False):
        """같은 이미지 전처리를 사용하며 라벨은 전처리가 아닌 학습 대상 필터에만 쓴다."""
        d = self.canonical
        if split is not None:
            if split not in ('train', 'validation', 'test'):
                raise ValueError('Unknown split')
            d = d[d.split.eq(split)]
        if image_ids is not None:
            if not set(image_ids) <= set(self.canonical.image_id):
                raise ValueError('Unknown requested image ID')
            d = d[d.image_id.isin(image_ids)]
        if eligible_only:
            if task not in ('anomaly', 'detection') or split is None:
                raise ValueError('Eligibility filtering requires task and split')
            key = ('anomaly_train_eligible' if split == 'train' else 'anomaly_image_eval_eligible') if task == 'anomaly' else ('detection_train_eligible' if split == 'train' else 'detection_eval_eligible')
            d = d[d.image_id.map(self.eligible_by_id[key]).eq(True)]
        return ReleasedSingleViewDataset(self.index(d.image_id), release=self, task=task, adapter=adapter)


class ReleasedSingleViewDataset(SingleViewDataset):
    """PC별 mtime 대신 콘텐츠 해시를 먼저 확인하고 기존 Crop 로더를 호출한다."""
    def __init__(self, index, *, release, **kwargs):
        super().__init__(index, **kwargs)
        self.release = release
        self._content_verified = {}

    def __getitem__(self, item):
        row = self.data.iloc[item].to_dict()
        if not row['image_valid'] or not row['target_geometry_valid']:
            raise ValueError('Invalid source must not enter training: '+row['image_id'])
        for field, expected in [('source_relative_path', row['source_sha256']), ('mask_path', row['mask_sha256'])]:
            if not row.get(field):
                continue
            path = (self.release.data_root/relative_path(row[field])).resolve()
            if not path.is_relative_to(self.release.data_root):
                raise ValueError('Data path escapes root')
            s = path.stat()
            key = (str(path), s.st_size, s.st_mtime_ns)
            if self._content_verified.get(key) != expected:
                if file_hash(path) != expected:
                    raise ValueError('Dataset content SHA-256 mismatch: '+row[field])
                after = path.stat()
                if (s.st_size, s.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                    raise ValueError('Source changed during verification')
                self._content_verified[key] = expected
            if field == 'source_relative_path':
                self.data.at[self.data.index[item], 'source_fingerprint'] = f'stat-v1:{s.st_size}:{s.st_mtime_ns}'
        sample = super().__getitem__(item)
        expected = self.release.eligible_by_id.loc[row['image_id']]
        # 적격성 표가 더 보수적이면 기존 로더의 부분 주석 허용 결과보다 우선한다.
        sample['detection_trainable'] = bool(sample['detection_trainable'] and expected.detection_trainable)
        sample['metadata'].update(data_release_id=RELEASE_ID, canonical_manifest_sha256=self.release.sha256,
                                  content_hash_checked=True, eligibility={k: bool(expected[k]) for k in ELIGIBILITY})
        return sample


def export_targets(root, destination, *, split, format):
    """Crop 좌표계의 가상 영상 타깃을 내보낸다. 원본 JPG를 해당 COCO 영상으로 오인하면 안 된다."""
    root, destination = Path(root), Path(destination)
    if destination.exists():
        raise FileExistsError(destination)
    if split not in ('train', 'validation', 'test') or format not in ('yolo', 'coco'):
        raise ValueError('Invalid export arguments')
    verify_release(root)
    d, e, boxes, _, classes = read_tables(root)
    d = d[d.split.eq(split)]
    key = 'detection_train_eligible' if split == 'train' else 'detection_eval_eligible'
    d = d.merge(e[['image_id', key, 'exclusion_reason']], on='image_id', validate='one_to_one')
    destination.mkdir(parents=True)
    d[~d[key]].to_csv(destination/'excluded.csv', index=False)
    allowed = d[d[key]]
    bgroups = {k: g for k, g in boxes[boxes.kept_after_crop].groupby('image_id')}
    images, annotations, index = [], [], []
    if format == 'yolo':
        (destination/'labels').mkdir()
    for number, row in enumerate(allowed.to_dict('records'), 1):
        objects = bgroups.get(row['image_id'], boxes.iloc[:0])
        lines = []
        for b in objects.to_dict('records'):
            x0, y0, x1, y1 = [b['crop_bbox_'+axis] for axis in ('x0', 'y0', 'x1', 'y1')]
            coords = [(x0+x1)/2/row['crop_width'], (y0+y1)/2/row['crop_height'], (x1-x0)/row['crop_width'], (y1-y0)/row['crop_height']]
            if not all(0 <= v <= 1 for v in coords) or min(coords[2:]) <= 0:
                raise ValueError('Invalid normalized boxes')
            lines.append(str(int(b['class_id']))+' '+' '.join(f'{v:.12g}' for v in coords))
            annotations.append(dict(id=len(annotations)+1, image_id=number, category_id=int(b['class_id'])+1,
                                    bbox=[x0, y0, x1-x0, y1-y0], area=(x1-x0)*(y1-y0), iscrowd=0))
        if row['status'] == 'NG' and not lines:
            raise ValueError('NG cannot be exported as an empty negative')
        if format == 'yolo':
            (destination/'labels'/(row['image_id']+'.txt')).write_text('\n'.join(lines)+('\n' if lines else ''))
        images.append(dict(id=number, image_id=row['image_id'], file_name='virtual_crops/'+row['image_id']+'.jpg',
                           width=row['crop_width'], height=row['crop_height'], original_path=row['image_path'],
                           crop_xyxy=[row['crop_'+v] for v in ('x0', 'y0', 'x1', 'y1')]))
        index.append(dict(image_id=row['image_id'], original_path=row['image_path'], boxes=len(lines), status=row['status']))
    if format == 'coco':
        save_json(destination/'instances.json', dict(info={'coordinate_space': 'CROP_PIXELS', 'images_are_virtual_crops': True},
                   images=images, annotations=annotations, categories=[dict(id=v, name=k) for k, v in classes['coco'].items()]))
    pd.DataFrame(index).to_csv(destination/'image_index.csv', index=False)
    save_json(destination/'export.json', dict(format=format, split=split, images=len(allowed), objects=len(annotations),
              excluded=len(d)-len(allowed), coordinate_space='CROP_PIXELS', images_written=False,
              warning='Use the common crop loader. Original JPGs are not already-cropped COCO/YOLO images.'))
    return dict(images=len(allowed), objects=len(annotations), excluded=len(d)-len(allowed))


def torchvision_target(release, image_id):
    """Crop 기준 XYXY와 배경 0을 위한 +1 labels. Resize는 기존 모델 Adapter가 별도로 맡는다."""
    if not release.eligible_by_id.loc[image_id].detection_trainable:
        raise ValueError('Not a supervised detection target')
    b = release.boxes[release.boxes.image_id.eq(image_id) & release.boxes.kept_after_crop]
    boxes = torch.tensor(b[['crop_bbox_x0', 'crop_bbox_y0', 'crop_bbox_x1', 'crop_bbox_y1']].to_numpy(), dtype=torch.float32)
    return dict(boxes=boxes.reshape(-1, 4), labels=torch.tensor(b.class_id.to_numpy()+1, dtype=torch.int64))
