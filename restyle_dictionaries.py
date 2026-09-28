"""Washi restyle for the MDX dictionaries — desktop reader and iPhone app.

  python restyle_dictionaries.py            (or double-click "Restyle dictionaries.cmd")
  python restyle_dictionaries.py --restore  (put every publisher stylesheet back)

For each dictionary that has an overlay in dict_styles\\washi\\<code>.css:
  * the publisher stylesheet named in dictionaries\\mdict-index.sqlite3 is backed up once to
    <dictionary folder>\\_original_css\\ ;
  * the stylesheet is rewritten as  original + Washi overlay  (same file name, so the index
    and the iPhone copy of the index stay valid);
  * the finished stylesheets are also packed into dictionaries\\iPhone dictionary styles.zip
    for copying to the phone.
Running it again rebuilds from the backups, so it is safe to repeat after an update.
デジタル大辞泉 and 広辞苑 already use their own Washi stylesheets and are left as they are.
"""
import shutil, sqlite3, sys, zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
DICT = HERE / 'dictionaries'
INDEX = DICT / 'mdict-index.sqlite3'
OVERLAYS = HERE / 'dict_styles' / 'washi'
BACKUP = '_original_css'
MARKER = '/* ==== Washi restyle (jp-game-reader)'
ZIP = DICT / 'iPhone dictionary styles.zip'


def catalog():
    db = sqlite3.connect(INDEX.resolve().as_uri() + '?mode=ro', uri=True, timeout=30)
    try:
        return {code: (root, css) for code, root, css in db.execute('SELECT code, root, css FROM dictionaries')}
    finally:
        db.close()


def folder_of(root):
    path = (DICT / root).resolve()
    if not path.is_relative_to(DICT.resolve()):
        raise ValueError(f'不安全的路徑：{root}')
    return path


def read(path):
    return path.read_text(encoding='utf-8-sig', errors='replace') if path.exists() else ''


def apply():
    cat = catalog()
    done, packed = [], []
    for overlay in sorted(OVERLAYS.glob('*.css')):
        code = overlay.stem
        if code not in cat:
            print(f'  – {code}：索引裡沒有這本辭典，略過'); continue
        root, css = cat[code]
        if not css:
            print(f'  – {code}：索引沒有指定樣式表，略過（請告訴 Claude）'); continue
        folder = folder_of(root)
        target = folder / css
        backup = folder / BACKUP / css
        if not backup.exists():
            backup.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                shutil.copy2(target, backup)
            else:
                backup.write_text('', encoding='utf-8')
        original = read(backup)
        if MARKER in original:                      # never stack overlays
            original = original.split(MARKER)[0].rstrip() + '\n'
        target.write_text(original.rstrip() + '\n\n' + read(overlay), encoding='utf-8')
        done.append(code)
        packed.append((target, Path(root) / css))
        print(f'  ✓ {code}  →  {Path(root) / css}')
    with zipfile.ZipFile(ZIP, 'w', zipfile.ZIP_DEFLATED) as z:
        for src, rel in packed:
            z.write(src, 'dictionaries/' + rel.as_posix())
        z.writestr('README.txt', PHONE_README + '\n'.join('dictionaries/' + r.as_posix() for _, r in packed) + '\n')
    print(f'\n完成：{len(done)} 本辭典已換上新樣式。電腦版閱讀器重新打開辭典頁即可看到。')
    print(f'iPhone 用的樣式檔已打包：{ZIP}')


def restore():
    cat = catalog()
    for code, (root, css) in sorted(cat.items()):
        if not css:
            continue
        folder = folder_of(root)
        backup = folder / BACKUP / css
        if backup.exists():
            shutil.copy2(backup, folder / css)
            print(f'  ↺ {code}  →  已還原原本的樣式表')
    print('完成：已還原。')


PHONE_README = '''iPhone：把每個 .css 放進「檔案 → 我的 iPhone → Japanese Reader → dictionaries → sources」裡
同名的資料夾（例如 MDX_CROWN），選「取代」。只換 .css，不要取代整個資料夾。
然後在 App 裡 Library → Refresh dictionaries。

On the iPhone, put each .css into the folder of the same name under
On My iPhone → Japanese Reader → dictionaries → sources, and choose Replace.
Replace only the .css file, never the whole folder. Then Library → Refresh dictionaries.

Files:
'''

if __name__ == '__main__':
    if not INDEX.exists():
        raise SystemExit('找不到 dictionaries\\mdict-index.sqlite3')
    if '--restore' in sys.argv:
        restore()
    else:
        print('辭典 Washi 新樣式（原本的樣式表會先備份到各辭典資料夾的 _original_css）')
        apply()
