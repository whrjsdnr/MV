"""모델별 Python에서 실행되는 공통 계약 worker. Owner 모델 구현은 models/로 위임한다."""
import argparse
from pathlib import Path
import traceback

from mv_analysis.experiments.contracts import atomic_json, digest, file_sha256
from .settings import MODELS, read_json, validate_settings
from .state import CONTRACT_VERSION, register_checkpoint, validate_checkpoint, code_fingerprint
from .state import training_evidence


def validate_request(request):
    if request.get('contract_version')!=CONTRACT_VERSION or request.get('model_key') not in MODELS:
        raise ValueError('Unsupported worker request')
    if request['mode'] not in ('smoke','train'):
        raise ValueError('Worker only accepts smoke/train')
    if request['data_kind']!=('SYNTHETIC' if request['mode']=='smoke' else 'REAL'):
        raise ValueError('Synthetic/real request mismatch')
    if request['mode']=='smoke' and request['device']!='cpu':
        raise ValueError('Synthetic runner smoke must use CPU')
    validate_settings(request['settings'])
    if request['settings']['model_key']!=request['model_key'] or digest(request['settings'])!=request['settings_sha256']:
        raise ValueError('Worker settings hash/model mismatch')
    if request['code_sha256']!=code_fingerprint():
        raise ValueError('Worker code differs from frozen runner')


def smoke(request, job_dir):
    """공식 모델 대신 CPU 텐서 연산·Recorder·Checkpoint 검증만 실행한다. backward도 하지 않는다."""
    import torch
    from mv_analysis.experiments.demo import example_config
    from mv_analysis.experiments.recorder import ExperimentRecorder
    from mv_analysis.experiments.reports import generate_experiment_report
    torch.set_num_threads(1)
    restored=None
    if request.get('resume_checkpoint'):
        restored=validate_checkpoint(job_dir,request['resume_checkpoint'],request)
    config=example_config(MODELS[request['model_key']])
    config['experiment_id']='weekend-runner-contract-smoke'
    config['reproduce_command']='uv run --offline python scripts/experiments/run_weekend.py --models '+request['model_key']+' --smoke'
    recorder=ExperimentRecorder.create(job_dir/'recorder',config).start()
    try:
        value=float(torch.tensor([1.,2.,3.]).square().mean())
        recorder.artifact('runner_smoke.json',dict(scope='SYNTHETIC_RUNNER_ONLY',tensor_value=value,
            official_model_executed=False,training_executed=False,resume_reference_checked=bool(restored)))
        payload=job_dir/('synthetic_state_'+request['attempt_id']+'.json')
        atomic_json(payload,dict(data_kind='SYNTHETIC',tensor_value=value,model_weights=False),exclusive=True)
        ref=register_checkpoint(job_dir,payload,request,epoch=0,global_step=0,state_fields=['synthetic_contract_only'])
        validate_checkpoint(job_dir,ref,request)
        recorder.finalize('PARTIAL',training_executed=False,evidence={'scope':'RUNNER_CONTRACT_ONLY'})
        report=generate_experiment_report(recorder.path)
        return dict(status='SMOKE_PASSED',checkpoint_reference=str(ref),report=str(report),
                    official_model_executed=False,training_executed=False)
    except BaseException:
        if recorder.state['status']=='RUNNING':
            recorder.finalize('FAILED',training_executed=False)
        raise


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request',required=True); parser.add_argument('--response',required=True)
    args=parser.parse_args(argv)
    response=Path(args.response)
    if response.exists():
        raise FileExistsError('Preserve existing worker response: '+str(response))
    request=read_json(args.request)
    result=dict(request_sha256=file_sha256(args.request),model_key=request.get('model_key'),training_executed=False)
    try:
        validate_request(request)
        if request['mode']=='train':
            from .backends import run_backend
            result.update(run_backend(request))
        else:
            result.update(smoke(request,Path(request['job_dir'])))
        code=0 if result['status'] in ('SMOKE_PASSED','COMPLETED') else 2
    except Exception as e:
        result.update(status='FAILED',error_type=type(e).__name__,error=str(e),traceback=traceback.format_exc())
        code=1
    except KeyboardInterrupt:
        result.update(status='INTERRUPTED',error='USER_INTERRUPT',traceback=traceback.format_exc())
        code=130
    if request.get('mode')=='train':
        evidence=training_evidence(request['job_dir'],include_legacy_history=True)
        result.update(evidence)
    atomic_json(response,result,exclusive=True)
    return code
