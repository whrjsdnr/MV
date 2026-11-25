"""승인 데이터 v2를 읽기 전용으로 연결한다. 좌표와 Split은 여기서 만들지 않는다."""
from contextlib import contextmanager
from pathlib import Path
import math
import random
import tempfile

import pandas as pd
from mv_analysis.data.team_release import extract_release
from mv_analysis.data.team_release_v2 import TeamReleaseV2
from mv_analysis.training.preflight import validate_data_release


@contextmanager
def open_release(request):
    source = Path(request['release_source'])
    verified = validate_data_release(source, request['data_root'])
    if verified['bindings_sha256'] != request['data_sha256']:
        raise ValueError('Release changed after preflight')
    with tempfile.TemporaryDirectory(prefix='mv-owner-release-') as temporary:
        root = extract_release(source, Path(temporary)/'release') if source.is_file() else source
        yield TeamReleaseV2(root, request['data_root'])


def subsample_background_rows(frame, ratio, seed):
    """OK(배경) 행만 품목별로 비율만큼 seed로 결정적으로 남긴다. NG 행은 전부 유지한다."""
    rng = random.Random(seed)
    ng = frame[frame.status.eq('NG')]
    parts = [ng]
    for _, group in frame[frame.status.eq('OK')].groupby('category', sort=True):
        keep = math.ceil(len(group) * ratio)
        if keep:
            parts.append(group.loc[rng.sample(list(group.index), keep)])
    return pd.concat(parts)


def datasets(release, config, *, category=None):
    """적격 표로 먼저 거른다. NG 미주석을 빈 Negative로 바꾸지 않는다."""
    task = config['model_family']
    result = {}
    for split in ('train', 'validation', 'test'):
        rows = release.canonical
        categories = [category] if category else config['categories']
        if categories:
            rows = rows[rows.category.isin(categories)]
        ds = release.dataset(task=task, split=split, image_ids=rows.image_id.tolist(),
                             eligible_only=True, annotation_policy='defect_only')
        limit = config['train_limit'] if split == 'train' else config['eval_limit']
        if limit:
            # 제한은 Split을 다시 만들지 않는다. 제한된 실험임을 config에 그대로 기록한다.
            rows = ds.data
            if split != 'train' and limit >= 2:
                # 짧은 점검 표본은 OK/NG를 함께 포함한다. 전체 실행에는 이 제한이 없다.
                selected = list(rows[rows.status.eq('OK')].head(limit//2).image_id)
                selected += list(rows[rows.status.eq('NG')].head(limit-limit//2).image_id)
                ds.index.data = rows[rows.image_id.isin(selected)].copy()
            else:
                ds.index.data = rows.iloc[:limit].copy()
            ds.data = ds.index.data.reset_index(drop=True)
        ratio = config.get('background_keep_ratio')
        if split == 'train' and ratio is not None:
            if config['model_family'] != 'detection':
                raise ValueError('background_keep_ratio is detection-only; anomaly OK rows are the training signal')
            ds.index.data = subsample_background_rows(ds.index.data, ratio, config['seed'])
            ds.data = ds.index.data.reset_index(drop=True)
        if not len(ds):
            raise ValueError(f'No eligible {split} images for {category or categories}')
        result[split] = ds
    return result


def collate(samples):
    """가변 크기 원본/결함 수를 유지하는 검출용 배치."""
    return samples
