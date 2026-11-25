import importlib.util
from pathlib import Path
import pytest

path=Path(__file__).resolve().parents[1]/'scripts/report_fusion_performance.py'
spec=importlib.util.spec_from_file_location('fusion_final_report',path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


def test_confusion_and_rates_have_known_values():
 r=m.binary_metrics([True,True,False,False],[True,False,True,False])
 assert (r['tp'],r['fn'],r['fp'],r['tn'])==(1,1,1,1)
 assert r['f1']==r['recall']==r['false_alarm_rate']==.5


def test_ranking_ties_and_nontrivial_order():
 assert m.ranking([True,False,True,False],[1,1,1,1])==dict(auroc=.5,average_precision=.5)
 r=m.ranking([True,False,True,False],[.9,.8,.7,.6]);assert r['auroc']==.75 and r['average_precision']==pytest.approx(5/6)


def test_hold_is_deferred_and_not_normal_or_correct():
 rows=[dict(truth='defect',binary_verdict='normal',verdict='hold',fusion_score=.5,rtdetr_positive=False,hvq_positive=True),dict(truth='normal',binary_verdict='normal',verdict='normal',fusion_score=.1,rtdetr_positive=False,hvq_positive=False)]
 r=m.summarize(rows)
 assert r['binary_threshold']['fn']==1
 assert r['final_with_hold']['hold_ng']==1
 assert r['final_with_hold']['decided_only_metrics']['fn']==0
 assert r['final_with_hold']['coverage']==.5


def test_partial_pipeline_is_refused_before_db_access(tmp_path):
 assert m.collect(tmp_path/'no_credentials',tmp_path,tmp_path/'no_manifest') is None
