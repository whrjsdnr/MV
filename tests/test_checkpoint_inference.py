"""추론 계약: 체크포인트 신원·클래스 범위·정상 후보와 미검출 구분. 합성 자료만 사용한다."""
import json,hashlib
import pytest
from scripts.inference.run_checkpoint import selected_checkpoint,status_from_detections


def test_reference_hash_and_bounds(tmp_path):
 weight=tmp_path/'state.pt';weight.write_bytes(b'synthetic');digest=hashlib.sha256(weight.read_bytes()).hexdigest()
 ref=tmp_path/'checkpoint.json';ref.write_text(json.dumps(dict(checkpoint_path=weight.name,sha256=digest,bytes=weight.stat().st_size)))
 pointer=tmp_path/'latest.json';pointer.write_text(json.dumps(dict(reference=ref.name,reference_sha256=hashlib.sha256(ref.read_bytes()).hexdigest())))
 p,metadata,actual=selected_checkpoint(pointer,None,None)
 assert p==weight and actual==digest and metadata['bytes']==9
 weight.write_bytes(b'changed')
 with pytest.raises(ValueError,match='SHA256'):selected_checkpoint(pointer,None,None)


def test_reference_cannot_escape_job(tmp_path):
 root=tmp_path/'job';root.mkdir();ref=root/'latest.json';ref.write_text(json.dumps(dict(reference='../other.json',reference_sha256='x')))
 with pytest.raises(ValueError,match='escapes'):selected_checkpoint(ref,None,None)


def test_direct_weights_require_explicit_hash(tmp_path):
 p=tmp_path/'state.pt';p.write_bytes(b'x')
 with pytest.raises(ValueError,match='required'):selected_checkpoint(None,p,None)


def test_normal_object_is_not_a_defect():
 classes={'battery/QS':0,'battery/OK':1}
 assert status_from_detections([1],[.9],classes,.25)['image_status']=='OK_CANDIDATE'
 assert status_from_detections([0,1],[.8,.9],classes,.25)['image_status']=='NG_CANDIDATE'


def test_no_detection_is_uncertain_not_normal():
 assert status_from_detections([],[],{'QS':0},.25)['image_status']=='NO_DETECTION_UNCERTAIN'
 assert status_from_detections([0],[.1],{'QS':0},.25)['displayed_objects']==0


@pytest.mark.parametrize('label,score',[(9,.5),(0,float('nan')),(0,1.1)])
def test_invalid_prediction_is_rejected(label,score):
 with pytest.raises(ValueError):status_from_detections([label],[score],{'QS':0},.25)
