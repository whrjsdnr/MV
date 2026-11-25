"""Read-only final fusion report; waits for the verified background pipeline with --wait."""
from pathlib import Path
import argparse,collections,csv,datetime,hashlib,itertools,json,math,os,sys,time

MV=Path(__file__).resolve().parents[1]
BASE=MV/'outputs/fusion_agent_validation_20261124_v1'
sys.path.insert(0,str(BASE/'background_code_v1'))
from sqlalchemy import text
from fusion_store import engine,read_env_file


def divide(n,d):return n/d if d else None


def binary_metrics(truth,predicted):
    if len(truth)!=len(predicted):raise ValueError('GT/prediction length mismatch')
    tp=sum(t and p for t,p in zip(truth,predicted));fn=sum(t and not p for t,p in zip(truth,predicted));fp=sum(not t and p for t,p in zip(truth,predicted));tn=sum(not t and not p for t,p in zip(truth,predicted))
    return dict(tp=tp,fn=fn,fp=fp,tn=tn,ng=tp+fn,ok=fp+tn,recall=divide(tp,tp+fn),miss_rate=divide(fn,tp+fn),false_alarm_rate=divide(fp,fp+tn),precision=divide(tp,tp+fp),f1=divide(2*tp,2*tp+fp+fn),accuracy=divide(tp+tn,len(truth)))


def ranking(truth,scores):
    groups=[]
    for score,items in itertools.groupby(sorted(zip(scores,truth)),key=lambda x:x[0]):
        labels=[t for _,t in items];groups.append((sum(labels),len(labels)-sum(labels)))
    positives=sum(truth);negatives=len(truth)-positives
    if not positives or not negatives:return dict(auroc=None,average_precision=None)
    neg_seen=0;wins=0.
    for ng,ok in groups:wins+=ng*(neg_seen+.5*ok);neg_seen+=ok
    tp=seen=0;ap=0.
    for ng,ok in reversed(groups):tp+=ng;seen+=ng+ok;ap+=(ng/positives)*(tp/seen)
    return dict(auroc=wins/(positives*negatives),average_precision=ap)


def summarize(rows):
    truth=[r['truth']=='defect' for r in rows]
    binary=binary_metrics(truth,[r['binary_verdict']=='defect' for r in rows])
    binary.update(ranking(truth,[r['fusion_score'] for r in rows]))
    decided=[r for r in rows if r['verdict']!='hold'];held=[r for r in rows if r['verdict']=='hold']
    final=binary_metrics([r['truth']=='defect' for r in decided],[r['verdict']=='defect' for r in decided])
    hold_ng=sum(r['truth']=='defect' for r in held);hold_ok=len(held)-hold_ng
    return {'products':len(rows),'binary_threshold':binary,'final_with_hold':{'decided_products':len(decided),'hold_products':len(held),'hold_ng':hold_ng,'hold_ok':hold_ok,'coverage':divide(len(decided),len(rows)),'hold_rate':divide(len(held),len(rows)),'decided_only_metrics':final,'miss_rate_over_all_ng':divide(final['fn'],sum(truth)),'false_alarm_rate_over_all_ok':divide(final['fp'],len(truth)-sum(truth))},'single_model_rtdetr':binary_metrics(truth,[r['rtdetr_positive'] for r in rows]),'single_model_hvq':binary_metrics(truth,[r['hvq_positive'] for r in rows])}


def collect(env_file,pipeline,manifest):
    marker=pipeline/'FINAL_VALIDATION.json'
    if not marker.exists():return None
    try:verified=json.loads(marker.read_text())
    except json.JSONDecodeError:return None
    if verified.get('status')!='COMPLETED_AND_AGENT_VERIFIED':return None
    env=read_env_file(env_file);e=engine(env['DATABASE_URL_READ'],readonly=True)
    try:
        with e.connect().execution_options(isolation_level='REPEATABLE READ') as c:
            run=c.execute(text('''SELECT r.fusion_run_id,r.score_set_id,r.status,r.metadata,r.profile,s.binding,s.status AS score_status,s.completed_products,s.completed_views
              FROM fusion_analysis.model_runs r JOIN fusion_analysis.score_sets s USING(score_set_id) WHERE r.is_active''')).mappings().one_or_none()
            if run is None or run['status']!='COMPLETE' or run['score_status']!='COMPLETE' or run['fusion_run_id']!=verified['model_version']:return None
            if (run['completed_products'],run['completed_views'])!=(24000,120000):return None
            actual=c.execute(text('SELECT count(DISTINCT product_id),count(*) FROM fusion_analysis.view_scores WHERE score_set_id=:key'),{'key':run['score_set_id']}).one()
            if tuple(actual)!=(24000,120000):raise ValueError('Actual derived view completeness failed')
            bad=c.execute(text('''SELECT count(*) FROM (SELECT product_id FROM fusion_analysis.view_scores WHERE score_set_id=:key GROUP BY product_id HAVING count(*)<>5 OR count(DISTINCT camera)<>5) q'''),{'key':run['score_set_id']}).scalar_one()
            if bad:raise ValueError('Missing or duplicate camera records')
            rows=[dict(r) for r in c.execute(text('SELECT * FROM fusion_analysis.product_predictions WHERE fusion_run_id=:run ORDER BY product_id'),{'run':run['fusion_run_id']}).mappings()]
            if len(rows)!=24000 or len({r['product_id'] for r in rows})!=24000:raise ValueError('Actual fusion product completeness failed')
            if run['profile']['rtdetr_conf_threshold']!=.55 or run['profile']['hvq_score_variant']!='max_avgpool16' or run['profile']['weights']!={'rtdetr':.7,'hvq':.3}:raise ValueError('Wrong fusion contract')
            binding=run['binding']['source_binding']
            with manifest.open('rb') as f:manifest_sha=hashlib.file_digest(f,'sha256').hexdigest()
            if manifest_sha!=binding['manifest_sha256']:raise ValueError('Manifest identity mismatch')
            expected={}
            with manifest.open() as f:
                for r in csv.DictReader(f):expected[r['product_id']]={k:r[k] for k in ('category','split','truth')}
            if len(expected)!=24000 or set(expected)!={r['product_id'] for r in rows}:raise ValueError('Manifest/product identity mismatch')
            for r in rows:
                if any(r[k]!=expected[r['product_id']][k] for k in ('category','split','truth')):raise ValueError('Dataset GT/split mismatch')
                hv_th=run['profile']['hvq_thresholds'][r['category']]
                if r['rtdetr_positive']!=(r['rtdetr_raw']>=.55) or r['hvq_positive']!=(r['hvq_max16_raw']>=hv_th):raise ValueError('Component threshold mismatch')
                if not math.isclose(r['fusion_score'],.7*r['rt_percentile']+.3*r['hvq_percentile'],rel_tol=0,abs_tol=1e-10):raise ValueError('Weighted score mismatch')
                binary='defect' if r['fusion_score']>=r['threshold'] else 'normal'
                verdict='hold' if abs(r['fusion_score']-r['threshold'])<=r['margin'] else binary
                if r['binary_verdict']!=binary or r['verdict']!=verdict:raise ValueError('Verdict/hold mismatch')
            test=[r for r in rows if r['split']=='test'];expected_test={p for p,r in expected.items() if r['split']=='test'}
            if len(test)!=len(expected_test) or {r['product_id'] for r in test}!=expected_test:raise ValueError('Test completeness failed')
            overall=summarize(test)
            counts=c.execute(text('''SELECT count(*) FILTER(WHERE truth='normal' AND binary_verdict='defect') AS fp,
              count(*) FILTER(WHERE truth='defect' AND binary_verdict='normal') AS fn,
              count(*) FILTER(WHERE verdict='hold') AS hold FROM fusion_analysis.product_predictions WHERE fusion_run_id=:run AND split='test' '''),{'run':run['fusion_run_id']}).mappings().one()
            if (counts['fp'],counts['fn'],counts['hold'])!=(overall['binary_threshold']['fp'],overall['binary_threshold']['fn'],overall['final_with_hold']['hold_products']):raise ValueError('Independent SQL count mismatch')
            by_category={name:summarize([r for r in test if r['category']==name]) for name in sorted({r['category'] for r in test})}
            macro={}
            for key in ('f1','recall','miss_rate','false_alarm_rate','auroc','average_precision'):
                vals=[r['binary_threshold'][key] for r in by_category.values() if r['binary_threshold'][key] is not None];macro[key]=sum(vals)/len(vals) if vals else None
            proof=pipeline/'agent_numeric_validation.json'
            agent=json.loads(proof.read_text())
            if agent['status']!='PASSED' or agent['agent_tool']['model_version']!=run['fusion_run_id']:raise ValueError('Agent verification missing or stale')
            if agent['independent_sql']['binary_fp']!=counts['fp'] or agent['independent_sql']['binary_fn']!=counts['fn']:raise ValueError('Agent/SQL result mismatch')
            report={'status':'FINAL_COMPLETE','timestamp':datetime.datetime.now().astimezone().isoformat(),'model_version':run['fusion_run_id'],'scope':'existing_test_split_product_C1_C5','cohort_products':24000,'cohort_views':120000,'split_counts':dict(collections.Counter(r['split'] for r in rows)),'profile':dict(run['profile']),'test':overall,'category_macro':macro,'by_category':by_category,'database_read_only':True,'independent_sql_verified':True,'agent_tool_verified':True,'deployment_eligible':run['metadata']['deployment_eligible'],'training_overlap':run['metadata']['training_overlap'],'notes':['HOLD is deferred, not silently counted as correct or normal.','Primary metrics use only the existing test partition. Validation and train products are excluded.','Original model training overlap is not independently verified; this is not a claim of reproducing the teammate experiment.']}
            return report,rows,test
    finally:e.dispose()


def save_report(result,output):
    report,all_rows,test=result
    stamp=datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f');out=output/stamp;out.mkdir(parents=True,exist_ok=False)
    (out/'performance.json').write_text(json.dumps(report,indent=2,ensure_ascii=False))
    fields=['product_id','category','split','truth','rtdetr_raw','hvq_max16_raw','rtdetr_filtered','hvq_filtered','rt_percentile','hvq_percentile','rtdetr_positive','hvq_positive','fusion_score','threshold','margin','binary_verdict','verdict','source_attempt_id']
    selections={'all_predictions.csv':all_rows,'test_predictions.csv':test,'binary_fp.csv':[r for r in test if r['truth']=='normal' and r['binary_verdict']=='defect'],'binary_fn.csv':[r for r in test if r['truth']=='defect' and r['binary_verdict']=='normal'],'final_fp.csv':[r for r in test if r['truth']=='normal' and r['verdict']=='defect'],'final_fn.csv':[r for r in test if r['truth']=='defect' and r['verdict']=='normal'],'hold.csv':[r for r in test if r['verdict']=='hold']}
    for name,rows in selections.items():
        with (out/name).open('w',newline='') as f:
            w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows(rows)
    (output/'latest.json').write_text(json.dumps({'report':str(out/'performance.json'),'directory':str(out),'model_version':report['model_version']},indent=2))
    b=report['test']['binary_threshold'];h=report['test']['final_with_hold'];d=h['decided_only_metrics']
    print(json.dumps({'report':str(out/'performance.json'),'test_products':report['test']['products'],'binary_fp':b['fp'],'binary_fn':b['fn'],'recall':b['recall'],'f1_micro':b['f1'],'f1_category_macro':report['category_macro']['f1'],'auroc':b['auroc'],'final_fp':d['fp'],'final_fn':d['fn'],'hold':h['hold_products'],'coverage':h['coverage'],'agent_verified':True},ensure_ascii=False,indent=2))


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--env-file',type=Path,default=Path('/home/geonug/agent/.env'));p.add_argument('--pipeline',type=Path,default=BASE/'background_pipeline');p.add_argument('--manifest',type=Path,default=MV/'outputs/agent_integration_20261123_v1/inference_cohort_120000/manifest.csv');p.add_argument('--output',type=Path,default=BASE/'final_performance');p.add_argument('--wait',action='store_true');p.add_argument('--poll-seconds',type=int,default=60);a=p.parse_args()
    os.nice(10)
    while True:
        result=collect(a.env_file,a.pipeline,a.manifest)
        if result is not None:save_report(result,a.output);return 0
        if not a.wait:
            print('아직 전체 점수·DB 반영·에이전트 검증이 끝나지 않았습니다. --wait를 사용하세요.',file=sys.stderr);return 2
        for status_file in (a.pipeline/'supervisor_state.json',a.pipeline.parent/'max16_scores/state.json'):
            try:
                status=json.loads(status_file.read_text())
                if str(status.get('phase','')).startswith('BLOCKED') or status.get('failed_products',0):
                    print('백그라운드 작업에서 오류가 감지됐습니다. supervisor_state.json과 추론 로그를 확인하세요.',file=sys.stderr);return 3
            except (FileNotFoundError,json.JSONDecodeError):
                pass
        print(datetime.datetime.now().astimezone().isoformat()+' 최종 완료 대기 중',file=sys.stderr,flush=True)
        time.sleep(max(10,a.poll_seconds))

if __name__=='__main__':
    try:raise SystemExit(main())
    except KeyboardInterrupt:raise SystemExit(130)
    except Exception as exc:
        print(json.dumps({'status':'REPORT_FAILED','type':type(exc).__name__}),file=sys.stderr);raise SystemExit(1)
