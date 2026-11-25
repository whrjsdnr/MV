# 한글 안내: train 배경(OK) 행의 비율 샘플링이 결정적이고 NG를 보존하는지 검사한다.
import pandas as pd
import pytest

from models._shared.data import subsample_background_rows


def _frame():
    rows = []
    for cat, n_ok in (('a', 10), ('b', 5)):
        for i in range(n_ok):
            rows.append(dict(image_id=f'{cat}-ok-{i}', category=cat, status='OK'))
        for i in range(2):
            rows.append(dict(image_id=f'{cat}-ng-{i}', category=cat, status='NG'))
    return pd.DataFrame(rows)


def test_ng_preserved_and_ok_stratified():
    out = subsample_background_rows(_frame(), 0.2, 42)
    assert len(out[out.status.eq('NG')]) == 4
    per_cat = out[out.status.eq('OK')].groupby('category').size().to_dict()
    assert per_cat == {'a': 2, 'b': 1}  # ceil(10*0.2), ceil(5*0.2)


def test_deterministic_for_same_seed():
    f = _frame()
    assert subsample_background_rows(f, 0.2, 42).equals(subsample_background_rows(f, 0.2, 42))


def test_subset_of_input_and_no_duplicates():
    f = _frame()
    out = subsample_background_rows(f, 0.5, 7)
    assert out.image_id.is_unique
    assert set(out.image_id) <= set(f.image_id)


def test_full_ratio_keeps_everything():
    out = subsample_background_rows(_frame(), 1.0, 0)
    assert len(out) == len(_frame())


def test_invalid_ratio_rejected_by_settings():
    from mv_analysis.training.settings import model_settings
    import pytest
    for bad in (0, -0.1, 1.5):
        with pytest.raises(ValueError):
            model_settings('yolo11', {'background_keep_ratio': bad})


def test_valid_ratio_accepted_by_settings():
    from mv_analysis.training.settings import model_settings
    cfg = model_settings('yolo11', {'background_keep_ratio': 0.2})
    assert cfg['background_keep_ratio'] == 0.2
    assert model_settings('yolo11')['background_keep_ratio'] is None
