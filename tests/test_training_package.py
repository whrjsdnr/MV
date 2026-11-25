"""배포 ZIP/설치기 안전성. 임시 Clone만 사용하며 기존 구현·데이터를 수정하지 않는다."""
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import install_team_training_tools as installer
import package_team_training_tools as packager


@pytest.fixture(scope='module')
def package(tmp_path_factory):
    folder=tmp_path_factory.mktemp('training-package')
    result=packager.build(folder/'tools.zip')
    bundle=installer.extract_archive(result['path'],folder/'unpacked',result['sha256'])
    return result,bundle


@pytest.fixture
def workspace(tmp_path,package):
    root=tmp_path/'workspace'
    subprocess.run(['git','clone','--quiet','--no-hardlinks',str(packager.ROOT),str(root)],check=True)
    return root


def test_inventory_payload_and_dependencies(package):
    result,bundle=package;info=installer.verify_bundle(bundle)
    assert info['installation_type']=='GIT_CLONE_OVERLAY' and not info['training_ready']
    assert info['deployment_status']['GPU Training']=='NOT_VERIFIED'
    assert info['deployment_status']['RT-DETRv2 Training']=='NOT_IMPLEMENTED'
    assert 'mv_analysis/data/release_smoke_v2.py' in info['payload_sha256']
    assert 'mv_analysis/experiments/recorder.py' in info['required_existing_code_sha256']
    assert 'uv.lock' in info['required_existing_code_sha256']
    assert not any(n.endswith(('.jpg','.png','.pt','.pth','.jsonl')) for n in info['payload_sha256'])


def test_dry_run_install_idempotence_preserves_results(package,workspace):
    _,bundle=package
    existing=workspace/'outputs/experiments/keep.bin';existing.parent.mkdir(parents=True);existing.write_bytes(b'KEEP')
    before=subprocess.check_output(['git','status','--porcelain'],cwd=workspace)
    result=installer.install(bundle,workspace)
    assert result['status']=='DRY_RUN_PASSED'
    assert not (workspace/'mv_analysis/training').exists()
    assert subprocess.check_output(['git','status','--porcelain'],cwd=workspace)==before
    done=installer.install(bundle,workspace,apply=True)
    assert done['status']=='INSTALLED_VERIFIED' and done['written_files']
    again=installer.install(bundle,workspace,apply=True)
    assert not again['written_files'] and len(again['identical_files'])==len(done['written_files'])
    assert existing.read_bytes()==b'KEEP'


def test_payload_conflict_stops_all_writes(package,workspace):
    _,bundle=package;p=workspace/'configs/training/uniad.json';p.parent.mkdir(parents=True);p.write_text('MY SETTINGS')
    with pytest.raises(ValueError,match='PRESERVE_EXISTING'):installer.install(bundle,workspace,apply=True)
    assert not (workspace/'mv_analysis/training').exists() and p.read_text()=='MY SETTINGS'


def test_base_conflict_stops_all_writes(package,workspace):
    _,bundle=package;p=workspace/'pyproject.toml';p.write_text(p.read_text()+'\n# My change\n')
    with pytest.raises(ValueError,match='BASE_MISMATCH'):installer.install(bundle,workspace,apply=True)
    assert not (workspace/'mv_analysis/training').exists()


def test_symlink_target_rejected(package,workspace,tmp_path):
    _,bundle=package;outside=tmp_path/'outside';outside.mkdir()
    (workspace/'mv_analysis/training').symlink_to(outside,target_is_directory=True)
    with pytest.raises(ValueError,match='Symlink'):installer.install(bundle,workspace,apply=True)
    assert not list(outside.iterdir())


def test_missing_or_tampered_bundle_file(package,tmp_path):
    _,source=package;bundle=tmp_path/'bundle';shutil.copytree(source,bundle)
    (bundle/'files/mv_analysis/training/settings.py').write_text('changed')
    with pytest.raises(ValueError,match='checksum'):installer.verify_bundle(bundle)


def test_unlisted_extra_file_rejected(package,tmp_path):
    _,source=package;bundle=tmp_path/'bundle';shutil.copytree(source,bundle)
    (bundle/'unexpected.txt').write_text('extra')
    with pytest.raises(ValueError,match='Unexpected'):installer.verify_bundle(bundle)


@pytest.mark.parametrize('name',['../escape','/absolute','C:/Windows/file','MV_TEAMMATE_TRAINING_TOOLS_v1/../escape',
    'MV_TEAMMATE_TRAINING_TOOLS_v1/a//b','wrong_root/file','MV_TEAMMATE_TRAINING_TOOLS_v1/.env'])
def test_zip_path_escape_rejected_before_writes(tmp_path,name):
    archive=tmp_path/'bad.zip'
    with zipfile.ZipFile(archive,'w') as z:z.writestr(name,'bad')
    with pytest.raises(ValueError):installer.extract_archive(archive,tmp_path/'dest',installer.sha256(archive))
    assert not (tmp_path/'dest').exists()


def test_zip_symlink_rejected(tmp_path):
    archive=tmp_path/'bad.zip';info=zipfile.ZipInfo(installer.PACKAGE+'/link')
    info.external_attr=0o120777<<16
    with zipfile.ZipFile(archive,'w') as z:z.writestr(info,'../../outside')
    with pytest.raises(ValueError):installer.extract_archive(archive,tmp_path/'dest',installer.sha256(archive))


def test_sha_and_extraction_overwrite_refused(package,tmp_path):
    result,_=package
    with pytest.raises(ValueError,match='SHA256'):installer.extract_archive(result['path'],tmp_path/'dest','0'*64)
    (tmp_path/'exists').mkdir()
    with pytest.raises(FileExistsError):installer.extract_archive(result['path'],tmp_path/'exists',result['sha256'])
    with pytest.raises(FileExistsError):packager.build(result['path'])


def test_final_build_requires_matching_validation(package,tmp_path):
    result,_=package
    with pytest.raises(ValueError,match='incomplete'):packager.build(tmp_path/'final.zip',validation={})
    keys=['zip_extract_sha256','conflict_preservation','clean_clone_install','common_import',
        'teammate_profile','synthetic_smoke','full_pytest','training_blocked','data_v2_integration']
    validation={k:True for k in keys}
    validation.update(payload_sha256=result['payload_sha256'],installer_sha256='0'*64)
    with pytest.raises(ValueError,match='does not cover'):packager.build(tmp_path/'final.zip',validation=validation)
