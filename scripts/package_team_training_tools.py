"""검증된 Git Clone에 추가할 작은 학습 도구 Overlay를 만든다. 기존 소스/ZIP은 변경하지 않는다."""
import argparse
from datetime import datetime,timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import zipfile

ROOT=Path(__file__).resolve().parents[1]
PACKAGE='MV_TEAMMATE_TRAINING_TOOLS_v1'
STATUS={'Common Runner':'VERIFIED','Data v2 Integration':'VERIFIED','Synthetic Smoke Test':'VERIFIED',
        'RT-DETRv2 Training':'NOT_IMPLEMENTED','UniAD Training':'NOT_IMPLEMENTED',
        'HVQ-Trans Training':'NOT_IMPLEMENTED','GPU Training':'NOT_VERIFIED',
        'Automatic Final Report':'NOT_VERIFIED'}


def file_sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def collect_files(root=ROOT):
    """공통 Git 파일은 해시 참조만 한다. 미배포 v2 Smoke/테스트 두 파일도 누락하지 않는다."""
    root=Path(root)
    payload=[p.relative_to(root).as_posix() for p in sorted((root/'mv_analysis/training').glob('*.py'))]
    payload+=[p.relative_to(root).as_posix() for p in sorted((root/'configs/training').glob('*.json'))]
    payload+=['scripts/experiments/run_weekend.py','scripts/experiments/training_worker.py',
        'mv_analysis/data/release_smoke_v2.py','tests/test_team_data_release_v2.py','tests/test_training_runner.py',
        'docs/experiments/TRAINING_IMPLEMENTATION_PROGRESS.md','docs/experiments/TRAINING_RUNNER_GUIDE.md',
        'environments/README.md']
    tracked=set(subprocess.check_output(['git','-C',str(root),'ls-files','-z'],text=True).strip('\0').split('\0'))
    base={n for n in tracked if n.startswith(('mv_analysis/','scripts/','tests/')) and n.endswith('.py')}
    base.update(['pyproject.toml','uv.lock','configs/experiments/model_registry.json'])
    base-=set(payload)
    for name in payload:
        path=root/name
        if path.is_symlink() or not path.is_file() or path.stat().st_size>1024*1024:
            raise ValueError('Unexpected/missing payload: '+name)
    # 변경된 기존 Git 코드를 이 ZIP 없이도 존재한다고 가정하지 않는다.
    for name in sorted(base):
        blob=subprocess.check_output(['git','-C',str(root),'show','HEAD:'+name])
        if (root/name).read_bytes()!=blob:
            raise ValueError('Required shared code differs from base Git HEAD: '+name)
    return sorted(payload),sorted(base)


def build(destination,*,validation=None,root=ROOT):
    root=Path(root);destination=Path(destination)
    if destination.exists():raise FileExistsError('Preserve existing ZIP: '+str(destination))
    payload,base=collect_files(root)
    head=subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD'],text=True).strip()
    hashes={n:file_sha(root/n) for n in payload}
    installer=root/'scripts/install_team_training_tools.py'
    if validation is not None:
        required=['zip_extract_sha256','conflict_preservation','clean_clone_install','common_import',
                  'teammate_profile','synthetic_smoke','full_pytest','training_blocked','data_v2_integration']
        if any(validation.get(k) is not True for k in required):raise ValueError('Packaging validation incomplete')
        if validation.get('payload_sha256')!=hashes or validation.get('installer_sha256')!=file_sha(installer):
            raise ValueError('Validation does not cover these payload/installer bytes')
    info=dict(package_id=PACKAGE,installation_type='GIT_CLONE_OVERLAY',reference_commit=head,
        source_repository='https://github.com/whrjsdnr/MV',created_utc=datetime.now(timezone.utc).isoformat(),
        deployment_status=STATUS,training_ready=False,
        package_validation='VERIFIED' if validation else 'PENDING',
        required_existing_code_sha256={n:file_sha(root/n) for n in base},payload_sha256=hashes,
        original_data_included=False,weights_included=False,approval_ledgers_included=False,
        dependencies_changed=False,existing_files_overwritten=False,
        note='Owner JSON configs retained for shared profiles/tests; no model implementations bundled.')
    readme=(root/'docs/experiments/package_templates/README_TEAMMATE.md').read_text().replace('{{BASE_COMMIT}}',head)
    inventory=['# 패키지 파일 목록','',f'기존 Clone 기준 Commit: `{head}`','',
        '실제 모델 소스/가중치는 포함하지 않는다. SHA는 package.json 및 SHA256SUMS를 따른다.',
        '', '|추가할 파일|바이트|SHA256|','|---|---:|---|']
    for n in payload:inventory.append(f'|`{n}`|{(root/n).stat().st_size}|`{hashes[n]}`|')
    inventory+=['','## 기존 Clone에서 재사용하는 파일','','아래 파일은 ZIP에 복제하지 않고 설치 전에 해시를 검사한다.','']
    inventory+=['- `'+n+'`' for n in base]
    content={'README_TEAMMATE.md':readme.encode(),'FILE_LIST.md':('\n'.join(inventory)+'\n').encode(),
        'package.json':json.dumps(info,ensure_ascii=False,indent=2).encode(),
        'install_tools.py':installer.read_bytes(),
        'VALIDATION_SUMMARY.json':json.dumps(validation or {'status':'PENDING_PACKAGE_VALIDATION'},ensure_ascii=False,indent=2).encode()}
    content.update({'files/'+n:(root/n).read_bytes() for n in payload})
    content['SHA256SUMS']=''.join(f'{hashlib.sha256(data).hexdigest()}  {name}\n' for name,data in sorted(content.items())).encode()
    destination.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(destination,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for name,data in sorted(content.items()):z.writestr(PACKAGE+'/'+name,data)
    with zipfile.ZipFile(destination) as z:
        if z.testzip() is not None:raise ValueError('ZIP CRC failed')
    return dict(path=str(destination.resolve()),bytes=destination.stat().st_size,sha256=file_sha(destination),
        payload_files=len(payload),base_files=len(base),archive_files=len(content),reference_commit=head,
        payload_sha256=hashes,installer_sha256=file_sha(installer),package_validation=info['package_validation'])


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--validation',type=Path)
    args=p.parse_args()
    validation=json.loads(args.validation.read_text()) if args.validation else None
    print(json.dumps(build(args.output,validation=validation),ensure_ascii=False,indent=2))


if __name__=='__main__':main()
