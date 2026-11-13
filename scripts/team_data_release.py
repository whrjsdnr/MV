"""팀 배포 ZIP 생성·검증·실제 로딩·주석 변환 CLI. 모델 학습은 수행하지 않는다."""
from pathlib import Path
import argparse
import json
import os
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mv_analysis.data.team_release import TeamRelease, verify_release, extract_release, export_targets, save_json


def smoke(root, data_root):
    """품목/상태별 제품과 예외 상태를 뽑되 모든 C1~C5를 함께 로딩한다."""
    import torch
    from mv_analysis.data.datasets import FiveViewDataset
    from mv_analysis.data.adapters import get_adapter, SPECS
    from mv_analysis.data.collate import five_view_collate, single_view_collate, detection_collate
    torch.set_num_threads(1)
    release = TeamRelease(root, data_root)
    d = release.canonical
    # 표본 선택만 라벨을 사용한다. 전처리는 모든 상태에 동일한 저장 Crop을 적용한다.
    chosen = set(d.groupby(['category', 'status']).first().product_id)
    for fields in [['split', 'status'], ['mask_status'], ['selected_policy'], ['crop_review_status']]:
        chosen.update(d.groupby(fields).first().product_id)
    rereview = Path(root)/'validation/re_review_43.csv'
    if rereview.exists():
        import pandas as pd
        changed = pd.read_csv(rereview).image_id
        chosen.update(d.loc[d.image_id.isin(changed), 'product_id'])
    ids = d.loc[d.product_id.isin(chosen), 'image_id']
    native = release.dataset(image_ids=ids)
    shapes, states, contracts = [], {}, {}
    first = None
    for i, sample in enumerate(native):
        im = sample['image']
        assert im.dtype == torch.float32 and im.shape[0] == 3 and torch.isfinite(im).all()
        assert 0 <= im.min() <= im.max() <= 1
        assert sample['metadata']['content_hash_checked']
        if sample['mask'] is not None:
            assert sample['mask'].shape[-2:] == im.shape[-2:]
        if sample['status'] == 'NG' and sample['mask_status'] == 'MISSING':
            assert sample['mask'] is None and not sample['detection_trainable']
        if sample['detection_trainable']:
            detection_collate([sample])
        states[sample['mask_status']] = states.get(sample['mask_status'], 0)+1
        contracts[sample['detection_status']] = contracts.get(sample['detection_status'], 0)+1
        shapes.append(dict(image_id=sample['image_id'], shape=list(im.shape), boxes=len(sample['boxes']), mask_status=sample['mask_status']))
        if first is None:
            first = sample
            single_view_collate([sample])
        if (i+1) % 100 == 0:
            print(f'SMOKE native {i+1}/{len(native)}', flush=True)
    adapted = release.dataset(image_ids=ids, adapter=get_adapter('EfficientAD-S'))
    five = FiveViewDataset(adapted)
    for i in range(len(five)):
        group = five[i]
        assert group['images'].shape == (5, 3, 256, 256)
        assert group['views'] == ['C1', 'C2', 'C3', 'C4', 'C5']
    batch = five_view_collate([five[0], five[1]])
    assert batch['images'].shape == (2, 5, 3, 256, 256)
    adapters = {name: list(get_adapter(name)(first)['image'].shape) for name in SPECS}
    selected = d[d.image_id.isin(ids)]
    return dict(status='VERIFIED', canonical_sha256=release.sha256, images=len(native),
                products=len(five), categories=selected.category.nunique(), splits=sorted(selected.split.unique()),
                mask_states=states, annotation_states=contracts, policies=selected.selected_policy.value_counts().to_dict(),
                manual_review_status=selected.crop_review_status.value_counts().to_dict(),
                five_view_batch_shape=list(batch['images'].shape), adapter_shapes=adapters,
                sample_shapes=shapes, model_forward='NOT_RUN', model_training='NOT_RUN')


def main():
    """기존 파일을 덮어쓰지 않는다. 결과 JSON도 새로운 경로를 지정한다."""
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    build = sub.add_parser('build', help='관리자 전용: 승인·마스크 전수 검증 후 새 ZIP 생성')
    build.add_argument('--data-root', default=os.getenv('REALIAD_DATA_ROOT'))
    build.add_argument('--output', type=Path, default=Path('outputs/team_data_release_v1'))
    build.add_argument('--workers', type=int, default=2)
    build.add_argument('--max-batches', type=int)
    v2 = sub.add_parser('build-v2', help='검증된 v1 테이블 재사용, 원본 재분석 없이 정책 분리 v2 생성')
    v2.add_argument('--source-release',type=Path,required=True)
    v2.add_argument('--output',type=Path,required=True)
    verify = sub.add_parser('verify', help='해시·참조·클래스·좌표·Split·적격성 검증')
    choice = verify.add_mutually_exclusive_group(required=True)
    choice.add_argument('--release', type=Path)
    choice.add_argument('--zip', type=Path)
    verify.add_argument('--extract-to', type=Path)
    verify.add_argument('--sha256', help='별도 채널로 받은 신뢰할 수 있는 ZIP SHA-256')
    check = sub.add_parser('smoke', help='원본 실제 표본과 Single/Five-view 로더 검사')
    check.add_argument('--release', type=Path, required=True)
    check.add_argument('--data-root', default=os.getenv('REALIAD_DATA_ROOT'))
    export = sub.add_parser('export-targets', help='Crop 기준 YOLO/COCO 주석만 생성, 이미지 생성 없음')
    export.add_argument('--release', type=Path, required=True)
    export.add_argument('--output', type=Path, required=True)
    export.add_argument('--split', choices=['train', 'validation', 'test'], required=True)
    export.add_argument('--format', choices=['yolo', 'coco'], required=True)
    export.add_argument('--annotation-policy',choices=['defect_only','product_and_defect'],default='defect_only')
    export.add_argument('--evaluation-mode',choices=['independent','diagnostic'],default='independent')
    for cmd in [verify, check]:
        cmd.add_argument('--result', type=Path, help='기존 파일을 덮어쓰지 않는 검증 결과 경로')
    args = parser.parse_args()
    if getattr(args, 'result', None) and args.result.exists():
        parser.error('--result must be a new file')
    if args.command in ('build', 'smoke') and not args.data_root:
        parser.error('Set REALIAD_DATA_ROOT or --data-root')
    if args.command == 'build':
        from mv_analysis.data.release_builder import build_release
        build_release(Path(__file__).resolve().parents[1], args.data_root, args.output, args.workers, args.max_batches)
        return
    if args.command == 'build-v2':
        from mv_analysis.data.team_release_v2 import build_v2
        result=build_v2(args.source_release,args.output,Path(__file__).resolve().parents[1]/'docs/data/README_DATA_TEMPLATE.md')
        print(json.dumps(result,ensure_ascii=False,indent=2))
        return
    if args.command == 'verify':
        if args.zip and not args.extract_to:
            parser.error('--zip requires --extract-to (new folder)')
        root = extract_release(args.zip, args.extract_to, args.sha256) if args.zip else args.release
        result = verify_release(root)
    elif args.command == 'smoke':
        if json.loads((args.release/'release.json').read_text()).get('release_id')=='MV_TEAM_DATA_RELEASE_v2':
            from mv_analysis.data.release_smoke_v2 import smoke_v2
            result=smoke_v2(args.release,args.data_root,Path(args.result).parent/'figures' if args.result else None)
        else:result = smoke(args.release, args.data_root)
    else:
        if json.loads((args.release/'release.json').read_text()).get('release_id')=='MV_TEAM_DATA_RELEASE_v2':
            from mv_analysis.data.team_release_v2 import export_v2
            result=export_v2(args.release,args.output,split=args.split,format=args.format,annotation_policy=args.annotation_policy,evaluation_mode=args.evaluation_mode)
        else:
            if args.annotation_policy!='defect_only':parser.error('v1 does not support D2')
            result = export_targets(args.release, args.output, split=args.split, format=args.format)
    if getattr(args, 'result', None):
        args.result.parent.mkdir(parents=True, exist_ok=True)
        save_json(args.result, result)
    print(json.dumps({k:v for k,v in result.items() if k != 'sample_shapes'}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
