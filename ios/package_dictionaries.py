"""Package the personal portable dictionaries locally. Never commit the output."""
import argparse, hashlib, json, pathlib, sqlite3, zipfile

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('portable', type=pathlib.Path)
    parser.add_argument('output', type=pathlib.Path)
    args = parser.parse_args()
    source = args.portable.resolve() / 'dictionaries'
    db = sqlite3.connect((source / 'mdict-index.sqlite3').as_uri() + '?mode=ro', uri=True)
    dictionaries = [dict(zip(('code', 'name'), row)) for row in db.execute('SELECT code,name FROM dictionaries ORDER BY rowid')]
    for path, size in db.execute('SELECT path,size FROM files'):
        target = (source / path).resolve()
        if not target.is_relative_to(source) or not target.is_file() or target.stat().st_size != size:
            raise ValueError('Missing or incomplete dictionary: ' + path)
    db.close()
    args.output.mkdir(parents=True, exist_ok=True)
    target = args.output / 'Japanese-Reader-iPhone-Dictionaries.zip'
    temporary = target.with_suffix('.partial')
    manifest = []
    with zipfile.ZipFile(temporary, 'w', compression=zipfile.ZIP_STORED, allowZip64=True) as archive:
        for path in sorted(source.rglob('*')):
            if not path.is_file(): continue
            digest = hashlib.sha256()
            name = 'dictionaries/' + path.relative_to(source).as_posix()
            with path.open('rb') as input_file, archive.open(name, 'w', force_zip64=True) as output_file:
                while chunk := input_file.read(8 * 1024 * 1024):
                    digest.update(chunk); output_file.write(chunk)
            manifest.append({'path': name, 'size': path.stat().st_size, 'sha256': digest.hexdigest()})
    temporary.replace(target)
    (args.output / 'dictionary-manifest.json').write_text(json.dumps({'collections': dictionaries, 'files': manifest}, ensure_ascii=False, indent=2), encoding='utf-8')
    with zipfile.ZipFile(target) as archive:
        broken = archive.testzip()
        if broken: raise ValueError('ZIP integrity check failed: ' + broken)
    print(json.dumps({'zip': str(target), 'bytes': target.stat().st_size, 'collections': len(dictionaries), 'files': len(manifest), 'zip_crc_verified': True}))

if __name__ == '__main__': main()
