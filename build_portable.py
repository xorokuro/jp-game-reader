"""Build a personal Windows folder with runtime and all indexed dictionaries."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import sqlite3
import urllib.request
import zipfile

RUNTIME_URL='https://www.python.org/ftp/python/3.13.15/python-3.13.15-embed-amd64.zip'
RUNTIME_SHA256='d1f04d990aee1253d8569e8e5104e30fa9f5fa830899f14843448872d936a2cf'


def checksum(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def build(index, destination, runtime_archive, argos_pack=None):
    source=Path(__file__).resolve().parent
    destination=destination.resolve()
    if destination.exists():raise ValueError('Choose a new output folder; existing personal data is never overwritten.')
    index=index.resolve()
    with sqlite3.connect(index.as_uri()+'?mode=ro',uri=True) as db:
        db.row_factory=sqlite3.Row
        dictionaries=[dict(row) for row in db.execute('SELECT * FROM dictionaries')]
        files=[dict(row) for row in db.execute('SELECT * FROM files')]
    def original(value):
        path=Path(value)
        return path if path.is_absolute() else index.parent/path
    roots={d['code']:original(d['root']).resolve() for d in dictionaries}
    for code,root in roots.items():
        if not re.fullmatch('[A-Za-z0-9_-]+',code):raise ValueError('Invalid dictionary code')
        if not root.is_dir():raise ValueError('Missing dictionary folder: '+str(root))
    for item in files:
        path=original(item['path']).resolve()
        if not path.is_relative_to(roots[item['code']]):raise ValueError('Dictionary archive is outside its source folder.')
        if not path.is_file() or path.stat().st_size!=item['size']:raise ValueError('Missing or changed dictionary archive: '+str(path))
    runtime_archive.parent.mkdir(parents=True,exist_ok=True)
    if not runtime_archive.exists():
        print('Downloading official portable Python runtime...',flush=True)
        urllib.request.urlretrieve(RUNTIME_URL,runtime_archive)
    if checksum(runtime_archive)!=RUNTIME_SHA256:raise ValueError('Python runtime checksum mismatch.')
    destination.mkdir(parents=True)
    for path in source.iterdir():
        if path.is_file() and path.suffix in ('.py','.js','.css','.html','.ps1','.cmd','.md','.txt'):
            shutil.copy2(path,destination/path.name)
    with zipfile.ZipFile(runtime_archive) as archive:archive.extractall(destination/'runtime')
    (destination/'runtime'/'python313._pth').write_text('python313.zip\n.\n..\n',encoding='utf-8')
    if argos_pack is not None:
        if not (argos_pack/'ready.json').is_file():raise ValueError('Argos pack has not passed its offline check.')
        shutil.copytree(argos_pack,destination/'translation'/'argos')
    copied=[]
    for code,root in roots.items():
        print('Copying '+code+'...',flush=True)
        output=destination/'dictionaries'/'sources'/code
        for path in root.rglob('*'):
            if path.is_file():
                target=output/path.relative_to(root);target.parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(path,target)
                digest=checksum(path)
                if checksum(target)!=digest:raise ValueError('Dictionary copy verification failed: '+str(target))
                copied.append({'path':target.relative_to(destination).as_posix(),'bytes':target.stat().st_size,'sha256':digest})
    target_index=destination/'dictionaries'/'mdict-index.sqlite3'
    print('Copying and relocating search index...',flush=True)
    with sqlite3.connect(index.as_uri()+'?mode=ro',uri=True) as original_db, sqlite3.connect(target_index) as target:
        original_db.backup(target)
        for code in roots:
            target.execute('UPDATE dictionaries SET root=? WHERE code=?',('sources/'+code,code))
        for item in files:
            relative=original(item['path']).resolve().relative_to(roots[item['code']])
            target.execute('UPDATE files SET path=? WHERE id=?',((Path('sources')/item['code']/relative).as_posix(),item['id']))
        target.commit()
        if target.execute('PRAGMA quick_check').fetchone()[0]!='ok':raise ValueError('Dictionary index verification failed.')
    copied.append({'path':target_index.relative_to(destination).as_posix(),'bytes':target_index.stat().st_size,'sha256':checksum(target_index)})
    manifest={'runtime_url':RUNTIME_URL,'runtime_sha256':RUNTIME_SHA256,'dictionaries':[{'code':d['code'],'name':d['name']} for d in dictionaries],'files':copied,'total_dictionary_bytes':sum(item['bytes'] for item in copied)}
    (destination/'bundle-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'folder':str(destination),'dictionaries':len(dictionaries),'files':len(copied),'GB':manifest['total_dictionary_bytes']/1e9}),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--index',type=Path,required=True)
    parser.add_argument('--destination',type=Path,required=True)
    parser.add_argument('--runtime-archive',type=Path,required=True)
    parser.add_argument('--argos-pack',type=Path,help='Prepared offline Argos folder to include')
    args=parser.parse_args()
    build(args.index,args.destination,args.runtime_archive,args.argos_pack)
