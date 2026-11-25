"""원본 좌표 공통 평가기/시각화 연결. Test의 threshold는 Validation에서만 결정한다."""
from pathlib import Path
import cv2
from mv_analysis.experiments.bridge import ground_truth_records
from mv_analysis.experiments.anomaly import calibrate_anomaly, evaluate_anomaly, binary_metrics
from mv_analysis.experiments.detection import calibrate_detection, evaluate_detection
from mv_analysis.experiments.recorder import load_predictions
from mv_analysis.experiments.visualization import visualize_anomaly, visualize_detection


def ground_truth(dataset, family):
    return ground_truth_records(dataset.index, dataset.index.data.image_id.tolist(),
        scope='canonical_crop' if family=='anomaly' else 'full_original', lazy=True)


def evaluate(family, gt, predictions, classes, *, split, policy=None):
    if family == 'anomaly':
        policy = policy or calibrate_anomaly(gt, predictions, data_kind='REAL')
        result = evaluate_anomaly(gt, predictions, policy, split=split, data_kind='REAL')
    else:
        policy = policy or calibrate_detection(gt, predictions, classes, data_kind='REAL')
        result = evaluate_detection(gt, predictions, classes, policy, split=split, data_kind='REAL')
    by_id={p['image_id']:p for p in predictions}
    threshold=policy.image if family=='anomaly' else policy.detection
    image_scores=[by_id[g['image_id']]['score'] if family=='anomaly'
                  else max(by_id[g['image_id']]['scores'],default=-1.) for g in gt]
    image_status=binary_metrics([int(g['status']=='NG') for g in gt],image_scores,threshold)
    tn,fp=image_status.get('tn',0),image_status.get('fp',0)
    tp,fn=image_status.get('tp',0),image_status.get('fn',0)
    image_status.update(ok_recall=tn/(tn+fp) if tn+fp else None,
                        ng_recall=tp/(tp+fn) if tp+fn else None,
                        scope='FROZEN_ELIGIBLE_IMAGE_COHORT',
                        no_detection_score=-1 if family=='detection' else None,
                        threshold_rule='Validation anomaly F1' if family=='anomaly' else 'Validation box F1 threshold, max predicted confidence')
    result['image_status']=image_status
    return result, policy


def save_examples(backend, dataset, gt, policy, recorder, *, limit=6):
    """실제 예측만 내부 Run에 저장한다. GT 미제공은 공통 시각화의 제외 표시를 유지한다."""
    truth = {r['image_id']:r for r in gt}
    directory = recorder.path/'figures'
    directory.mkdir(exist_ok=True)
    for i in range(min(limit,len(dataset))):
        sample = dataset[i]
        row = dataset.index.data.iloc[i].to_dict()
        image = cv2.imread(str(dataset.index.source_path(row)))
        if image is None:
            raise ValueError('Cannot decode visualization original')
        image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        prediction = backend.predict(sample)
        output = directory/f'actual_{sample["split"]}_{i:03d}.png'
        if backend.config['model_family']=='anomaly':
            visualize_anomaly(image, truth[sample['image_id']], prediction,
                model_name=backend.config['model_name'], threshold=policy.pixel, output=output, data_kind='REAL')
        else:
            visualize_detection(image, truth[sample['image_id']], prediction, backend.classes, policy,
                model_name=backend.config['model_name'], output=output, data_kind='REAL')


def final_evaluation(backend, data, recorder):
    policy = None
    for split in ('validation','test'):
        gt = ground_truth(data[split], backend.config['model_family'])
        # NPY sidecar에 즉시 스트리밍한다. 수만 장의 1024² 맵을 RAM에 모으지 않는다.
        recorder.predictions(backend.predict(sample) for sample in data[split])
        predictions = [p for p in load_predictions(recorder.path) if p['split']==split]
        result, policy = evaluate(backend.config['model_family'],gt,predictions,backend.classes,
                                  split=split,policy=policy)
        recorder.evaluation(split,result)
        save_examples(backend,data[split],gt,policy,recorder)
