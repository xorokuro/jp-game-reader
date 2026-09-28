"""Check portable file integrity and read samples without the original folders."""
import hashlib
import json
from pathlib import Path
import sqlite3
import mdict_library


def verify():
    root=Path(__file__).resolve().parent
    manifest=json.loads((root/'bundle-manifest.json').read_text(encoding='utf-8'))
    for item in manifest['files']:
        path=root/item['path']
        if not path.is_file() or path.stat().st_size!=item['bytes']:
            raise ValueError('Missing or incomplete file: '+item['path'])
        with path.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
        if digest!=item['sha256']:raise ValueError('File checksum mismatch: '+item['path'])
    index=root/'dictionaries'/'mdict-index.sqlite3'
    mdict_library.INDEX=index
    definitions=0;media=0
    with sqlite3.connect(index.as_uri()+'?mode=ro',uri=True) as db:
        db.row_factory=sqlite3.Row
        for source in db.execute('SELECT * FROM files'):
            if Path(source['path']).is_absolute():raise ValueError('Non-portable dictionary path')
            rows=db.execute('SELECT * FROM records WHERE file=? LIMIT 30',(source['id'],)).fetchall()
            if source['kind']=='.mdx':
                for row in rows:
                    try:
                        output=mdict_library.entry(source['code'],row['id'])
                        if output:definitions+=1;break
                    except ValueError:continue
                else:raise ValueError('No readable definition sample: '+source['code'])
            else:
                if not rows:raise ValueError('No resource sample: '+source['path'])
                data,_=mdict_library.read_record(db,rows[0])
                if not data:raise ValueError('Empty resource sample: '+source['path'])
                media+=1
    print(json.dumps({'verified_files':len(manifest['files']),'dictionary_definitions':definitions,'resource_archives':media,'dictionary_GB':manifest['total_dictionary_bytes']/1e9}))


if __name__=='__main__':verify()
