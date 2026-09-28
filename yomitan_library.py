"""Yomitan / Yomichan dictionaries (.zip) for the local reader.

Zips are imported once into dictionaries/yomitan-index.sqlite3; afterwards the
reader needs only that index (the zips can move or be deleted). Sources:

* every *.zip in dictionaries/yomitan/
* every file or folder listed in dictionaries/yomitan-paths.txt (one per line, # comments)

Term dictionaries become their own tabs. All kanji dictionaries and kanji
frequency lists merge into one 漢字 tab (a kanji card per character). Term
frequency lists show as rank chips beside the looked-up word.
"""
import hashlib, html, json, mimetypes, os, re, sqlite3, threading, time, unicodedata, zipfile, zlib
from contextlib import closing
from pathlib import Path
from urllib.parse import urlencode, parse_qs, urlsplit

HERE = Path(__file__).resolve().parent
INDEX = Path(os.environ.get('JP_READER_YOMITAN_INDEX', str(HERE / 'dictionaries' / 'yomitan-index.sqlite3')))
SOURCE_DIR = INDEX.parent / 'yomitan'
PATHS_FILE = INDEX.parent / 'yomitan-paths.txt'
KANJI_CODE = 'YT_KANJI'
SCHEMA = 4

# Friendlier names for well-known dictionaries (title in index.json -> shown name).
NAMES = {
    'JMdict (English)': 'JMdict 和英',
    'Pixiv': 'ピクシブ百科事典 · Pixiv',
    'PixivLight': 'ピクシブ百科事典 · Pixiv Light',
    'surasura 擬声語': 'オノマトペ · surasura',
    'Nico/Pixiv': 'ニコニコ・ピクシブ 見出し',
    '複合語起源': '複合語起源',
    '青空文庫熟語': '青空文庫 語彙頻度',
    'CantoDict': 'CantoDict 粵語',
    'Japanese-Mongolian/日・モ辞典': '日・モ辞典',
}
# Imported, but left unticked the first time (name lists, other languages, duplicates).
DEFAULT_OFF = {'Nico/Pixiv', 'PixivLight', 'CantoDict', 'Japanese-Mongolian/日・モ辞典'}
# Short labels for kanji sources inside the merged kanji card.
KANJI_LABELS = {
    'KANJIDIC (English)': 'KANJIDIC',
    'JPDB Kanji': 'JPDB',
    'TheKanjiMap Kanji Radicals/Composition': '部首・構成 · TheKanjiMap',
    'Wiktionary漢字': 'ウィクショナリー 漢字',
    'ZH Wiktionary Hanzi': '中文維基詞典 漢字',
    'jitai': '字体 · jitai',
    'mozc Kanji Variants': '異体字 · mozc',
    '青空文庫漢字': '青空文庫',
    'Innocent Corpus Kanji': '小説',
    'JPDB Kanji Freq': 'JPDB',
    'Wikipedia Kanji': 'Wikipedia',
}

_lock = threading.Lock()
status = {'importing': False, 'message': '', 'error': ''}


# ----------------------------------------------------------------------------- helpers
def _hira(text):
    return ''.join(chr(ord(c) - 0x60) if 'ァ' <= c <= 'ヶ' else c for c in text)


def normalize(word):
    return unicodedata.normalize('NFKC', word or '').strip().casefold()


def norm_reading(word):
    return _hira(normalize(word))


def _clean_title(title):
    return re.sub(r'\s*\[\d{4}-\d\d-\d\d\]\s*$', '', title or '').strip() or 'Yomitan dictionary'


def _code(title):
    return 'YT_' + hashlib.sha1(_clean_title(title).encode('utf-8')).hexdigest()[:8].upper()


def sources():
    found = []
    if SOURCE_DIR.is_dir():
        found += sorted(SOURCE_DIR.glob('*.zip'))
    if PATHS_FILE.is_file():
        for line in PATHS_FILE.read_text(encoding='utf-8-sig').splitlines():
            line = line.strip().strip('"')
            if not line or line.startswith('#'):
                continue
            path = Path(os.path.expandvars(os.path.expanduser(line)))
            if not path.is_absolute():
                path = INDEX.parent / path
            if path.is_dir():
                found += sorted(path.glob('*.zip'))
            elif path.is_file() and path.suffix.lower() == '.zip':
                found.append(path)
    unique, seen = [], set()
    for path in found:
        key = str(path.resolve()).casefold()
        if key not in seen:
            seen.add(key)
            unique.append(path.resolve())
    return unique


def _signature(paths):
    items = []
    for p in paths:
        try:
            st = p.stat()
            items.append([str(p), st.st_size, int(st.st_mtime)])
        except OSError:
            pass
    return json.dumps({'schema': SCHEMA, 'files': items}, ensure_ascii=False)


def connect():
    db = sqlite3.connect(INDEX.resolve().as_uri() + '?mode=ro', uri=True, timeout=10)
    db.row_factory = sqlite3.Row
    return db


def available():
    return INDEX.exists()


# ----------------------------------------------------------------------------- import
def _banks(zf, prefix):
    names = [n for n in zf.namelist() if re.fullmatch(prefix + r'_bank_\d+\.json', n.rsplit('/', 1)[-1])]
    return sorted(names, key=lambda n: int(re.search(r'(\d+)\.json$', n)[1]))


def _fix(value):
    """Repair UTF-16 surrogate halves some dictionary builders leave in JSON strings."""
    if isinstance(value, str):
        try:
            value.encode('utf-8')
            return value
        except UnicodeEncodeError:
            return value.encode('utf-16', 'surrogatepass').decode('utf-16', 'replace')
    if isinstance(value, list):
        return [_fix(v) for v in value]
    if isinstance(value, dict):
        return {_fix(k): _fix(v) for k, v in value.items()}
    return value


def _pack(value):
    return zlib.compress(json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode('utf-8'), 6)


def _unpack(blob):
    return json.loads(zlib.decompress(blob).decode('utf-8') if isinstance(blob, bytes) else blob)


def _load(zf, name):
    return _fix(json.loads(zf.read(name).decode('utf-8-sig')))


def build(paths=None, target=None, log=print):
    """Import every Yomitan zip into a fresh index, then swap it into place."""
    paths = sources() if paths is None else [Path(p) for p in paths]
    target = Path(target or INDEX)
    target.parent.mkdir(parents=True, exist_ok=True)
    pending = target.with_suffix('.building')
    if pending.exists():
        pending.unlink()
    db = sqlite3.connect(pending)
    db.executescript('''
        PRAGMA journal_mode=OFF; PRAGMA synchronous=OFF;
        CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT);
        CREATE TABLE dictionaries(code TEXT PRIMARY KEY, title TEXT, name TEXT, kind TEXT, revision TEXT, source TEXT,
            attribution TEXT, url TEXT, author TEXT, description TEXT, position INTEGER, terms INTEGER, kanji INTEGER,
            term_meta INTEGER, kanji_meta INTEGER);
        CREATE TABLE terms(id INTEGER PRIMARY KEY, dict TEXT, expression TEXT, reading TEXT, nexp TEXT, nread TEXT,
            def_tags TEXT, rules TEXT, score REAL, glossary BLOB, sequence INTEGER, term_tags TEXT);
        CREATE TABLE kanji(id INTEGER PRIMARY KEY, dict TEXT, character TEXT, onyomi TEXT, kunyomi TEXT, tags TEXT,
            meanings TEXT, stats TEXT);
        CREATE TABLE term_meta(dict TEXT, expression TEXT, nexp TEXT, mode TEXT, data TEXT);
        CREATE TABLE kanji_meta(dict TEXT, character TEXT, mode TEXT, data TEXT);
        CREATE TABLE tags(dict TEXT, name TEXT, category TEXT, ord REAL, notes TEXT, score REAL);
        CREATE TABLE media(dict TEXT, path TEXT, data BLOB);
    ''')
    position = 0
    for path in paths:
        try:
            zf = zipfile.ZipFile(path)
        except (OSError, zipfile.BadZipFile) as e:
            log(f'  skipped {path.name}: {e}')
            continue
        with zf:
            names = zf.namelist()
            index_name = next((n for n in names if n.rsplit('/', 1)[-1] == 'index.json'), None)
            if not index_name:
                log(f'  skipped {path.name}: no index.json (not a Yomitan dictionary)')
                continue
            info = _load(zf, index_name)
            title = _clean_title(info.get('title'))
            code = _code(title)
            if db.execute('SELECT 1 FROM dictionaries WHERE code=?', (code,)).fetchone():
                log(f'  skipped {path.name}: “{title}” is already imported from another file')
                continue
            log(f'  importing {title} …')
            counts = {'terms': 0, 'kanji': 0, 'term_meta': 0, 'kanji_meta': 0}
            for bank in _banks(zf, 'term'):
                rows = []
                for r in _load(zf, bank):
                    if len(r) < 6:
                        continue
                    if len(r) == 6:  # format 1: expression, reading, def_tags, rules, score, *glossary
                        r = [r[0], r[1], r[2], r[3], r[4], r[5:], 0, '']
                    expression, reading = str(r[0]), str(r[1] or r[0])
                    rows.append((code, expression, reading, normalize(expression), norm_reading(reading),
                                 r[2] or '', r[3] or '', r[4] or 0, _pack(r[5]),
                                 r[6] if len(r) > 6 and isinstance(r[6], int) else 0, r[7] if len(r) > 7 and r[7] else ''))
                db.executemany('INSERT INTO terms(dict,expression,reading,nexp,nread,def_tags,rules,score,glossary,sequence,term_tags) VALUES(?,?,?,?,?,?,?,?,?,?,?)', rows)
                counts['terms'] += len(rows)
            for bank in _banks(zf, 'kanji'):
                rows = []
                for r in _load(zf, bank):
                    if len(r) < 5:
                        continue
                    meanings = r[4] if isinstance(r[4], list) else r[4:]
                    stats = r[5] if len(r) > 5 and isinstance(r[5], dict) else {}
                    rows.append((code, str(r[0]), r[1] or '', r[2] or '', r[3] or '',
                                 json.dumps(meanings, ensure_ascii=False), json.dumps(stats, ensure_ascii=False)))
                db.executemany('INSERT INTO kanji(dict,character,onyomi,kunyomi,tags,meanings,stats) VALUES(?,?,?,?,?,?,?)', rows)
                counts['kanji'] += len(rows)
            for bank in _banks(zf, 'term_meta'):
                rows = [(code, str(r[0]), normalize(str(r[0])), r[1], json.dumps(r[2], ensure_ascii=False)) for r in _load(zf, bank) if len(r) >= 3]
                db.executemany('INSERT INTO term_meta VALUES(?,?,?,?,?)', rows)
                counts['term_meta'] += len(rows)
            for bank in _banks(zf, 'kanji_meta'):
                rows = [(code, str(r[0]), r[1], json.dumps(r[2], ensure_ascii=False)) for r in _load(zf, bank) if len(r) >= 3]
                db.executemany('INSERT INTO kanji_meta VALUES(?,?,?,?)', rows)
                counts['kanji_meta'] += len(rows)
            for bank in _banks(zf, 'tag'):
                rows = []
                for r in _load(zf, bank):
                    if len(r) >= 5:
                        rows.append((code, str(r[0]), r[1] or '', r[2] or 0, r[3] or '', r[4] or 0))
                db.executemany('INSERT INTO tags VALUES(?,?,?,?,?,?)', rows)
            for n in names:
                if not n.endswith('/') and not n.lower().endswith('.json') and mimetypes.guess_type(n)[0]:
                    db.execute('INSERT INTO media VALUES(?,?,?)', (code, n, zf.read(n)))
            if counts['terms']:
                kind = 'term'
            elif counts['kanji'] or counts['kanji_meta']:
                kind = 'kanji'
            elif counts['term_meta']:
                kind = 'freq'
            else:
                log(f'  skipped {title}: no entries')
                continue
            position += 1
            db.execute('INSERT INTO dictionaries VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)', (
                code, title, NAMES.get(title, title), kind, str(info.get('revision', '')), path.name,
                info.get('attribution', ''), info.get('url', ''), info.get('author', ''), info.get('description', ''),
                position, counts['terms'], counts['kanji'], counts['term_meta'], counts['kanji_meta']))
            log('    ' + ', '.join(f'{v:,} {k}' for k, v in counts.items() if v))
    db.executescript('''
        CREATE INDEX terms_exp ON terms(dict,nexp);
        CREATE INDEX terms_read ON terms(dict,nread);
        CREATE INDEX kanji_char ON kanji(character);
        CREATE INDEX term_meta_exp ON term_meta(nexp);
        CREATE INDEX kanji_meta_char ON kanji_meta(character);
        CREATE INDEX tags_name ON tags(dict,name);
        CREATE INDEX media_path ON media(dict,path);
        ANALYZE;
    ''')
    db.execute('INSERT INTO meta VALUES(?,?)', ('signature', _signature(paths)))
    db.commit()
    db.close()
    for attempt in range(20):
        try:
            os.replace(pending, target)
            break
        except PermissionError:  # a reader request may briefly hold the old index open (Windows)
            time.sleep(0.25)
    else:
        raise OSError('Could not replace ' + str(target))
    _catalog_cache.clear()
    return target


def needs_import():
    paths = sources()
    if not paths:
        return False  # never discard an index whose zips have been moved away (portable copies)
    if not INDEX.exists():
        return True
    try:
        with closing(connect()) as db:
            row = db.execute("SELECT value FROM meta WHERE key='signature'").fetchone()
        return row is None or row[0] != _signature(paths)
    except sqlite3.Error:
        return True


def ensure_async(log=None):
    """Import new or changed zips in the background; the reader keeps working meanwhile."""
    def run():
        with _lock:
            try:
                if not needs_import():
                    return
                status.update(importing=True, message='Importing Yomitan dictionaries…', error='')
                messages = []
                build(log=lambda m: (messages.append(m), status.update(message=m.strip()), log and log(m)))
                status.update(message='Imported Yomitan dictionaries.')
            except Exception as e:  # keep the reader running; show the problem in the dictionary chooser
                status.update(error=str(e))
            finally:
                status['importing'] = False
    threading.Thread(target=run, daemon=True, name='yomitan-import').start()


# ----------------------------------------------------------------------------- catalog / search
_catalog_cache = {}


def _dicts(db):
    return [dict(r) for r in db.execute('SELECT * FROM dictionaries ORDER BY position')]


def dictionaries():
    """Catalog rows: term dictionaries, one merged kanji tab, and frequency lists."""
    if not INDEX.exists():
        return []
    stamp = INDEX.stat().st_mtime_ns
    if _catalog_cache.get('stamp') == stamp:
        return _catalog_cache['rows']
    out = []
    try:
        with closing(connect()) as db:
            rows = _dicts(db)
    except sqlite3.Error:
        return []
    kanji = [d for d in rows if d['kind'] == 'kanji']
    for d in rows:
        if d['kind'] == 'term':
            out.append({'code': d['code'], 'name': d['name'], 'kind': 'term', 'source': 'yomitan', 'default_on': d['title'] not in DEFAULT_OFF})
        elif d['kind'] == 'freq':
            out.append({'code': d['code'], 'name': d['name'], 'kind': 'freq', 'source': 'yomitan'})
    if kanji:
        out.append({'code': KANJI_CODE, 'name': '漢字 · Kanji', 'kind': 'kanji', 'source': 'yomitan',
                    'parts': [KANJI_LABELS.get(d['title'], d['name']) for d in kanji]})
    _catalog_cache.update(stamp=stamp, rows=out)
    return out


def _entry_row(r):
    exp, reading = r['expression'], r['reading']
    if reading and reading != exp and _KANJI.search(exp):
        return {'id': r['id'], 'title': reading, 'label': exp, 'anchor': ''}
    return {'id': r['id'], 'title': exp, 'label': '', 'anchor': ''}


_KANJI = re.compile(r'[㐀-䶿一-鿿豈-﫿々〆ヶ\U00020000-\U0003FFFF]')


def _kanji_chars(db, word):
    chars = []
    for ch in dict.fromkeys(unicodedata.normalize('NFKC', word)):
        if not _KANJI.search(ch) and not ('⺀' <= ch <= '⿟'):
            continue
        if db.execute('SELECT 1 FROM kanji WHERE character=? UNION ALL SELECT 1 FROM kanji_meta WHERE character=? LIMIT 1', (ch, ch)).fetchone():
            chars.append(ch)
    return chars[:24]


def search(word, codes=None):
    """Results in the same shape as mdict_library.search, plus frequency chips."""
    if not INDEX.exists():
        return [], []
    key, rkey = normalize(word), norm_reading(word)
    results, freqs = [], []
    with closing(connect()) as db:
        for d in dictionaries():
            if codes is not None and d['code'] not in codes:
                continue
            if d['kind'] == 'term':
                rows = db.execute('SELECT MIN(id) id, expression, reading, MAX(score) s, MAX(nexp=?) e FROM terms WHERE id IN '
                                  '(SELECT id FROM terms WHERE dict=? AND nexp=? UNION SELECT id FROM terms WHERE dict=? AND nread=?) '
                                  'GROUP BY expression, reading ORDER BY e DESC, s DESC, id LIMIT 80', (key, d['code'], key, d['code'], rkey)).fetchall()
                exact = bool(rows)
                if len(rows) < 80:
                    rows += db.execute('SELECT MIN(id) id, expression, reading FROM terms WHERE dict=? AND nexp>? AND nexp<? '
                                       'GROUP BY expression, reading ORDER BY length(expression), nexp LIMIT ?',
                                       (d['code'], key, key + '\U0010ffff', 80 - len(rows))).fetchall()
                entries = [_entry_row(r) for r in rows]
                results.append({'code': d['code'], 'name': d['name'], 'kind': 'term', 'count': len(entries), 'exact': exact, 'entries': entries})
            elif d['kind'] == 'kanji':
                chars = _kanji_chars(db, word)
                entries = [{'id': ord(c), 'title': c, 'label': '', 'anchor': ''} for c in chars]
                results.append({'code': d['code'], 'name': d['name'], 'kind': 'kanji', 'count': len(entries), 'exact': bool(entries), 'entries': entries})
            elif d['kind'] == 'freq':
                for f in _term_freqs(db, word, [d['code']]):
                    freqs.append(f)
    return results, freqs


def _freq_value(data):
    """(sort value, display text, reading) for any Yomitan frequency format."""
    reading = ''
    if isinstance(data, dict) and 'frequency' in data:
        reading = data.get('reading', '')
        data = data['frequency']
    if isinstance(data, dict):
        value = data.get('value')
        shown = data.get('displayValue') or (str(value) if value is not None else '')
    else:
        value, shown = data, str(data)
    shown = re.sub(r'^(\d+)(\s*\(\d+\))?$', lambda m: f'{int(m[1]):,}', str(shown).strip())
    try:
        value = float(value)
    except (TypeError, ValueError):
        value = None
    return value, shown, reading


def _term_freqs(db, word, codes):
    out = []
    names = {d['code']: d['name'] for d in dictionaries()}
    for code in codes:
        rows = db.execute("SELECT data FROM term_meta WHERE nexp=? AND dict=? AND mode='freq' LIMIT 8", (normalize(word), code)).fetchall()
        seen = set()
        for r in rows:
            value, shown, reading = _freq_value(json.loads(r['data']))
            if shown in seen:
                continue
            seen.add(shown)
            out.append({'code': code, 'name': names.get(code, code), 'value': value, 'display': shown, 'reading': reading})
    return out


def labels(code, ids):
    return {}


# ----------------------------------------------------------------------------- structured content
def _route(kind, code, **kw):
    return '/api/dictionary/' + kind + '?' + urlencode({'code': code, **kw})


_STYLE_KEYS = {
    'fontSize': 'font-size', 'fontWeight': 'font-weight', 'fontStyle': 'font-style', 'textDecorationLine': 'text-decoration-line',
    'verticalAlign': 'vertical-align', 'textAlign': 'text-align', 'marginTop': 'margin-top', 'marginLeft': 'margin-left',
    'marginRight': 'margin-right', 'marginBottom': 'margin-bottom', 'paddingLeft': 'padding-left', 'listStyleType': 'list-style-type',
    'whiteSpace': 'white-space', 'wordBreak': 'word-break',
}
_TAGS = {'span', 'div', 'ol', 'ul', 'li', 'table', 'thead', 'tbody', 'tfoot', 'tr', 'td', 'th', 'ruby', 'rt', 'rp',
         'details', 'summary', 'a', 'img', 'br', 'sup', 'sub', 'b', 'i', 'strong', 'em'}


def _style(style):
    if not isinstance(style, dict):
        return ''
    parts = []
    for k, v in style.items():
        css = _STYLE_KEYS.get(k)
        if not css:
            continue
        if isinstance(v, (int, float)):
            v = f'{v}em' if 'margin' in css or 'padding' in css else str(v)
        if isinstance(v, list):
            v = ' '.join(map(str, v))
        v = str(v)
        if re.search(r'[;{}<>\\]|url\(|expression', v, re.I):
            continue
        parts.append(f'{css}:{v}')
    return ';'.join(parts)


def _attr(name, value):
    return f' {name}="{html.escape(str(value), quote=True)}"'


def _lookup_link(code, word, inner):
    return f'<a class="yt-link"{_attr("href", _route("resolve", code, word=word))}{_attr("data-lookup", word)}>{inner}</a>'


def render_sc(node, code):
    if node is None:
        return ''
    if isinstance(node, str):
        return html.escape(node).replace('\n', '<br>')
    if isinstance(node, (int, float)):
        return html.escape(str(node))
    if isinstance(node, list):
        return ''.join(render_sc(n, code) for n in node)
    if not isinstance(node, dict):
        return ''
    kind = node.get('type')
    if kind == 'structured-content':
        return render_sc(node.get('content'), code)
    if kind == 'text':
        return html.escape(node.get('text', '')).replace('\n', '<br>')
    if kind == 'image':
        return _image(node, code)
    tag = node.get('tag')
    if not tag:
        return render_sc(node.get('content'), code)
    if tag == 'br':
        return '<br>'
    if tag == 'img':
        return _image(node, code)
    out_tag = tag if tag in _TAGS else 'span'
    attrs = ''
    data = node.get('data')
    if isinstance(data, dict):
        for k, v in data.items():
            k = re.sub(r'[^a-z0-9-]', '-', str(k).lower())[:40]
            attrs += _attr('data-sc-' + k, v)
    style = _style(node.get('style'))
    if style:
        attrs += _attr('style', style)
    for key in ('lang', 'title'):
        if node.get(key):
            attrs += _attr(key, node[key])
    if tag in ('td', 'th'):
        for key, name in (('colSpan', 'colspan'), ('rowSpan', 'rowspan')):
            if node.get(key):
                attrs += _attr(name, node[key])
    if tag == 'details' and node.get('open'):
        attrs += ' open'
    inner = render_sc(node.get('content'), code)
    if tag == 'a':
        href = str(node.get('href', ''))
        if href.startswith('?'):
            word = parse_qs(urlsplit(href).query).get('query', [''])[0]
            return _lookup_link(code, word, inner) if word else inner
        if re.match(r'https?://', href):
            return f'<a class="yt-external"{_attr("href", href)}{_attr("data-external", href)} rel="noopener noreferrer">{inner}</a>'
        return inner
    return f'<{out_tag}{attrs}>{inner}</{out_tag}>'


def _image(node, code):
    path = node.get('path')
    if not path:
        return ''
    attrs = _attr('src', _route('media', code, name=path)) + _attr('alt', node.get('title') or node.get('alt') or '')
    size = []
    for key in ('width', 'height'):
        if isinstance(node.get(key), (int, float)):
            size.append(f'{key}:{node[key]}{node.get("sizeUnits", "px") if node.get("sizeUnits") == "em" else "px"}')
    if size:
        attrs += _attr('style', ';'.join(size))
    cls = 'yt-img' + (' yt-img-inline' if node.get('verticalAlign') or node.get('collapsible') is False else '')
    return f'<img class="{cls}"{attrs}>'


def media(code, name):
    with closing(connect()) as db:
        row = db.execute('SELECT data FROM media WHERE dict=? AND path=?', (code, name)).fetchone()
    if row is None:
        raise ValueError('This image is not part of the dictionary.')
    return row['data'], mimetypes.guess_type(name)[0] or 'application/octet-stream'


# ----------------------------------------------------------------------------- pages
def _furigana(expression, reading):
    """Ruby markup, with okurigana left outside the ruby when it can be aligned."""
    esc = html.escape
    if not reading or reading == expression or not _KANJI.search(expression):
        return esc(expression)
    parts = re.findall(r'[㐀-䶿一-鿿豈-﫿々〆ヶ\U00020000-\U0003FFFF]+|[^㐀-䶿一-鿿豈-﫿々〆ヶ\U00020000-\U0003FFFF]+', expression)
    pattern = ''.join('(.+?)' if _KANJI.match(p) else '(' + re.escape(_hira(p)) + ')' for p in parts)
    m = re.fullmatch(pattern, _hira(reading))
    if not m:
        return f'<ruby>{esc(expression)}<rt>{esc(reading)}</rt></ruby>'
    out = []
    for i, part in enumerate(parts, 1):
        span = reading[m.start(i):m.end(i)]  # _hira keeps length, so offsets match the original reading
        out.append(f'<ruby>{esc(part)}<rt>{esc(span)}</rt></ruby>' if _KANJI.match(part) else esc(part))
    return ''.join(out)


def _tag_map(db, code):
    return {r['name']: dict(r) for r in db.execute('SELECT name,category,notes FROM tags WHERE dict=?', (code,))}


def _tag_pills(names, tags, extra_class=''):
    out = []
    for name in dict.fromkeys(n for n in (names or '').split() if n):
        info = tags.get(name, {})
        cat = re.sub(r'[^a-z0-9-]', '', (info.get('category') or 'default').lower()) or 'default'
        title = info.get('notes') or ''
        out.append(f'<span class="yt-tag yt-tag-{cat} {extra_class}"{_attr("title", title) if title else ""}>{html.escape(name)}</span>')
    return ''.join(out)


def _glossary(items, code):
    if not isinstance(items, list):
        items = [items]
    simple = all(isinstance(g, str) for g in items)
    if simple and len(items) > 1 and all(len(g) < 120 and '\n' not in g for g in items):
        return '<div class="yt-gloss yt-gloss-list">' + '<span class="yt-sep">；</span>'.join(f'<span class="yt-g">{html.escape(g)}</span>' for g in items) + '</div>'
    return ''.join(f'<div class="yt-gloss">{render_sc(g, code)}</div>' for g in items)


def _page(code, title, name, body, lang='ja'):
    return ('<!doctype html><html lang="' + lang + '"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            '<body class="mdict-entry yomitan-entry" data-dict="' + html.escape(code, quote=True) + '">'
            '<div class="dictionary-source">' + html.escape(name) + ' · ' + html.escape(title) + '</div>' + body +
            '<link rel="stylesheet" href="/dictionary-entry.css"></body></html>').encode('utf-8')


def _info(db, code):
    row = db.execute('SELECT * FROM dictionaries WHERE code=?', (code,)).fetchone()
    if row is None:
        raise ValueError('Unknown Yomitan dictionary.')
    return dict(row)


def _freq_chips(freqs):
    if not freqs:
        return ''
    chips = ''.join(f'<span class="yt-freq"><span class="yt-freq-name">{html.escape(f["name"])}</span>'
                    f'<span class="yt-freq-value">{html.escape(f["display"])}</span></span>' for f in freqs)
    return f'<div class="yt-freqs" aria-label="Frequency">{chips}</div>'


def _attribution(d):
    bits = [html.escape(d.get('attribution') or d.get('author') or '')]
    if d.get('url'):
        bits.append(f'<a class="yt-external"{_attr("href", d["url"])}{_attr("data-external", d["url"])}>{html.escape(re.sub(r"^https?://", "", d["url"]).rstrip("/")[:60])}</a>')
    bits = [b for b in bits if b]
    return f'<footer class="yt-credit">{" · ".join(bits)}</footer>' if bits else ''


def term_entry(code, entry_id):
    with closing(connect()) as db:
        d = _info(db, code)
        first = db.execute('SELECT * FROM terms WHERE id=? AND dict=?', (int(entry_id), code)).fetchone()
        if first is None:
            raise ValueError('Entry not found in this dictionary.')
        rows = db.execute('SELECT * FROM terms WHERE dict=? AND expression=? AND reading=? ORDER BY score DESC, sequence, id',
                          (code, first['expression'], first['reading'])).fetchall()
        tags = _tag_map(db, code)
        freq_codes = [x['code'] for x in dictionaries() if x['kind'] == 'freq']
        freqs = _term_freqs(db, first['expression'], freq_codes)
    exp, reading = first['expression'], first['reading']
    term_tags = ' '.join(r['term_tags'] for r in rows if r['term_tags'])
    head = (f'<header class="yt-head"><h1 class="yt-headword" lang="ja">{_furigana(exp, reading)}</h1>'
            + (f'<div class="yt-head-tags">{_tag_pills(term_tags, tags)}</div>' if term_tags.strip() else '')
            + '</header>' + _freq_chips(freqs))
    senses = []
    for r in rows:
        gloss = _glossary(_unpack(r['glossary']), code)
        pills = _tag_pills(r['def_tags'], tags)
        senses.append(f'<li class="yt-sense">{f"<div class=yt-tags>{pills}</div>" if pills else ""}{gloss}</li>')
    listing = f'<ol class="yt-senses{" yt-single" if len(senses) == 1 else ""}">{"".join(senses)}</ol>'
    title = exp + (f'【{reading}】' if reading != exp else '')
    return _page(code, title, d['name'], f'<article class="yt-entry">{head}{listing}</article>{_attribution(d)}')


def resolve(code, word):
    if code == KANJI_CODE:
        ch = unicodedata.normalize('NFKC', word or '')[:1]
        return kanji_entry(ord(ch)) if ch else _missing(code, word)
    with closing(connect()) as db:
        row = (db.execute('SELECT id FROM terms WHERE dict=? AND nexp=? ORDER BY score DESC, id LIMIT 1', (code, normalize(word))).fetchone()
               or db.execute('SELECT id FROM terms WHERE dict=? AND nread=? ORDER BY score DESC, id LIMIT 1', (code, norm_reading(word))).fetchone())
    return term_entry(code, row['id']) if row else _missing(code, word)


def _missing(code, word):
    body = (f'<div class="yt-missing"><p>このページには「{html.escape(word or "")}」の項目がありません。</p>'
            f'<p>{_lookup_link(code, word or "", "すべての辞書で「" + html.escape(word or "") + "」を検索 · Search all dictionaries")}</p></div>')
    return _page(code, word or '', 'Yomitan', body)


# ----------------------------------------------------------------------------- kanji card
_GRADE = {'1': '小1', '2': '小2', '3': '小3', '4': '小4', '5': '小5', '6': '小6', '8': '常用', '9': '人名用', '10': '人名用'}


def _kana_readings(text, cls):
    items = [t for t in re.split(r'\s+', text or '') if t]
    if not items:
        return ''
    out = []
    for t in items:
        if '.' in t:
            stem, okuri = t.split('.', 1)
            t_html = f'{html.escape(stem)}<span class="yt-okuri">{html.escape(okuri)}</span>'
        else:
            t_html = html.escape(t)
        out.append(f'<span class="yt-rd {cls}">{t_html}</span>')
    return ''.join(out)


def _char_links(text):
    return ''.join(_lookup_link(KANJI_CODE, c, html.escape(c)) if _KANJI.match(c) or '\u2e80' <= c <= '\u2fdf' else html.escape(c)
                   for c in text if not c.isspace())


def _wiki_lines(lines, code, link_chars=False):
    """Kanji dumps: '＝＝見出し＝＝' / 'ーー小見出しーー' lines, 'key：value' rows, text and a source URL."""
    out = []
    for line in lines:
        if not isinstance(line, str):
            out.append(render_sc(line, code))
            continue
        s = line.strip()
        if not s or re.fullmatch(r'[ー－\-=＝]+', s):
            continue
        m = re.fullmatch(r'[＝=]{2,}\s*(.+?)\s*[＝=]{2,}', s)
        m2 = re.fullmatch(r'[ー－\-]{2,}\s*(.+?)\s*[ー－\-]{2,}', s)
        if m or m2:
            out.append(f'<h4 class="yt-wh{"" if m else " yt-wh2"}">{html.escape((m or m2)[1])}</h4>')
            continue
        if re.fullmatch(r'https?://\S+', s):
            out.append(f'<p class="yt-wsrc"><a class="yt-external"{_attr("href", s)}{_attr("data-external", s)}>{html.escape(re.sub(r"^https?://", "", s)[:70])}</a></p>')
            continue
        kv = re.fullmatch(r'([^：:]{1,10}?)\s*[：:]\s*(.+)', s)
        if kv and not re.match(r'https?|[（(]', s):
            value = kv[2]
            v_html = _char_links(value) if link_chars and all(_KANJI.match(c) or c.isspace() or '\u2e80' <= c <= '\u2fdf' or c in '、・' for c in value) else html.escape(value)
            out.append(f'<div class="yt-kv"><span class="yt-k">{html.escape(kv[1])}</span><span class="yt-v">{v_html}</span></div>')
            continue
        if link_chars and (len(s.replace(' ', '')) <= 3 or ' ' in s) and all(_KANJI.match(c) or c.isspace() or '\u2e80' <= c <= '\u2fdf' for c in s):
            out.append(f'<p class="yt-wl yt-chars">{_char_links(s)}</p>')
            continue
        out.append(f'<p class="yt-wl">{html.escape(s)}</p>')
    return ''.join(out)


def kanji_entry(codepoint):
    ch = chr(int(codepoint))
    with closing(connect()) as db:
        dicts = {d['code']: d for d in _dicts(db)}
        rows = db.execute('SELECT * FROM kanji WHERE character=? ORDER BY id', (ch,)).fetchall()
        metas = db.execute("SELECT * FROM kanji_meta WHERE character=? AND mode='freq'", (ch,)).fetchall()
        tag_maps = {code: _tag_map(db, code) for code in {r['dict'] for r in rows}}
    by = {}
    for r in rows:
        by.setdefault(dicts[r['dict']]['title'], []).append(r)
    def label(code):
        return KANJI_LABELS.get(dicts[code]['title'], dicts[code]['name'])

    onyomi, kunyomi, meanings, badges = '', '', [], []
    kd = (by.get('KANJIDIC (English)') or [None])[0]
    if kd:
        onyomi, kunyomi = kd['onyomi'], kd['kunyomi']
        meanings = json.loads(kd['meanings'])
        stats = json.loads(kd['stats'])
        if 'jouyou' in (kd['tags'] or '') or stats.get('grade') in ('1', '2', '3', '4', '5', '6', '8'):
            badges.append(('常用', 'accent'))
        if stats.get('grade') in _GRADE and _GRADE[stats['grade']] != '常用':
            badges.append((_GRADE[stats['grade']], ''))
        if stats.get('jlpt'):
            badges.append(('舊JLPT ' + stats['jlpt'] + '級', ''))
        if stats.get('strokes'):
            badges.append((stats['strokes'] + '画', ''))
        if stats.get('skip'):
            badges.append(('SKIP ' + stats['skip'], 'muted'))
    else:
        for r in rows:
            if r['onyomi'] or r['kunyomi']:
                onyomi, kunyomi = onyomi or r['onyomi'], kunyomi or r['kunyomi']
    for r in by.get('JPDB Kanji', []):
        s = json.loads(r['stats'])
        if s.get('漢字検定'):
            badges.append(('漢検 ' + re.sub(r'^Pre-', '準', s['漢字検定']) + '級', ''))
    for r in by.get('TheKanjiMap Kanji Radicals/Composition', []):
        s = json.loads(r['stats'])
        if s.get('画数') and not any(b[0].endswith('画') for b in badges):
            badges.append((s['画数'] + '画', ''))
    for r in by.get('Wiktionary漢字', []):
        st = json.loads(r['stats'])
        if st.get('部首'):
            badges.append(('部首 ' + re.sub(r'\s+', '', st['部首']), 'accent2'))
        if st.get('総画') and not any(b[0].endswith('画') and not b[0].startswith('部首') for b in badges):
            badges.append((st['総画'], ''))
    for r in by.get('jitai', []):
        if r['tags']:
            badges.append((r['tags'], 'accent2'))

    freqs = []
    for m in sorted(metas, key=lambda m: dicts[m['dict']]['position']):
        value, shown, _ = _freq_value(json.loads(m['data']))
        freqs.append({'name': label(m['dict']), 'display': '#' + shown if shown and shown[0].isdigit() else shown})
    if kd and json.loads(kd['stats']).get('freq'):
        freqs.append({'name': '新聞', 'display': f"#{int(json.loads(kd['stats'])['freq']):,}"})

    readings = ''
    if onyomi:
        readings += f'<div class="yt-rrow"><span class="yt-rlabel">音</span><span class="yt-rlist">{_kana_readings(onyomi, "yt-on")}</span></div>'
    if kunyomi:
        readings += f'<div class="yt-rrow"><span class="yt-rlabel">訓</span><span class="yt-rlist">{_kana_readings(kunyomi, "yt-kun")}</span></div>'
    badge_html = ''.join(f'<span class="yt-badge {"yt-badge-" + c if c else ""}">{html.escape(t)}</span>' for t, c in badges)
    meaning_html = f'<p class="yt-kmean" lang="en">{html.escape(", ".join(meanings))}</p>' if meanings else ''
    head = (f'<header class="yt-khead"><div class="yt-glyph" lang="ja">{html.escape(ch)}</div><div class="yt-kinfo">'
            f'{readings}{f"<div class=yt-badges>{badge_html}</div>" if badge_html else ""}{meaning_html}</div></header>')

    sections = []
    for r in by.get('JPDB Kanji', []):
        rd = []
        for t in (r['kunyomi'] or '').split():
            m = re.fullmatch(r'(.+?)\((\d+)%\)', t)
            if m:
                rd.append(f'<span class="yt-share"><span class="yt-share-bar" style="width:{min(100, int(m[2]))}%"></span><span class="yt-share-k">{html.escape(m[1])}</span><span class="yt-share-p">{m[2]}%</span></span>')
            else:
                rd.append(f'<span class="yt-rd yt-rare">{html.escape(t)}</span>')
        words, parts, target = [], [], 'words'
        for w in json.loads(r['meanings']):
            if not isinstance(w, str) or not w.strip():
                continue
            if w.strip().rstrip(':：') == '漢字分解':
                target = 'parts'
                continue
            (words if target == 'words' else parts).append(w.strip())
        chips = ''.join(_lookup_link(r['dict'], w, html.escape(w)) for w in dict.fromkeys(words))
        body = (f'<div class="yt-shares">{"".join(rd)}</div>' if rd else '') + (f'<div class="yt-words"><span class="yt-sublabel">よく使う語</span>{chips}</div>' if chips else '')
        if parts:
            body += f'<div class="yt-kv yt-parts"><span class="yt-k">漢字分解</span><span class="yt-v">{_char_links(" ".join(parts))}</span></div>'
        sections.append(('JPDB · 読みの割合', body, True))
    for title in ('jitai', 'mozc Kanji Variants'):
        for r in by.get(title, []):
            lines = [l for l in json.loads(r['meanings']) if isinstance(l, str) and l.strip()]
            body = ''.join(f'<p class="yt-wl">{html.escape(l)}</p>' for l in lines)
            sections.append((label(r['dict']), body, True))
    for r in by.get('TheKanjiMap Kanji Radicals/Composition', []):
        sections.append((label(r['dict']), _wiki_lines(json.loads(r['meanings']), r['dict'], link_chars=True), True))
    for title, open_ in (('Wiktionary漢字', True), ('ZH Wiktionary Hanzi', False)):
        for r in by.get(title, []):
            sections.append((label(r['dict']), _wiki_lines(json.loads(r['meanings']), r['dict'], link_chars=True), open_))
    known = {'KANJIDIC (English)', 'JPDB Kanji', 'jitai', 'mozc Kanji Variants', 'TheKanjiMap Kanji Radicals/Composition', 'Wiktionary漢字', 'ZH Wiktionary Hanzi'}
    for title, rs in by.items():
        if title in known:
            continue
        for r in rs:
            pills = _tag_pills(r['tags'], tag_maps.get(r['dict'], {}))
            reads = _kana_readings(r['onyomi'], 'yt-on') + _kana_readings(r['kunyomi'], 'yt-kun')
            sections.append((label(r['dict']), (f'<div class="yt-tags">{pills}</div>' if pills else '') + (f'<div class="yt-rlist">{reads}</div>' if reads else '') + _wiki_lines(json.loads(r['meanings']), r['dict']), True))
    if kd:
        s = json.loads(kd['stats'])
        refs = [(k, s[k]) for k in ('heisig6', 'heisig', 'nelson_c', 'nelson_n', 'halpern_njecd', 'kodansha_compact', 'four_corner', 'ucs') if s.get(k)]
        if refs:
            names = {'heisig6': 'Heisig 6', 'heisig': 'Heisig', 'nelson_c': 'Nelson (classic)', 'nelson_n': 'New Nelson', 'halpern_njecd': 'Halpern', 'kodansha_compact': 'Kodansha', 'four_corner': '四角号碼', 'ucs': 'Unicode'}
            body = ''.join(f'<div class="yt-kv"><span class="yt-k">{names[k]}</span><span class="yt-v">{"U+" + v.upper() if k == "ucs" else html.escape(v)}</span></div>' for k, v in refs)
            sections.append(('KANJIDIC · 索引番号', body, False))
    sec_html = ''.join(f'<details class="yt-ksec"{" open" if o else ""}><summary>{html.escape(t)}</summary><div class="yt-ksec-body">{b}</div></details>' for t, b, o in sections if b)
    if not rows and not metas:
        return _missing(KANJI_CODE, ch)
    return _page(KANJI_CODE, ch, '漢字', f'<article class="yt-kanji">{head}{_freq_chips(freqs)}{sec_html}</article>')


def entry(code, entry_id):
    if code == KANJI_CODE:
        return kanji_entry(int(entry_id))
    return term_entry(code, entry_id)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Import Yomitan dictionaries into the reader.')
    parser.add_argument('zips', nargs='*', type=Path, help='Zip files (default: dictionaries/yomitan and yomitan-paths.txt)')
    args = parser.parse_args()
    paths = args.zips or sources()
    if not paths:
        print('No Yomitan zips found. Put them in', SOURCE_DIR, 'or list them in', PATHS_FILE)
        raise SystemExit(1)
    started = time.time()
    print(f'Importing {len(paths)} Yomitan dictionar{"y" if len(paths) == 1 else "ies"} into {INDEX} …', flush=True)
    build(paths, log=lambda m: print(m, flush=True))
    print(f'Done in {time.time() - started:.0f} s. Restart or reload the reader.')
