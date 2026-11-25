"""표준 라이브러리만 사용하는 팀 학습 도구 설치기. 기본은 Dry Run이며 기존 파일은 덮어쓰지 않는다."""
import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import zipfile

PACKAGE='MV_TEAMMATE_TRAINING_TOOLS_v1'
MAX_BYTES=16*1024*1024


def sha256(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):
            digest.update(block)
    return digest.hexdigest()


def relative_name(name):
    """POSIX 상대 경로만 허용한다. Windows drive, 숨김 경로, 중복 슬래시도 거부한다."""
    if not isinstance(name,str) or not re.fullmatch(r'[A-Za-z0-9_./-]+',name):
        raise ValueError('Invalid package path: '+str(name))
    parts=name.split('/')
    if any(not p or p in ('.','..') or p.startswith('.') for p in parts) or PurePosixPath(name).is_absolute():
        raise ValueError('Unsafe package path: '+name)
    return name


def safe_path(root,name):
    relative_name(name);root=Path(root).resolve();current=root
    for part in name.split('/'):
        current=current/part
        if current.is_symlink():
            raise ValueError('Symlink is not allowed: '+name)
    if not current.resolve().is_relative_to(root):
        raise ValueError('Path escapes root: '+name)
    return current


def read_json(path):
    def pairs(items):
        result={}
        for key,value in items:
            if key in result:raise ValueError('Duplicate manifest key: '+key)
            result[key]=value
        return result
    def invalid(value):raise ValueError('Non-standard JSON: '+value)
    return json.loads(Path(path).read_text(),object_pairs_hook=pairs,parse_constant=invalid)


def check_sha(value):
    if not isinstance(value,str) or not re.fullmatch('[a-f0-9]{64}',value):
        raise ValueError('Invalid SHA256')


def verify_bundle(bundle):
    """SHA256SUMS 자체를 제외한 정확한 파일 집합과 모든 바이트를 검사한다."""
    bundle=Path(bundle).resolve();entries={}
    checks=safe_path(bundle,'SHA256SUMS')
    for line in checks.read_text().splitlines():
        digest,name=line.split('  ',1);check_sha(digest);relative_name(name)
        if name in entries or name=='SHA256SUMS':raise ValueError('Duplicate/self-referential checksum')
        entries[name]=digest
    actual=set()
    for p in bundle.rglob('*'):
        if p.is_symlink():raise ValueError('Package contains a symlink')
        if p.is_file():actual.add(p.relative_to(bundle).as_posix())
    if actual!=set(entries)|{'SHA256SUMS'}:raise ValueError('Unexpected or missing package files')
    for name,digest in entries.items():
        if sha256(safe_path(bundle,name))!=digest:raise ValueError('Package checksum failed: '+name)
    info=read_json(bundle/'package.json')
    if info['package_id']!=PACKAGE or info['installation_type']!='GIT_CLONE_OVERLAY':
        raise ValueError('Wrong package contract')
    payload=info['payload_sha256'];base=info['required_existing_code_sha256']
    if not payload or set(payload)&set(base):raise ValueError('Payload/base overlap or empty payload')
    actual_payload={n.removeprefix('files/') for n in actual if n.startswith('files/')}
    if actual_payload!=set(payload):raise ValueError('Payload manifest differs from file set')
    for table in (payload,base):
        for name,digest in table.items():relative_name(name);check_sha(digest)
    for name,digest in payload.items():
        if entries['files/'+name]!=digest:raise ValueError('Payload SHA disagreement')
    return info


def extract_archive(archive,destination,expected_sha256):
    """새 폴더에만 압축 해제한다. 모든 ZIP 경로/유형/크기를 쓰기 전에 검사한다."""
    archive=Path(archive);destination=Path(destination)
    check_sha(expected_sha256)
    if sha256(archive)!=expected_sha256:raise ValueError('ZIP SHA256 differs from sender value')
    if destination.exists() or destination.is_symlink():raise FileExistsError('Use a new extraction directory')
    with zipfile.ZipFile(archive) as z:
        members=z.infolist();names=[i.filename for i in members]
        if len(names)!=len(set(names)) or len(names)>500 or sum(i.file_size for i in members)>MAX_BYTES:
            raise ValueError('Duplicate or oversized archive')
        for item in members:
            name=item.filename
            relative_name(name)
            if not name.startswith(PACKAGE+'/') or item.is_dir():raise ValueError('Unexpected archive root/directory entry')
            mode=stat.S_IFMT(item.external_attr>>16)
            if mode not in (0,stat.S_IFREG) or item.flag_bits&1:raise ValueError('Link/special/encrypted archive entry')
        if z.testzip() is not None:raise ValueError('ZIP CRC failure')
        destination.mkdir(parents=True,exist_ok=False)
        for item in members:
            target=safe_path(destination,item.filename);target.parent.mkdir(parents=True,exist_ok=True)
            with z.open(item) as src,target.open('xb') as dst:
                while block:=src.read(1024*1024):dst.write(block)
    bundle=destination/PACKAGE
    verify_bundle(bundle)
    return bundle


def inspect_workspace(workspace,info):
    root=Path(workspace).expanduser().resolve()
    proc=subprocess.run(['git','-C',str(root),'rev-parse','--show-toplevel'],text=True,capture_output=True)
    if proc.returncode or Path(proc.stdout.strip()).resolve()!=root:
        raise ValueError('--workspace must be the root of an existing Git clone')
    pending=[];identical=[];conflicts=[]
    for name,digest in info['required_existing_code_sha256'].items():
        path=safe_path(root,name)
        if not path.is_file() or sha256(path)!=digest:conflicts.append('BASE_MISMATCH: '+name)
    for name,digest in info['payload_sha256'].items():
        path=safe_path(root,name)
        if path.exists():
            if not path.is_file() or sha256(path)!=digest:conflicts.append('PRESERVE_EXISTING: '+name)
            else:identical.append(name)
        else:
            # 디렉터리 자리에 기존 일반 파일이 있으면 일부 설치 전에 중단한다.
            parent=path.parent
            while parent!=root:
                if parent.exists() and not parent.is_dir():conflicts.append('PARENT_NOT_DIRECTORY: '+name);break
                parent=parent.parent
            pending.append(name)
    if conflicts:raise ValueError('Installation blocked; no files written:\n'+'\n'.join(conflicts))
    head=subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD'],text=True).strip()
    return root,pending,identical,head


@contextmanager
def installation_lock(root):
    """디렉터리 FD 잠금이므로 Clone 안에 잠금 파일이나 Git 변경을 만들지 않는다."""
    fd=os.open(root,os.O_RDONLY|os.O_DIRECTORY)
    try:
        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        yield
    finally:os.close(fd)


def install(bundle,workspace,*,apply=False):
    bundle=Path(bundle).resolve();info=verify_bundle(bundle)
    root,pending,identical,head=inspect_workspace(workspace,info)
    written=[]
    if apply:
        with installation_lock(root):
            root,pending,identical,head=inspect_workspace(root,info)
            try:
                for name in pending:
                    target=safe_path(root,name);target.parent.mkdir(parents=True,exist_ok=True)
                    data=safe_path(bundle,'files/'+name).read_bytes()
                    if hashlib.sha256(data).hexdigest()!=info['payload_sha256'][name]:raise ValueError('Payload changed during install')
                    with target.open('xb') as f:
                        f.write(data);f.flush();os.fsync(f.fileno())
                    written.append(name)
                _,remaining,_,_=inspect_workspace(root,info)
                if remaining:raise RuntimeError('Post-install files missing')
            except Exception as e:
                raise RuntimeError('Partial installation preserved; retry after inspection. Added files='+json.dumps(written)+'; '+str(e)) from e
    return dict(status='INSTALLED_VERIFIED' if apply else 'DRY_RUN_PASSED',package_id=PACKAGE,
        workspace=str(root),base_commit=head,reference_commit=info['reference_commit'],
        new_files=pending,identical_files=identical,written_files=written,existing_files_overwritten=False,
        training_ready=False,reason='RT-DETRv2 / UniAD / HVQ-Trans training backend NOT_IMPLEMENTED')


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--workspace',required=True);p.add_argument('--bundle',type=Path)
    p.add_argument('--archive',type=Path);p.add_argument('--extract-to',type=Path)
    p.add_argument('--expected-sha256')
    mode=p.add_mutually_exclusive_group();mode.add_argument('--apply',action='store_true');mode.add_argument('--dry-run',action='store_true')
    args=p.parse_args(argv)
    try:
        if args.archive:
            if args.bundle or not args.extract_to or not args.expected_sha256:
                raise ValueError('--archive requires --extract-to and --expected-sha256; do not also set --bundle')
            bundle=extract_archive(args.archive,args.extract_to,args.expected_sha256)
        else:
            if args.extract_to or args.expected_sha256:raise ValueError('Extraction options require --archive')
            bundle=args.bundle or Path(__file__).resolve().parent
        print(json.dumps(install(bundle,args.workspace,apply=args.apply),ensure_ascii=False,indent=2))
        return 0
    except (OSError,ValueError,RuntimeError,KeyError,zipfile.BadZipFile) as e:
        print(json.dumps({'status':'BLOCKED','error':str(e),'training_ready':False},ensure_ascii=False,indent=2))
        return 2


if __name__=='__main__':raise SystemExit(main())
