"""Add デジタル大辞泉 and 広辞苑 第七版 to the reader (and so to the vocab exporter and the iPhone pack).

  python add_dictionaries.py            (or double-click "Add Daijisen and Kojien.cmd")

Copies each dictionary from its download folder into dictionaries\\sources\\<code>\\, writes the Washi
restyle (dict_styles\\*.css) next to it, and indexes the .mdx (+ .mdd media such as 大辞泉 audio) into
dictionaries\\mdict-index.sqlite3. Running it again replaces the entries (e.g. after a newer download).
Close the reader first.
"""
import shutil, sqlite3, sys, unicodedata
from pathlib import Path

HERE = Path(__file__).resolve().parent
DICT = HERE / 'dictionaries'
INDEX = DICT / 'mdict-index.sqlite3'
sys.path.insert(0, str(HERE))
import mdx_tools   # noqa: E402

DICTIONARIES = [
    {'code': 'MDX_DAIJISEN', 'name': '小学館 デジタル大辞泉',
     'src': r'C:\Users\sagen\Downloads\Compressed\大辞泉202304 (小学館) NEW',
     'mdx_name': '大辞泉202304.mdx', 'css': 'daijisen-washi.css'},
    {'code': 'MDX_KOJIEN', 'name': '岩波 広辞苑 第七版',
     'src': r'C:\Users\sagen\Downloads\Compressed\広辞苑（第七版）改',
     'mdx_name': '広辞苑第七版.mdx', 'css': 'kojien-washi.css'},
]

def norm(w):
    return unicodedata.normalize('NFKC', w).strip().casefold()

def find_mdx(src):
    """The .mdx in the folder. Some zips lose the file name (…・・mdx without a dot), so match the ending."""
    cands = [p for p in src.iterdir() if p.is_file() and p.name.lower().endswith('mdx') and p.stat().st_size > 1_000_000]
    return max(cands, key=lambda p: p.stat().st_size) if cands else None

def install(d, db):
    src = Path(d['src'])
    if not src.exists():
        print(f"✗ 找不到 {src}，略過「{d['name']}」"); return
    mdx = find_mdx(src)
    if not mdx:
        print(f"✗ {src} 裡沒有 .mdx，略過"); return
    dest = DICT / 'sources' / d['code']
    dest.mkdir(parents=True, exist_ok=True)
    print(f"「{d['name']}」：複製到 {dest} …")
    target = dest / d['mdx_name']
    shutil.copy2(mdx, target)
    mdds = []
    for p in sorted(src.iterdir()):
        if not p.is_file() or p == mdx: continue
        low = p.name.lower()
        if low.endswith('.mdd'):
            out = dest / p.name
            print(f'  媒體檔 {p.name}（{p.stat().st_size / 2**30:.2f} GB）…')
            shutil.copy2(p, out); mdds.append(out)
        elif low.endswith(('.otf', '.ttf', '.woff', '.woff2', '.png', '.svg', '.jpg', '.js')):
            shutil.copy2(p, dest / p.name)
    shutil.copy2(HERE / 'dict_styles' / d['css'], dest / d['css'])

    # replace any older copy of this dictionary in the index
    for (fid,) in db.execute('SELECT id FROM files WHERE code=?', (d['code'],)).fetchall():
        db.execute('DELETE FROM records WHERE file=?', (fid,))
        db.execute('DELETE FROM blocks WHERE file=?', (fid,))
    db.execute('DELETE FROM files WHERE code=?', (d['code'],))
    rel = lambda p: p.relative_to(DICT).as_posix()
    print('  建立索引（約一分鐘）…')
    fid, n = mdx_tools.index_mdx(target, db, d['code'], d['name'], rel(dest), d['css'], rel(target), norm)
    for m in mdds:
        _, k = mdx_tools.index_mdd(m, db, d['code'], rel(m))
        print(f'  媒體索引：{k:,} 個檔案')
    print(f"✓ 「{d['name']}」：{n:,} 個詞條")

def main():
    if not INDEX.exists():
        raise SystemExit('找不到 dictionaries\\mdict-index.sqlite3')
    print('加入 デジタル大辞泉 與 広辞苑 第七版（請先關閉閱讀器）')
    try:
        if input('開始嗎？輸入 y 後按 Enter：').strip().lower() != 'y':
            raise SystemExit('已取消。')
    except EOFError:
        raise SystemExit('已取消。')
    db = sqlite3.connect(INDEX, timeout=60)
    db.executescript(mdx_tools.SCHEMA)
    try:
        for d in DICTIONARIES:
            db.execute('BEGIN IMMEDIATE')
            try:
                install(d, db); db.commit()
            except Exception as e:
                db.rollback(); print(f"✗ 「{d['name']}」失敗，索引未變更：{e}")
    finally:
        db.close()
    print('\n完成。重新開啟閱讀器：辭典清單會出現這兩本（可在設定裡調整順序）。')
    print('之後用 Export vocab sources.cmd 匯出的語料也會包含它們。')

if __name__ == '__main__':
    main()
