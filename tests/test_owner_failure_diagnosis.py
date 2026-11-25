"""실패를 숨기지 않는 calibration·loss·target·상태 집계 및 검증 전 복구 회귀 검사."""
import json
from pathlib import Path
import pytest
import torch
from models._shared.diagnostics import checked_losses,tensor_stats,sample_evidence
from models.anomaly.efficientad_s.backend import calibration_quantiles,CalibrationError
from models.detection.retinanet.preprocessing import prepare_batch
from mv_analysis.training.state import training_evidence


def test_calibration_matches_pinned_quantiles():
    maps={'st':torch.arange(1000,dtype=torch.float32),'ae':torch.linspace(.1,1,1000)}
    q,stats=calibration_quantiles(maps)
    assert torch.equal(q,torch.cat([torch.quantile(v,torch.tensor([.9,.995])) for v in maps.values()]))
    assert all(v['valid'] for v in stats.values())


@pytest.mark.parametrize('values',[torch.ones(100),torch.empty(0),torch.tensor([1.,float('nan')]),torch.tensor([1.,float('inf')])])
def test_calibration_rejects_degenerate_without_epsilon(values):
    with pytest.raises(CalibrationError) as result:
        calibration_quantiles({'st':values,'ae':torch.arange(10,dtype=torch.float32)})
    assert not result.value.diagnostics['st']['valid']
    json.dumps(result.value.diagnostics,allow_nan=False)


def test_tied_upper_tail_is_not_silently_accepted():
    with pytest.raises(CalibrationError):
        calibration_quantiles({'st':torch.cat([torch.zeros(5),torch.ones(95)])})


@pytest.mark.parametrize('invalid',[float('nan'),float('inf'),-float('inf')])
def test_nonfinite_component_identified(invalid):
    with pytest.raises(FloatingPointError,match='bbox_regression'):
        checked_losses({'classification':torch.tensor(1.),'bbox_regression':torch.tensor(invalid)})
    assert tensor_stats(torch.tensor(invalid))['nonfinite']==1


def sample():
    return dict(image_id='sample',metadata={'image_policy':'original_full'},detection_trainable=True,
                image=torch.zeros(3,16,16),boxes=torch.empty(0,4),labels=torch.empty(0,dtype=torch.int64))


def test_empty_ok_target_valid():
    _,targets=prepare_batch([sample()],'cpu')
    assert targets[0]['boxes'].shape==(0,4)


@pytest.mark.parametrize('boxes',[[[1.,1.,1.,2.]],[[0.,0.,17.,2.]],[[float('nan'),1.,2.,3.]],[[1.,1.,2.,float('inf')]]])
def test_invalid_target_fails_without_clipping(boxes):
    s=sample();s.update(boxes=torch.tensor(boxes),labels=torch.tensor([0]))
    with pytest.raises(ValueError,match='XYXY'):prepare_batch([s],'cpu')


def test_nan_image_rejected():
    s=sample();s['image'][0,0,0]=float('nan')
    with pytest.raises(ValueError,match='unnormalized'):prepare_batch([s],'cpu')


def test_invalid_coordinates_can_still_be_written_as_failure_evidence():
    s=sample();s['boxes']=torch.tensor([[float('nan'),0,1,1]])
    evidence=sample_evidence([s])
    json.dumps(evidence,allow_nan=False)
    assert evidence[0]['boxes'][0][0] is None
    assert torch.isnan(s['boxes'][0,0])  # 진단 JSON 처리만 하며 원본 Target은 보정하지 않는다.


def test_retina_empty_and_positive_anchor_diagnostics():
    from models.detection.retinanet.backend import Backend
    from mv_analysis.training.settings import model_settings
    torch.set_num_threads(1)
    backend=Backend(model_settings('retinanet',{'input_resolution':64}),{'AK':0},'cpu')
    s=sample();s['image']=torch.zeros(3,64,64)
    backend.model.train(); losses=backend.loss([s])
    assert losses['bbox_regression']==0
    assert backend.last_diagnostics['anchors'][0]['positive']==0
    s.update(boxes=torch.tensor([[8.,8.,32.,32.]]),labels=torch.tensor([0]))
    losses=backend.loss([s])
    assert torch.isfinite(checked_losses(losses))
    assert backend.last_diagnostics['anchors'][0]['positive']>0


def test_failed_child_training_aggregated(tmp_path):
    folder=tmp_path/'category';folder.mkdir()
    (folder/'training_progress.json').write_text(json.dumps(dict(status='FAILED',training_executed=True,
        progress={'step':3},error='CALIBRATION',traceback='trace')))
    ev=training_evidence(tmp_path)
    assert ev['training_executed'] and ev['last_recorded_step']==3
    assert ev['training_failures'][0]['traceback']=='trace'


def test_stale_yolo_recorder_checkpoint_and_history(tmp_path):
    run=tmp_path/'runs/r1';run.mkdir(parents=True)
    (run/'run.json').write_text('{"training_executed":false}')
    (tmp_path/'checkpoint_1.json').write_text('{"global_step":7}')
    (run/'training_history.csv').write_text('phase,step\ntrain,8\n')
    assert training_evidence(tmp_path)['last_recorded_step']==7
    assert training_evidence(tmp_path,include_legacy_history=True)['last_recorded_step']==8


def test_calibration_failure_preserves_pending_snapshot_and_resume(tmp_path,monkeypatch):
    """runtime 자체에서 실패 전 저장 및 재개 시 update 중복 방지를 검증한다."""
    from models._shared import runtime
    from mv_analysis.training.state import CONTRACT_VERSION,latest_checkpoint
    class Recorder:
        state={'status':'RUNNING'}
        path=tmp_path/'fake_report'
        @classmethod
        def create(cls,*a,**k):return cls()
        def start(self):return self
        def artifact(self,*a,**k):pass
        def log(self,*a,**k):pass
        def finalize(self,status,**kw):self.state={'status':status}
    class Backend:
        model=torch.nn.Linear(1,1)
        calls=0
        def prepare(self,train):pass
        def loss(self,samples):
            self.calls+=1
            return {'loss':self.model(torch.ones(1,1)).square().sum()}
        def calibrate_maps(self,validation):raise ValueError('forced calibration failure')
    cfg=dict(optimizer='SGD',learning_rate=.01,weight_decay=0.,scheduler='MultiStepLR',step_size=[10],gamma=.1,
        batch_size=1,epochs=1,max_steps=None,mixed_precision=False,seed=42,gradient_clip=None)
    request=dict(settings=cfg,settings_sha256='s',job_dir=str(tmp_path),device='cpu',contract_version=CONTRACT_VERSION,
        model_key='retinanet',data_sha256='d',environment_sha256='e',data_kind='REAL',code_sha256='c')
    monkeypatch.setattr(runtime,'ExperimentRecorder',Recorder)
    monkeypatch.setattr(runtime,'recorder_config',lambda *a:{})
    monkeypatch.setattr(runtime,'generate_experiment_report',lambda *a:None)
    backend=Backend();data={'train':[sample()],'validation':[]}
    with pytest.raises(ValueError,match='forced'):runtime.train_torch(request,None,data,backend,suffix='D1')
    folder=tmp_path/'D1';ref=json.loads(Path(latest_checkpoint(folder)).read_text())
    state=torch.load(folder/ref['checkpoint_path'],weights_only=True)
    assert state['progress']=={'epoch':0,'batch':1,'step':1,'phase':'calibration_pending'}
    assert backend.calls==1
    with pytest.raises(ValueError,match='forced'):runtime.train_torch(request,None,data,backend,suffix='D1')
    assert backend.calls==1  # 검증만 재시도하며 이미 완료한 학습을 반복하지 않는다.
