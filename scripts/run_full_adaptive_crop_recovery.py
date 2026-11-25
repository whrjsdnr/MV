"""전수 특징 추출이 끝나면 자동 Crop CSV·사후 감사·수동 검수 큐·보고서를 순서대로 생성한다.

기존 데이터/원장/릴리스/모델 Run은 건드리지 않는다. 계산 오류를 성공으로 바꾸지 않는다.
"""
from pathlib import Path
import argparse,csv,fcntl,hashlib,json,os,subprocess,sys,time,traceback
ROOT=Path(__file__).resolve().parents[1]


def atomic(path,data):
 temp=path.with_suffix('.tmp');temp.write_text(json.dumps(data,indent=2,ensure_ascii=False,allow_nan=False));os.replace(temp,path)


def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--output',type=Path,required=True);p.add_argument('--features',type=Path,required=True)
 p.add_argument('--wait-features',action='store_true',help='이미 별도로 시작한 특징 추출의 완료를 기다림')
 p.add_argument('--resume',action='store_true');p.add_argument('--workers',type=int,choices=[1,2,3],default=2)
 args=p.parse_args();out=args.output.resolve();features=args.features.resolve();out.mkdir(parents=True,exist_ok=True)
 state_path=out/'pipeline_state.json'
 if state_path.exists() and not args.resume:raise FileExistsError('Use --resume; preserve existing pipeline state')
 state=json.loads(state_path.read_text()) if state_path.exists() else dict(status='CREATED',features=str(features),output=str(out),started_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()))
 def mark(phase,**kw):
  state.update(status='RUNNING',phase=phase,updated_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),**kw);atomic(state_path,state)
 def run(name,argv):
  log=out/(name+'_'+str(time.time_ns())+'.log')
  with log.open('x') as stream:subprocess.run([sys.executable,*argv],cwd=ROOT,env=dict(os.environ,OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1'),stdout=stream,stderr=subprocess.STDOUT,check=True)
 with (out/'pipeline.lock').open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  try:
   mark('WAITING_FEATURES' if args.wait_features else 'COMPUTING_FEATURES')
   if args.wait_features:
    # 같은 run.lock을 확인하여 선행 작업이 끝나기 전에 변경 중인 캐시를 읽지 않는다.
    while True:
     with (features/'run.lock').open('a') as feature_lock:
      try:fcntl.flock(feature_lock,fcntl.LOCK_EX|fcntl.LOCK_NB);released=True
      except BlockingIOError:released=False
     progress=json.loads((features/'progress.json').read_text())
     mark('WAITING_FEATURES',feature_progress=progress)
     if released:
      if not progress.get('full_processing_complete'):raise RuntimeError('Feature worker stopped before full coverage; resume feature worker then pipeline')
      break
     time.sleep(30)
   else:
    run('compute_features',['scripts/compute_missing_crop_features.py','--output',str(features),'--resume','--workers',str(args.workers)])
   mark('BUILDING_APPLIED_MANIFEST')
   metadata=out/'full_metadata'
   if not (metadata/'validation.json').exists():
    if metadata.exists():
     metadata=out/('full_metadata_retry_'+str(time.time_ns()))
    state['metadata_dir']=str(metadata)
    command=['scripts/rebuild_preprocessing_metadata.py','--output',str(metadata),'--additional-features',str(features),'--apply-auto','--rule','image_gate']
    preview=out/'preview_ready'
    if (preview/'manual_crop_review_ledger.jsonl').exists():
     command+=['--review-overlay',str(preview/'manual_crop_review_ledger.jsonl'),str(preview/'preprocessing_metadata_applied.csv')]
    if (out/'user_confirmed_reference_overrides.json').exists():
     command+=['--reference-overrides',str(out/'user_confirmed_reference_overrides.json')]
    run('build_manifest',command)
   else:state['metadata_dir']=str(metadata)
   mark('POST_CROP_AUDIT')
   if not (metadata/'post_crop_audit_validation.json').exists():
    run('audit',['scripts/audit_applied_crop_and_prepare_review.py','--directory',str(metadata),'--resume','--features-complete'])
   summary=json.loads((metadata/'post_crop_audit_validation.json').read_text());validation=json.loads((metadata/'validation.json').read_text())
   if summary['images']!=151050 or validation['images']!=151050:raise ValueError('Full coverage row mismatch')
   mark('REPORTING',post_crop_audit=summary)
   report=out/'FULL_ADAPTIVE_CROP_APPLICATION.md'
   report.write_text('# 전체 자동 Crop 적용 및 수동 검수 요청\n\n'
    +'자동 좌표를 적용하고 사후 GT/마스크 손실을 검수 큐에 분리했다. 사람 승인과 자동 추정은 구분한다.\n\n'
    +f'- 전체 이미지: {summary["images"]:,}\n- 정책 분포: {validation["final_policy_counts"]}\n'
    +f'- 결함 마스크 손실 이미지: {summary["mask_loss_images"]:,}\n- 제품 GT BBox 손실 이미지: {summary["product_gt_loss_images"]:,}\n'
    +f'- 필수 검수: {summary["required_review_images"]:,}\n- 이미지 기반 추가 검수 권장: {summary["recommended_review_images"]:,}\n'
    +f'- 최종 전처리 CSV: `{metadata}/preprocessing_metadata_applied.csv`\n'
    +f'- 필수 검수 CSV: `{metadata}/manual_review_required.csv`\n\n'
    +'## 수동 검수 실행\n\n```bash\n'
    +f'uv run --offline python scripts/review_crop_ranges.py --metadata {metadata}/preprocessing_metadata_applied.csv --queue {metadata}/manual_review_required.csv --ledger {metadata}/manual_crop_review_ledger.jsonl --port 8773\n```\n\n'
    +'브라우저 http://127.0.0.1:8773 에서 범위를 수정·보존 점검·승인 후 새 CSV 내보내기를 실행한다. 기존 승인 기록은 보존된다.\n\n'
    +'제품 GT가 없는 이미지의 제품 보존은 UNVERIFIED다. 위험을 찾지 못한 사실을 제품 전체 보존의 증명으로 해석하지 않는다. 기존 학습 Manifest/데이터 ZIP은 자동 교체하지 않았다.\n')
   state.update(status='COMPLETED_WITH_MANUAL_REVIEW_REQUIRED',phase='COMPLETE',report=str(report),applied_csv=summary['applied_csv'],completed_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()));atomic(state_path,state)
  except BaseException as exc:
   state.update(status='INTERRUPTED' if isinstance(exc,KeyboardInterrupt) else 'FAILED',error=repr(exc),traceback=traceback.format_exc());atomic(state_path,state);raise


if __name__=='__main__':main()
