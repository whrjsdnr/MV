"""실행 상태와 Checkpoint 참조. 모델 가중치를 역직렬화하지 않고 SHA/계약만 확인한다."""
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import json
from pathlib import Path
import uuid
import csv

from mv_analysis.experiments.contracts import atomic_json, digest, file_sha256
from .settings import ROOT, read_json

CONTRACT_VERSION='mv-sequential-run-v1'
TERMINAL={'DRY_RUN_PASSED','SMOKE_PASSED','BLOCKED','FAILED','INTERRUPTED','PARTIAL','COMPLETED'}


def utc():
    return datetime.now(timezone.utc).isoformat()


def code_fingerprint():
    """Git HEAD만으로 미커밋 구현을 구분할 수 없어 실행기·설정 파일의 실제 해시도 고정한다."""
    paths=list((ROOT/'mv_analysis/training').glob('*.py'))
    paths+=list((ROOT/'models').rglob('*.py'))
    paths+=list((ROOT/'configs/training').glob('*.json'))
    paths+=[ROOT/'scripts/experiments/run_weekend.py',ROOT/'scripts/experiments/training_worker.py']
    return digest({p.relative_to(ROOT).as_posix():file_sha256(p) for p in paths if p.is_file()})


class RunStore:
    """plan은 불변, state는 원자 갱신, events는 추가 기록. 이미 실행 중이면 즉시 거부한다."""
    @classmethod
    def create(cls, output_root, plan):
        root=Path(output_root).expanduser().resolve()
        root.mkdir(parents=True,exist_ok=True)
        path=root/(datetime.now(timezone.utc).strftime('weekend_%Y%m%dT%H%M%S_')+uuid.uuid4().hex)
        path.mkdir()
        plan=dict(plan,contract_version=CONTRACT_VERSION,code_sha256=code_fingerprint(),run_id=path.name)
        atomic_json(path/'plan.json',plan,exclusive=True)
        atomic_json(path/'state.json',dict(status='CREATED',plan_sha256=file_sha256(path/'plan.json'),
            created_utc=utc(),jobs={k:dict(status='PENDING',attempts=[]) for k in plan['models']}),exclusive=True)
        return cls(path)

    def __init__(self,path):
        self.path=Path(path).expanduser().resolve()
        self.plan=read_json(self.path/'plan.json')
        self.state=read_json(self.path/'state.json')
        self.verify()

    def verify(self):
        if self.state['plan_sha256']!=file_sha256(self.path/'plan.json'):
            raise ValueError('Run plan was modified; create a new run')
        if self.plan['contract_version']!=CONTRACT_VERSION or self.plan['code_sha256']!=code_fingerprint():
            raise ValueError('Runner/config code changed; create a new run instead of unsafe resume')

    @contextmanager
    def lock(self):
        with (self.path/'.execution.lock').open('a') as f:
            try:
                fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError as e:
                raise RuntimeError('This run is already executing') from e
            try:
                self.state=read_json(self.path/'state.json')
                self.verify()
                yield
            finally:
                fcntl.flock(f,fcntl.LOCK_UN)

    def save(self):
        for key, job in self.state['jobs'].items():
            evidence=training_evidence(self.path/key)
            job.update(evidence)
        self.state['training_executed']=any(j.get('training_executed',False) for j in self.state['jobs'].values())
        self.state['updated_utc']=utc()
        atomic_json(self.path/'state.json',self.state)

    def event(self,kind,**details):
        with (self.path/'events.jsonl').open('a') as f:
            f.write(json.dumps(dict(time_utc=utc(),event=kind,**details),ensure_ascii=False,allow_nan=False)+'\n')
            f.flush()
            import os
            os.fsync(f.fileno())


def training_evidence(job_dir, *, include_legacy_history=False):
    """하위 진행 기록을 읽어 집계한다. 이전 실행 기록은 수정하지 않는다.

    강제 종료된 기존 YOLO는 run.json이 stale일 수 있어 명시적 감사에서만 CSV를 순회한다.
    운영 중에는 대규모 CSV 재스캔 없이 새 progress/기존 recorder 상태를 읽는다.
    """
    root=Path(job_dir); steps=0; executed=False; failures=[]; phases=[]
    for path in list(root.glob('training_progress.json'))+list(root.glob('*/training_progress.json')):
        data=read_json(path);executed |= bool(data.get('training_executed'))
        steps=max(steps,data.get('progress',{}).get('step',0));phases.append(data.get('status'))
        if data.get('error'): failures.append(dict(source=str(path),error=data['error'],traceback=data.get('traceback')))
    for path in list(root.glob('runs/*/run.json'))+list(root.glob('*/runs/*/run.json')):
        data=read_json(path);executed |= bool(data.get('training_executed'))
    for path in list(root.glob('checkpoint_*.json'))+list(root.glob('*/checkpoint_*.json')):
        data=read_json(path);steps=max(steps,data.get('global_step',0))
    for path in root.glob('attempt_*/response.json'):
        data=read_json(path);executed |= bool(data.get('training_executed'))
        if data.get('error'):failures.append(dict(source=str(path),error=data['error'],traceback=data.get('traceback')))
    if include_legacy_history:
        for path in list(root.glob('runs/*/training_history.csv'))+list(root.glob('*/runs/*/training_history.csv')):
            with path.open() as stream:
                for row in csv.DictReader(stream):
                    if row.get('phase')=='train':steps=max(steps,int(row['step']))
    return dict(training_executed=executed or steps>0,last_recorded_step=steps,
                training_phases=phases,training_failures=failures)


def checkpoint_bindings(request):
    """다른 모델/데이터/설정/환경의 Checkpoint를 자동 재사용하지 않는다."""
    return {k:request[k] for k in ('contract_version','model_key','settings_sha256','data_sha256',
                                  'environment_sha256','data_kind','code_sha256')}


def register_checkpoint(job_dir, checkpoint, request, *, epoch, global_step, state_fields):
    """백엔드가 원자 저장한 파일만 등록한다. epoch는 완료 epoch 수, global_step은 완료 update 수다."""
    job_dir=Path(job_dir).resolve(); checkpoint=Path(checkpoint)
    path=checkpoint.resolve()
    if checkpoint.is_symlink() or not path.is_relative_to(job_dir) or not path.is_file():
        raise ValueError('Checkpoint must be a regular file inside its job directory')
    if any(type(v) is not int or v<0 for v in (epoch,global_step)):
        raise ValueError('Invalid checkpoint progress')
    required={'model','optimizer','scheduler','rng','sampler','scaler','best_validation','progress'}
    if request['data_kind']=='REAL' and not required<=set(state_fields):
        raise ValueError('Real resume requires model/optimizer/scheduler/RNG/sampler/scaler/best/progress states')
    reference=dict(contract_version=CONTRACT_VERSION,bindings=checkpoint_bindings(request),
        checkpoint_path=path.relative_to(job_dir).as_posix(),sha256=file_sha256(path),bytes=path.stat().st_size,
        completed_epochs=epoch,global_step=global_step,state_fields=sorted(state_fields),created_utc=utc())
    ref=job_dir/('checkpoint_'+uuid.uuid4().hex+'.json')
    atomic_json(ref,reference,exclusive=True)
    # worker 종료 응답 전에 중단돼도 마지막 원자 저장 지점을 찾을 수 있다.
    atomic_json(job_dir/'checkpoint_latest.json',{'reference':ref.name,'reference_sha256':file_sha256(ref)})
    return ref


def validate_checkpoint(job_dir, reference, request):
    root=Path(job_dir).resolve(); reference=Path(reference)
    if reference.is_symlink() or not reference.resolve().is_relative_to(root):
        raise ValueError('Checkpoint reference escapes job directory')
    record=read_json(reference)
    if record['bindings']!=checkpoint_bindings(request):
        raise ValueError('Checkpoint settings/data/environment/kind mismatch')
    path=root/record['checkpoint_path']
    if path.is_symlink() or not path.resolve().is_relative_to(root) or not path.is_file():
        raise ValueError('Checkpoint path escapes job directory or is missing')
    if file_sha256(path)!=record['sha256'] or path.stat().st_size!=record['bytes']:
        raise ValueError('Checkpoint integrity failure')
    return record


def latest_checkpoint(job_dir):
    root=Path(job_dir).resolve();pointer=root/'checkpoint_latest.json'
    if not pointer.exists():
        return None
    item=read_json(pointer);ref=root/item['reference']
    if not ref.resolve().is_relative_to(root) or ref.is_symlink() or file_sha256(ref)!=item['reference_sha256']:
        raise ValueError('Latest checkpoint reference is corrupt')
    return str(ref)
