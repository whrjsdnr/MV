"""Git 변경 없이 팀 데이터 배포에 필요한 새 도구만 작은 별도 ZIP으로 묶는다."""
from pathlib import Path
import argparse
import hashlib
import json
import zipfile


INSTALLER = '''"""기존 소스 해시를 확인하고 새 도구만 설치한다. 기존 수정 파일은 덮어쓰지 않는다."""
from pathlib import Path, PurePosixPath
import argparse, hashlib, json

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def safe(base, relative):
    p = PurePosixPath(relative)
    if p.is_absolute() or '..' in p.parts or '\\\\' in relative or ':' in relative:
        raise ValueError('Unsafe tool path')
    target = (base/relative).resolve()
    if not target.is_relative_to(base.resolve()):
        raise ValueError('Tool path escapes destination')
    return target

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', type=Path, required=True)
    parser.add_argument('--apply', action='store_true', help='없으면 검증만, 있으면 새 파일만 설치')
    args = parser.parse_args()
    bundle = Path(__file__).resolve().parent
    info = json.loads((bundle/'tooling.json').read_text())
    for name, sha in info['required_existing_code_sha256'].items():
        path = safe(args.workspace, name)
        if not path.is_file() or digest(path) != sha:
            raise ValueError('Base MV code differs: '+name)
    actual = {p.relative_to(bundle/'files').as_posix() for p in (bundle/'files').rglob('*') if p.is_file()}
    if actual != set(info['new_files_sha256']):
        raise ValueError('Unexpected/missing tooling files')
    pending = []
    for name, sha in info['new_files_sha256'].items():
        source, target = safe(bundle/'files', name), safe(args.workspace, name)
        if digest(source) != sha:
            raise ValueError('Tool payload hash mismatch: '+name)
        if target.exists() and digest(target) != sha:
            raise FileExistsError('Preserve existing changes; file differs: '+name)
        if not target.exists():
            pending.append((source, target))
    if args.apply:
        for source, target in pending:
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open('xb') as out:
                out.write(source.read_bytes())
    print(json.dumps(dict(status='INSTALLED' if args.apply else 'VERIFIED_ONLY', new_files=len(pending)), ensure_ascii=False))

if __name__ == '__main__':
    main()
'''


def main():
    """팀원은 이 생성기가 아니라 ZIP의 install_tools.py를 실행한다."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    if args.output.exists():raise FileExistsError(args.output)
    new = ['mv_analysis/data/team_release.py', 'mv_analysis/data/release_builder.py',
           'mv_analysis/data/team_release_v2.py','mv_analysis/data/release_smoke_v2.py',
           'scripts/team_data_release.py', 'scripts/package_team_data_tools.py',
           'tests/test_team_data_release.py','tests/test_team_data_release_v2.py', 'docs/data/README_DATA_TEMPLATE.md',
           'docs/data/archive/README_DATA_v1.md',
           'docs/data/MANIFEST_SCHEMA.md', 'docs/data/DATA_LOADER_GUIDE.md']
    base = ['pyproject.toml','uv.lock','mv_analysis/crop_manifest.py',
            'mv_analysis/data/__init__.py','mv_analysis/data/manifest.py','mv_analysis/data/targets.py',
            'mv_analysis/data/datasets.py','mv_analysis/data/adapters.py','mv_analysis/data/collate.py',
            'mv_analysis/experiments/geometry.py']
    digest = lambda name: hashlib.sha256((root/name).read_bytes()).hexdigest()
    info = dict(tooling_version='MV_TEAM_DATA_TOOLS_v2', required_existing_code_sha256={n:digest(n) for n in base},
                new_files_sha256={n:digest(n) for n in new}, original_data_included=False,
                existing_files_overwritten=False, dependencies_changed=False)
    readme = '''# MV 팀 배포 도구 설치

이 작은 ZIP은 데이터 ZIP을 읽는 새 Python 코드·테스트·계약 문서입니다. Git Commit/Push 없이 내부 전달하기 위해 별도 제공합니다. 기존 공개 공통 코드와 uv.lock을 교체하지 않습니다.

1. 발신자가 따로 전달한 이 ZIP의 SHA-256을 `sha256sum MV_TEAM_DATA_TOOLS_v1.zip`으로 비교합니다.
2. WSL에서 `unzip MV_TEAM_DATA_TOOLS_v1.zip -d /tmp/mv-team-tools`로 새 위치에 풉니다. 데이터 ZIP은 이곳에 풀 필요가 없습니다.
3. 자신의 MV 프로젝트 루트에서 `python3 /tmp/mv-team-tools/MV_TEAM_DATA_TOOLS_v1/install_tools.py --workspace "$PWD"`로 기존 코드와 새 파일의 해시를 검사합니다.
4. VERIFIED_ONLY면 같은 명령 끝에 `--apply`를 추가하여 새 파일만 설치합니다. 기존 파일이 다르면 중단하므로 임의로 삭제하지 말고 관리자와 버전을 맞춥니다.
5. MV 루트에서 `uv sync --locked`, `uv run --locked pytest -q tests/test_team_data_release.py`, `uv run --locked python scripts/team_data_release.py --help`를 실행합니다.
6. 함께 받은 데이터 ZIP의 README_DATA.md에 따라 verify/smoke를 실행합니다. 모델 학습은 실행하지 않습니다.

설치 후 파일은 로컬 미커밋 상태입니다. 팀 소스 반영은 별도 리뷰 절차로 진행합니다. 원본 Real-IAD·승인 원장·가중치는 들어 있지 않습니다.
'''
    args.output.parent.mkdir(parents=True,exist_ok=True)
    readme=readme.replace('TOOLS_v1','TOOLS_v2').replace('tests/test_team_data_release.py','tests/test_team_data_release.py tests/test_team_data_release_v2.py')
    readme+='\n v1 도구가 이미 수정된 작업 공간이면 설치기가 덮어쓰기를 거부합니다. 기존 자료를 보존하고 별도 c4b4a46 코드 복사본에 설치하거나, 변경 diff를 검토해 수동으로 통합합니다. DATA ZIP v1은 보존하고 v2를 새 폴더에 풉니다.\n'
    prefix='MV_TEAM_DATA_TOOLS_v2/'
    with zipfile.ZipFile(args.output,'x',compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr(prefix+'README.md',readme)
        z.writestr(prefix+'tooling.json',json.dumps(info,ensure_ascii=False,indent=2))
        z.writestr(prefix+'install_tools.py',INSTALLER)
        for name in new:z.write(root/name,prefix+'files/'+name)
    with zipfile.ZipFile(args.output) as z:
        if z.testzip() is not None:raise ValueError('Tool ZIP CRC failed')
    print(json.dumps(dict(path=str(args.output.resolve()), bytes=args.output.stat().st_size,
                         sha256=hashlib.sha256(args.output.read_bytes()).hexdigest()),indent=2))


if __name__ == '__main__':
    main()
