"""Export one indexed dictionary, with its media, for incremental iPhone import."""
import argparse, pathlib, sqlite3, tempfile, zipfile
from contextlib import closing


def export(source, code, output):
    source = pathlib.Path(source).resolve()
    output = pathlib.Path(output).resolve()
    with closing(sqlite3.connect((source / 'mdict-index.sqlite3').as_uri() + '?mode=ro', uri=True)) as db:
        row = db.execute('SELECT root FROM dictionaries WHERE code=?', (code,)).fetchone()
        if not row:
            raise ValueError('Unknown dictionary')
        folder = (source / row[0]).resolve()
        if not folder.is_relative_to(source) or folder == source:
            raise ValueError('A portable dictionary source folder is required')
        for path, size in db.execute('SELECT path,size FROM files WHERE code=?', (code,)):
            item = (source / path).resolve()
            if not item.is_relative_to(folder) or not item.is_file() or item.stat().st_size != size:
                raise ValueError('Dictionary source is missing or incomplete: ' + path)
        if output.exists():
            raise ValueError('Output already exists; choose a new filename')
        output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory() as temp:
            index = pathlib.Path(temp) / 'mdict-index.sqlite3'
            with closing(sqlite3.connect(index)) as target:
                db.backup(target)
                target.execute('DELETE FROM records WHERE file NOT IN (SELECT id FROM files WHERE code=?)', (code,))
                target.execute('DELETE FROM blocks WHERE file NOT IN (SELECT id FROM files WHERE code=?)', (code,))
                target.execute('DELETE FROM files WHERE code<>?', (code,))
                target.execute('DELETE FROM dictionaries WHERE code<>?', (code,))
                target.commit()
                target.execute('VACUUM')
                assert target.execute('PRAGMA quick_check').fetchone()[0] == 'ok'
            partial = output.with_suffix('.partial')
            try:
                with zipfile.ZipFile(partial, 'w', compression=zipfile.ZIP_STORED, allowZip64=True) as archive:
                    archive.write(index, 'dictionary-pack/mdict-index.sqlite3')
                    for item in sorted(folder.rglob('*')):
                        if item.is_file():
                            if not item.resolve().is_relative_to(folder):
                                raise ValueError('Source contains an external link')
                            archive.write(item, 'dictionary-pack/' + item.relative_to(source).as_posix())
                partial.replace(output)
            finally:
                partial.unlink(missing_ok=True)
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=pathlib.Path, required=True)
    parser.add_argument('--code')
    parser.add_argument('--output', type=pathlib.Path)
    args = parser.parse_args()
    if not args.code:
        with closing(sqlite3.connect((args.source.resolve() / 'mdict-index.sqlite3').as_uri() + '?mode=ro', uri=True)) as db:
            rows = db.execute('SELECT code,name FROM dictionaries ORDER BY rowid').fetchall()
        for i, (_, name) in enumerate(rows, 1):
            print(str(i) + '. ' + name)
        args.code = rows[int(input('Dictionary number to export: ')) - 1][0]
    output = args.output or pathlib.Path.cwd() / ('Dictionary-' + args.code + '.zip')
    print('Preparing only this dictionary and its media. Please wait...')
    print('Ready:', export(args.source, args.code, output))
    print('Upload this ZIP. On iPhone: unpack in Files, then Library > Add dictionary pack > dictionary-pack.')

if __name__ == '__main__':
    main()
