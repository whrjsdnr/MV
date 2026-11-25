"""순차 하위 프로세스 실행기. 실제 학습 백엔드는 아직 연결하지 않으며 실패를 성공으로 바꾸지 않는다."""
import argparse
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import traceback
import uuid
import psutil

from mv_analysis.experiments.contracts import atomic_json, digest, file_sha256
from .preflight import check_model, validate_data_release
from .settings import ROOT, MODELS, model_settings, select_models, python_path, read_json
from .state import RunStore, CONTRACT_VERSION, validate_checkpoint, latest_checkpoint, utc


def worker_command(python, request, response):
    """shell=False와 명시적 Python 경로를 사용한다. venv symlink를 resolve하지 않는다."""
    return [str(python),str(ROOT/'scripts/experiments/training_worker.py'),
            '--request',str(request),'--response',str(response)]


def execute_worker(command, log_path, *, timeout=None):
    """시간 초과/사용자 중단은 해당 하위 프로세스 그룹만 종료한다. 기존 서버·다른 Run은 건드리지 않는다."""
    started=time.monotonic()
    with Path(log_path).open('x') as log:
        proc=subprocess.Popen(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        lease_path=Path(log_path).parent/'worker_lease.json'
        lease=dict(pid=proc.pid,create_time=psutil.Process(proc.pid).create_time(),active=True)
        atomic_json(lease_path,lease,exclusive=True)
        try:
            return proc.wait(timeout=timeout)
        except (subprocess.TimeoutExpired,KeyboardInterrupt):
            os.killpg(proc.pid,signal.SIGTERM)
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid,signal.SIGKILL); proc.wait()
            raise
        finally:
            lease['active']=False
            atomic_json(lease_path,lease)
            log.write('\nrunner_elapsed_seconds='+str(time.monotonic()-started)+'\n')


def assert_no_live_worker(store):
    """부모만 종료되고 모델 worker가 남은 경우 중복 실행하지 않는다. 다른 PID는 종료하지 않는다."""
    for path in store.path.glob('*/attempt_*/worker_lease.json'):
        lease=read_json(path)
        if not lease['active']:
            continue
        try:
            process=psutil.Process(lease['pid'])
            if process.create_time()==lease['create_time'] and process.status()!=psutil.STATUS_ZOMBIE:
                raise RuntimeError(f'Worker still alive (PID {lease["pid"]}); resume refused')
        except psutil.NoSuchProcess:
            pass


def check_response(response, request, request_file, returncode):
    if response.get('request_sha256')!=file_sha256(request_file) or response.get('model_key')!=request['model_key']:
        raise ValueError('Stale or unrelated worker response')
    status=response.get('status')
    if status not in ('SMOKE_PASSED','BLOCKED','FAILED','INTERRUPTED','PARTIAL','COMPLETED'):
        raise ValueError('Unknown worker status')
    if (returncode==0)!=(status in ('SMOKE_PASSED','COMPLETED')):
        raise ValueError('Worker exit code/result contract mismatch')
    if status=='COMPLETED':
        report=Path(response.get('report',''))
        if request['mode']!='train' or not response.get('training_executed') or response.get('steps',0)<=0 or not report.is_file():
            raise ValueError('COMPLETED requires actual training and report evidence')
        if not report.resolve().is_relative_to(Path(request['job_dir']).resolve()) or file_sha256(report)!=response.get('report_sha256'):
            raise ValueError('Training report integrity mismatch')
    if request['mode']=='smoke' and response.get('training_executed') is not False:
        raise ValueError('Smoke must not train')
    if status=='SMOKE_PASSED' and request['mode']!='smoke':
        raise ValueError('Synthetic result cannot complete training')
    return response


def _new_plan(args):
    selected=select_models(args.profile,args.models)
    overrides=read_json(args.config) if args.config else {}
    if not isinstance(overrides,dict) or set(overrides)-set(selected):
        raise ValueError('--config must map selected model keys to override objects')
    mode='dry_run' if args.dry_run else 'smoke' if args.smoke else 'train'
    if mode=='smoke' and args.device not in (None,'auto','cpu'):
        raise ValueError('Runner synthetic smoke is CPU-only; CUDA validation belongs to future model smoke')
    configs={key:model_settings(key,overrides.get(key)) for key in selected}
    pythons={}; environment_scope={}
    for key in selected:
        env_key='MV_WEIGHTS_'+key.upper()
        if configs[key]['weights'] is None and os.environ.get(env_key):
            configs[key]['weights']=str(Path(os.environ[env_key]).expanduser().resolve())
        local_weight=configs[key].get('weights')
        if local_weight and Path(local_weight).is_file() and configs[key]['weights_sha256'] is None:
            # Resume 때 같은 경로의 가중치 내용이 바뀌어도 조용히 재사용하지 않는다.
            configs[key]['weights_sha256']=file_sha256(local_weight)
        path=python_path(key)
        if mode=='smoke' and not path.is_file() and 'MV_PYTHON_'+key.upper() not in os.environ:
            path=Path(sys.executable)
            environment_scope[key]='SHARED_ENV_SYNTHETIC_ONLY'
        else:
            environment_scope[key]='EXPLICIT_MODEL_PYTHON'
        pythons[key]=str(path)
    release=args.release_dir or os.environ.get('MV_DATA_RELEASE')
    data=args.data_root or os.environ.get('REALIAD_DATA_ROOT')
    return dict(models=selected,profile=args.profile,mode=mode,settings=configs,pythons=pythons,
        environment_scope=environment_scope,device='cpu' if mode=='smoke' or (args.profile=='owner' and args.device is None) else args.device or 'auto',
        release_source=str(Path(release).expanduser().resolve()) if release else None,
        data_root=str(Path(data).expanduser().resolve()) if data else None,
        expected_zip_sha256=args.release_sha256,continue_on_error=args.continue_on_error,
        max_hours=args.max_hours)


def _validate_resume_args(args, store):
    """Resume로 batch/device/model/data 정책을 바꾸지 않는다. 시간 예산만 새 세션에 다시 적용한다."""
    if args.config or args.profile or args.models or args.dry_run or args.smoke or args.release_sha256:
        raise ValueError('Use --resume RUN_DIR alone (plus --max-hours/--continue-on-error); do not change frozen settings')
    for attr,key in [('device','device'),('data_root','data_root'),('release_dir','release_source')]:
        value=getattr(args,attr)
        if value is not None:
            value=str(Path(value).expanduser().resolve()) if attr!='device' else value
            if value!=store.plan[key]:
                raise ValueError('Resume cannot change '+key)


def run(args):
    if args.max_hours is not None and (not math.isfinite(args.max_hours) or args.max_hours<=0):
        raise ValueError('--max-hours must be finite and positive')
    if args.resume:
        store=RunStore(args.resume); _validate_resume_args(args,store)
    else:
        plan=_new_plan(args)
        output=Path(args.output_root).expanduser().resolve()
        for protected in (plan['data_root'],plan['release_source']):
            if protected and output.is_relative_to(Path(protected)):
                raise ValueError('Output directory cannot be inside source data/release')
        store=RunStore.create(output,plan)
    plan=store.plan; mode=plan['mode']
    budget=args.max_hours if args.max_hours is not None else plan['max_hours']
    deadline=time.monotonic()+budget*3600 if budget else None
    keep_going=args.continue_on_error or plan['continue_on_error'] or mode=='dry_run'
    print('Run:',store.path,flush=True)
    with store.lock():
        assert_no_live_worker(store)
        if store.state['status']=='RUNNING':
            store.event('STALE_PROCESS_RECOVERED',previous_status='RUNNING')
            for job in store.state['jobs'].values():
                if job['status']=='RUNNING':
                    job['status']='INTERRUPTED'
                    if job['attempts']:
                        job['attempts'][-1].update(status='INTERRUPTED',reason='Previous worker did not finish')
        store.state['status']='RUNNING'; store.save()
        store.event('RESUMED' if args.resume else 'STARTED',mode=mode)
        try:
            release=None
            if plan['release_source']:
                print('Validating v2 release checksums/tables...',flush=True)
                release=validate_data_release(plan['release_source'],plan['data_root'],plan['expected_zip_sha256'])
            elif mode!='smoke':
                raise FileNotFoundError('Set --release-dir or MV_DATA_RELEASE to a v2 directory/ZIP')
            if mode!='smoke' and not plan['data_root']:
                raise FileNotFoundError('Set --data-root or REALIAD_DATA_ROOT')
            data_sha=release['bindings_sha256'] if release else digest('SYNTHETIC_NO_DATASET')
            if store.state.get('data_sha256') and store.state['data_sha256']!=data_sha:
                raise ValueError('Data release changed since this run; resume refused')
            store.state['data_sha256']=data_sha
            if release:
                evidence=store.path/('release_check_'+uuid.uuid4().hex+'.json')
                atomic_json(evidence,release,exclusive=True)
                store.state['latest_release_check']=str(evidence.relative_to(store.path))
            store.save()
            for position,key in enumerate(plan['models'],1):
                job=store.state['jobs'][key]
                if job['status'] in ('SMOKE_PASSED','COMPLETED','DRY_RUN_PASSED'):
                    print(f'[{position}/{len(plan["models"])}] {key}: already finished, preserved',flush=True)
                    continue
                if deadline and time.monotonic()>=deadline:
                    store.state['status']='PARTIAL';store.event('TIME_BUDGET_EXHAUSTED');break
                print(f'[{position}/{len(plan["models"])}] {key}: preflight',flush=True)
                job_dir=store.path/key;job_dir.mkdir(exist_ok=True)
                attempt_id=uuid.uuid4().hex
                attempt_dir=job_dir/('attempt_'+attempt_id);attempt_dir.mkdir()
                attempt=dict(id=attempt_id,status='RUNNING',path=str(attempt_dir.relative_to(store.path)),started_utc=utc())
                job['attempts'].append(attempt);job['status']='RUNNING';store.save()
                try:
                    check=check_model(plan['settings'][key],plan['pythons'][key],plan['device'],store.path,mode=mode)
                    atomic_json(attempt_dir/'preflight.json',check,exclusive=True)
                    if check['blockers']:
                        attempt.update(status='BLOCKED',reasons=check['blockers'])
                    else:
                        env_sha=check['environment']['identity_sha256']
                        if job.get('environment_sha256') and job['environment_sha256']!=env_sha:
                            raise ValueError('Model environment changed; resume requires a new run')
                        job['environment_sha256']=env_sha
                        if mode=='dry_run':
                            attempt['status']='DRY_RUN_PASSED'
                        else:
                            request=dict(contract_version=CONTRACT_VERSION,model_key=key,mode=mode,
                                data_kind='SYNTHETIC' if mode=='smoke' else 'REAL',
                                release_source=plan['release_source'],data_root=plan['data_root'],
                                settings=plan['settings'][key],settings_sha256=digest(plan['settings'][key]),
                                environment_sha256=env_sha,data_sha256=data_sha,code_sha256=plan['code_sha256'],
                                attempt_id=attempt_id,job_dir=str(job_dir),resume_checkpoint=latest_checkpoint(job_dir),
                                device=check['environment']['resolved_device'])
                            if request['resume_checkpoint']:
                                validate_checkpoint(job_dir,request['resume_checkpoint'],request)
                            request_file=attempt_dir/'request.json';response_file=attempt_dir/'response.json'
                            atomic_json(request_file,request,exclusive=True)
                            command=worker_command(plan['pythons'][key],request_file,response_file)
                            atomic_json(attempt_dir/'command.json',{'argv':command,'cwd':str(ROOT)},exclusive=True)
                            timeout=max(.001,deadline-time.monotonic()) if deadline else None
                            code=execute_worker(command,attempt_dir/'worker.log',timeout=timeout)
                            if not response_file.exists():
                                raise RuntimeError(f'Worker exited {code} without response; see worker.log')
                            result=check_response(read_json(response_file),request,request_file,code)
                            if result.get('checkpoint_reference'):
                                validate_checkpoint(job_dir,result['checkpoint_reference'],request)
                                job['checkpoint_reference']=result['checkpoint_reference']
                            attempt.update(status=result['status'],result=result,returncode=code)
                except subprocess.TimeoutExpired as e:
                    attempt.update(status='INTERRUPTED',error='TIME_LIMIT',error_type=type(e).__name__)
                except KeyboardInterrupt:
                    attempt.update(status='INTERRUPTED',error='USER_INTERRUPT')
                    job['status']='INTERRUPTED';store.save();raise
                except Exception as e:
                    attempt.update(status='FAILED',error=str(e),error_type=type(e).__name__)
                    atomic_json(attempt_dir/'error.json',dict(error=str(e),traceback=traceback.format_exc()),exclusive=True)
                attempt['finished_utc']=utc();job['status']=attempt['status'];store.save()
                store.event('JOB_FINISHED',model=key,status=job['status'],attempt=attempt_id)
                print(f'{key}: {job["status"]}',flush=True)
                if job['status'] not in ('SMOKE_PASSED','COMPLETED','DRY_RUN_PASSED') and not keep_going:
                    break
            statuses=[j['status'] for j in store.state['jobs'].values()]
            success='SMOKE_PASSED' if mode=='smoke' else 'DRY_RUN_PASSED' if mode=='dry_run' else 'COMPLETED'
            if all(s==success for s in statuses):store.state['status']=success
            elif 'FAILED' in statuses:store.state['status']='FAILED'
            elif 'INTERRUPTED' in statuses:store.state['status']='INTERRUPTED'
            elif 'BLOCKED' in statuses:store.state['status']='BLOCKED'
            else:store.state['status']='PARTIAL'
        except KeyboardInterrupt:
            store.state['status']='INTERRUPTED';store.event('USER_INTERRUPT')
        except Exception as e:
            store.state['status']='BLOCKED' if isinstance(e,FileNotFoundError) else 'FAILED'
            store.event('PREPARATION_ERROR',error=str(e),error_type=type(e).__name__,traceback=traceback.format_exc())
            store.state['last_error']=str(e)
        store.save();store.event('SESSION_FINISHED',status=store.state['status'])
    return store


def parser():
    p=argparse.ArgumentParser(description='6개 모델 순차 실행 계약. Owner 실제 Backend 지원, teammate는 미구현. --smoke는 합성 실행기 검증입니다.')
    selection=p.add_mutually_exclusive_group()
    selection.add_argument('--profile',choices=['owner','teammate']);selection.add_argument('--models',nargs='+',choices=list(MODELS))
    p.add_argument('--device',choices=['auto','cpu','cuda']+[f'cuda:{i}' for i in range(16)])
    p.add_argument('--data-root');p.add_argument('--release-dir',help='v2 배포 디렉터리 또는 ZIP')
    p.add_argument('--release-sha256');p.add_argument('--config',help='모델 키별 JSON 설정 override')
    p.add_argument('--output-root',default='outputs/weekend_runs')
    modes=p.add_mutually_exclusive_group();modes.add_argument('--dry-run',action='store_true');modes.add_argument('--smoke',action='store_true')
    p.add_argument('--resume',metavar='RUN_DIR');p.add_argument('--max-hours',type=float)
    p.add_argument('--continue-on-error',action='store_true')
    return p


def main(argv=None):
    p=parser();args=p.parse_args(argv)
    try:
        store=run(args)
    except (ValueError,RuntimeError,OSError) as e:
        p.error(str(e))
    status=store.state['status']
    print(json.dumps({'run_dir':str(store.path),'status':status,'training_executed':store.state.get('training_executed',False)},ensure_ascii=False))
    return 0 if status in ('SMOKE_PASSED','DRY_RUN_PASSED','COMPLETED') else 130 if status=='INTERRUPTED' else 1 if status=='FAILED' else 2
