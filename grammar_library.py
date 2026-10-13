"""文法 · Grammar lessons: serve your own lesson pages inside the reader.

A collection is a folder of HTML lesson pages (for example the JLPT 文法 folder with
its 總目錄 and lessons/). The reader shows it in the 文法 tab next to the dictionary,
so selecting a word in a lesson looks it up like any other reading text.

Where collections come from (all optional, all kept out of Git):
  - grammar_root.txt next to this script: one folder per line, # starts a comment
  - the JP_READER_GRAMMAR environment variable (folders separated by ; on Windows)
  - folders dropped into grammar/ next to this script (for portable copies)

Lesson files are never modified. Each HTML page is served with two small extra tags
(grammar-frame.css / grammar-frame.js) so furigana is left out of text selections and
the page can follow the reader's palette.
"""
import html
import os
import re
from pathlib import Path
from urllib.parse import quote

HERE = Path(__file__).resolve().parent
ROOT_FILE = 'grammar_root.txt'
MIME = {
    '.html': 'text/html; charset=utf-8', '.htm': 'text/html; charset=utf-8',
    '.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8',
    '.json': 'application/json; charset=utf-8', '.txt': 'text/plain; charset=utf-8',
    '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.gif': 'image/gif',
    '.webp': 'image/webp', '.svg': 'image/svg+xml', '.ico': 'image/x-icon',
    '.woff': 'font/woff', '.woff2': 'font/woff2', '.ttf': 'font/ttf', '.otf': 'font/otf',
    '.mp3': 'audio/mpeg', '.m4a': 'audio/mp4', '.ogg': 'audio/ogg', '.wav': 'audio/wav',
}
INJECT = b'<link rel="stylesheet" href="/grammar-frame.css"><script src="/grammar-frame.js"></script>'
INDEX_WORDS = ('總目錄', '总目录', '目錄', '目录', '目次', 'index')
MAX_FILE = 32 * 1024 * 1024


def _pages(folder):
    return sorted(p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in ('.html', '.htm'))


def find_home(root, single=True):
    """The page a collection opens on: index.html, a 總目錄-style page, or (single=True) the only page."""
    try:
        pages = _pages(root)
    except OSError:
        return None
    for page in pages:
        if page.stem.lower() == 'index':
            return page.name
    named = [p for p in pages if any(word in p.stem.lower() for word in INDEX_WORDS)]
    if named:
        return min(named, key=lambda p: (len(p.name), p.name)).name
    return pages[0].name if single and len(pages) == 1 else None


def _clean(line):
    return line.strip().strip('"').strip("'").strip()


def configured(app=HERE, environ=None):
    """Folder paths the user listed, in order, without duplicates."""
    environ = os.environ if environ is None else environ
    lines = []
    listing = Path(app) / ROOT_FILE
    if listing.exists():
        for line in listing.read_text(encoding='utf-8-sig').splitlines():
            line = _clean(line)
            if line and not line.startswith('#'):
                lines.append(line)
    lines += [_clean(p) for p in environ.get('JP_READER_GRAMMAR', '').split(os.pathsep) if _clean(p)]
    drop = Path(app) / 'grammar'
    if drop.is_dir():
        if find_home(drop) or any(drop.glob('*.htm*')):
            lines.append(str(drop))
        else:
            lines += [str(p) for p in sorted(drop.iterdir()) if p.is_dir()]
    seen, result = set(), []
    for line in lines:
        path = Path(line)
        if not path.is_absolute():
            path = Path(app) / path
        try:
            path = path.resolve()
        except OSError:
            continue
        key = os.path.normcase(str(path))
        if key not in seen:
            seen.add(key)
            result.append(path)
    return result


def _collection_root(path):
    """Pointing at a lessons/ folder is fine: its parent holds the index page."""
    if path.is_dir() and (path / 'manifest.js').exists() and not find_home(path, False) and find_home(path.parent, False):
        return path.parent
    return path


class Collection:
    def __init__(self, number, root):
        self.id = str(number)
        self.root = root
        self.title = root.name or str(root)

    @property
    def base(self):
        return '/grammar/' + self.id + '/'

    def home(self):
        name = find_home(self.root)
        return self.base + (quote(name) if name else '')

    def count(self):
        total = 0
        for folder in (self.root, self.root / 'lessons'):
            try:
                total += len(_pages(folder))
            except OSError:
                pass
        return total

    def info(self):
        return {'id': self.id, 'title': self.title, 'home': self.home(), 'path': str(self.root), 'pages': self.count()}

    def resolve(self, relative):
        """A file inside this collection, or None. Never leaves the collection folder."""
        if '\x00' in relative or '\\' in relative:
            return None
        parts = [p for p in relative.split('/') if p not in ('', '.')]
        if any(p == '..' or ':' in p for p in parts):
            return None
        try:
            root = self.root.resolve()
            target = root.joinpath(*parts).resolve()
        except OSError:
            return None
        if target != root and root not in target.parents:
            return None
        return target

    def listing(self):
        """Fallback index for a folder without a 總目錄 page."""
        rows = []
        for folder, prefix in ((self.root, ''), (self.root / 'lessons', 'lessons/')):
            try:
                pages = _pages(folder)
            except OSError:
                continue
            rows += ['<li><a href="%s">%s</a></li>' % (html.escape(quote(prefix + p.name)), html.escape(p.stem)) for p in pages]
        body = '<ul>' + ''.join(rows) + '</ul>' if rows else '<p>這個資料夾裡沒有 HTML 講義。</p>'
        page = ('<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8"><title>%s</title>'
                '<style>body{font:15px/1.8 sans-serif;max-width:840px;margin:0 auto;padding:26px 18px;'
                'background:var(--paper,#f6f2e7);color:var(--ink,#2a2722)}a{color:var(--indigo,#1f3a5f)}'
                'li{margin-bottom:4px}</style></head><body><h1>%s</h1>%s</body></html>') % (
                    html.escape(self.title), html.escape(self.title), body)
        return inject(page.encode('utf-8'))


def collections(app=HERE, environ=None):
    result = []
    for path in configured(app, environ):
        root = _collection_root(path)
        if root.is_dir() and not any(os.path.normcase(str(c.root)) == os.path.normcase(str(root)) for c in result):
            result.append(Collection(len(result), root))
    return result


def inject(raw):
    """Add the reader's frame stylesheet and script to a lesson page (in memory only)."""
    if b'/grammar-frame.js' in raw:
        return raw
    match = re.search(rb'</head\s*>', raw, re.I) or re.search(rb'<body\b', raw, re.I)
    if match:
        return raw[:match.start()] + INJECT + raw[match.start():]
    return INJECT + raw


def serve(path, app=HERE, environ=None):
    """(bytes, mime) for a /grammar/<id>/<file> URL path that is already percent-decoded."""
    match = re.fullmatch(r'/grammar/(\d+)(?:/(.*))?', path)
    if not match:
        raise LookupError('Not found')
    found = {c.id: c for c in collections(app, environ)}.get(match.group(1))
    if found is None:
        raise LookupError('Unknown grammar collection')
    relative = match.group(2) or ''
    if not relative.strip('/'):
        home = find_home(found.root)
        if not home:
            return found.listing(), MIME['.html']
        relative = home
    target = found.resolve(relative)
    if target is None or not target.is_file():
        raise LookupError('Not found')
    mime = MIME.get(target.suffix.lower())
    if mime is None:
        raise LookupError('File type is not served')
    if target.stat().st_size > MAX_FILE:
        raise LookupError('File is too large')
    raw = target.read_bytes()
    if target.suffix.lower() in ('.html', '.htm'):
        raw = inject(raw)
    return raw, mime


def missing_page(path, message):
    """A small themed page for a lesson link whose file is not in the folder."""
    name = html.escape(path.rsplit('/', 1)[-1] or path)
    page = ('<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8"><title>找不到講義</title>'
            '<style>body{font:15px/1.8 sans-serif;max-width:640px;margin:0 auto;padding:40px 18px;'
            'background:var(--paper,#f6f2e7);color:var(--ink,#2a2722)}code{color:var(--muted,#6b6357)}'
            'a{color:var(--indigo,#1f3a5f)}</style></head><body><h2>找不到這一頁</h2>'
            '<p>講義資料夾裡沒有 <code>%s</code>（%s）。</p>'
            '<p><a href="javascript:history.back()">← 回上一頁</a></p></body></html>') % (name, html.escape(message))
    return inject(page.encode('utf-8'))


def add_root(folder, app=HERE):
    """Remember a lesson folder in grammar_root.txt. Returns the collection it became."""
    text = _clean(str(folder or ''))
    if not text or len(text) > 1000 or '\n' in text or '\r' in text:
        raise ValueError('請貼上講義資料夾的完整路徑。')
    path = Path(text)
    if not path.is_absolute():
        raise ValueError('請使用完整路徑，例如 C:\\Users\\you\\Desktop\\JLPT文法。')
    try:
        path = path.resolve()
    except OSError as error:
        raise ValueError('無法讀取這個路徑：' + str(error))
    if not path.is_dir():
        raise ValueError('找不到這個資料夾：' + str(path))
    root = _collection_root(path)
    try:
        has_pages = bool(_pages(root)) or (root / 'lessons').is_dir() and bool(_pages(root / 'lessons'))
    except OSError as error:
        raise ValueError('無法讀取這個資料夾：' + str(error))
    if not has_pages:
        raise ValueError('這個資料夾裡沒有 HTML 講義。請選擇放總目錄和 lessons 的那一層。')
    existing = collections(app)
    for item in existing:
        if os.path.normcase(str(item.root)) == os.path.normcase(str(root)):
            return item
    listing = Path(app) / ROOT_FILE
    previous = listing.read_text(encoding='utf-8-sig') if listing.exists() else (
        '# 文法講義資料夾，一行一個（放總目錄和 lessons 的那一層）。這個檔案不會進 Git。\n')
    if previous and not previous.endswith('\n'):
        previous += '\n'
    try:
        listing.write_text(previous + str(root) + '\n', encoding='utf-8')
    except OSError as error:
        raise ValueError('無法寫入 grammar_root.txt：' + str(error))
    for item in collections(app):
        if os.path.normcase(str(item.root)) == os.path.normcase(str(root)):
            return item
    raise ValueError('已寫入 grammar_root.txt，但無法開啟這個資料夾。')
