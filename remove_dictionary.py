"""Remove one MDX dictionary from the reader: index rows out, files moved to dictionaries\\_to_delete\\.

  python remove_dictionary.py MDX_ALL        (or double-click "Remove all-in-one dictionary.cmd")

Nothing is deleted: the source folder is moved to dictionaries\\_to_delete\\<code>\\ so you can
delete it yourself (or move it back and re-index it later). Close the reader first.
"""
import shutil, sqlite3, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
DICT = HERE / 'dictionaries'
INDEX = DICT / 'mdict-index.sqlite3'

def main(code):
    if not INDEX.exists():
        raise SystemExit('找不到 dictionaries\\mdict-index.sqlite3')
    db = sqlite3.connect(INDEX, timeout=60)
    row = db.execute('SELECT name, root FROM dictionaries WHERE code=?', (code,)).fetchone()
    if not row:
        print(f'索引裡沒有 {code}（可能已移除）。')
    else:
        name, root = row
        files = [r[0] for r in db.execute('SELECT id FROM files WHERE code=?', (code,))]
        n = db.execute(f'SELECT COUNT(*) FROM records WHERE file IN ({",".join("?" * len(files)) or "NULL"})', files).fetchone()[0]
        print(f'移除「{name}」（{code}）：{len(files)} 個檔案、{n:,} 筆索引 …')
        try:
            db.execute('BEGIN IMMEDIATE')
            for fid in files:
                db.execute('DELETE FROM records WHERE file=?', (fid,))
                db.execute('DELETE FROM blocks WHERE file=?', (fid,))
            db.execute('DELETE FROM files WHERE code=?', (code,))
            db.execute('DELETE FROM dictionaries WHERE code=?', (code,))
            db.commit()
        except Exception as e:
            db.rollback(); db.close()
            raise SystemExit(f'✗ 失敗，索引未變更：{e}（請先關閉閱讀器再試）')
        print('索引已更新。')
        src = (DICT / root).resolve() if root and root != '.' else None
        if src and src.is_dir() and src.is_relative_to(DICT.resolve()) and src != DICT.resolve():
            dest = DICT / '_to_delete' / src.name
            if dest.exists():
                dest = dest.with_name(dest.name + time.strftime('_%Y%m%d%H%M%S'))
            dest.parent.mkdir(exist_ok=True)
            shutil.move(str(src), str(dest))
            print(f'檔案已移到：{dest}\n（確認閱讀器正常後，可自行刪除 _to_delete 資料夾）')
    print('壓縮索引檔（VACUUM，可能需要一兩分鐘）…')
    before = INDEX.stat().st_size
    try:
        db.execute('VACUUM')
        print(f'完成：{before / 2**30:.2f} GB → {INDEX.stat().st_size / 2**30:.2f} GB')
    except Exception as e:
        print('（略過壓縮：', e, '）')
    db.close()
    print('重新開啟閱讀器即可。')

if __name__ == '__main__':
    code = sys.argv[1] if len(sys.argv) > 1 else 'MDX_ALL'
    if '--yes' not in sys.argv:
        print(f'從閱讀器移除辭典 {code}：')
        print('  1. 從辭典索引刪除它的項目')
        print('  2. 把它的資料夾移到 dictionaries\\_to_delete\\（不會直接刪檔）')
        print('  3. 壓縮索引檔')
        print('請先關閉閱讀器。')
        if input('確定要繼續嗎？輸入 y 後按 Enter：').strip().lower() != 'y':
            raise SystemExit('已取消，沒有任何變更。')
    main(code)
