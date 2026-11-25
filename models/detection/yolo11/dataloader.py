"""원본은 복사·수정하지 않고 Run 내부 symlink와 Label/YAML만 생성한다."""
from pathlib import Path
import yaml
from models._shared.data import datasets
from .preprocessing import label_lines


def build_datasets(release, config):
    return datasets(release, config)


def export_dataset(data, classes, destination):
    destination=Path(destination).resolve(); destination.mkdir(exist_ok=False)
    for split, dataset in data.items():
        images=destination/'images'/split; labels=destination/'labels'/split
        images.mkdir(parents=True);labels.mkdir(parents=True)
        for row in dataset.data.to_dict('records'):
            image_id=row['image_id']
            if Path(image_id).name!=image_id: raise ValueError('Unsafe image ID')
            source=dataset.index.source_path(row)
            boxes, ids=dataset.index.boxes.get(row['source_relative_path'],([],[]))
            if row['status']=='OK' and len(boxes): raise ValueError('OK has defect annotation')
            if row['status']=='NG' and not len(boxes): raise ValueError('Unannotated NG in YOLO export')
            (images/(image_id+source.suffix)).symlink_to(source)
            (labels/(image_id+'.txt')).write_text(label_lines(boxes,ids,row['original_width'],row['original_height']))
    path=destination/'dataset.yaml'
    path.write_text(yaml.safe_dump(dict(path=str(destination),train='images/train',val='images/validation',
        test='images/test',names={v:k for k,v in classes.items()}),sort_keys=False))
    return path
