"""현재 프로젝트의 Owner 3개 모델을 CPU 50 epoch/batch 1로 순차 실행한다."""
import argparse
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from mv_analysis.training.runner import main as run_weekend
from mv_analysis.training.settings import model_settings, PROFILES


def command(args):
    """경로만 기본 제공한다. 실제 Crop/Manifest/Split은 v2 검증기로 확인한다."""
    if args.resume:
        result=['--resume',str(args.resume)]
    else:
        for key in PROFILES['owner']:
            cfg=model_settings(key)
            if cfg['epochs']!=50 or cfg['batch_size']!=1 or cfg['max_steps'] is not None:
                raise ValueError('Owner CPU launcher requires epochs=50, batch_size=1, max_steps=null')
        result=['--profile','owner','--device','cpu','--data-root',str(args.data_root),
                '--release-dir',str(args.release_dir),'--output-root',str(args.output_root)]
        if args.dry_run: result.append('--dry-run')
        if args.smoke: result.append('--smoke')
    if args.max_hours is not None: result += ['--max-hours',str(args.max_hours)]
    result.append('--continue-on-error')
    return result


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--data-root',type=Path,default=os.environ.get('REALIAD_DATA_ROOT',ROOT/'dataset'))
    p.add_argument('--release-dir',type=Path,default=os.environ.get('MV_DATA_RELEASE',ROOT/'outputs/team_data_release_v2/MV_TEAM_DATA_RELEASE_v2'))
    p.add_argument('--output-root',type=Path,default=ROOT/'outputs/owner_cpu_training')
    mode=p.add_mutually_exclusive_group();mode.add_argument('--dry-run',action='store_true');mode.add_argument('--smoke',action='store_true');mode.add_argument('--resume',type=Path)
    p.add_argument('--max-hours',type=float)
    args=p.parse_args(argv)
    return run_weekend(command(args))


if __name__=='__main__':raise SystemExit(main())
