"""Extracted game scripts (personal study corpora) for reading, search and OCR matching.

A script folder contains ``script.json`` ({"game": ..., "rows": [{source, id, kind,
speaker, ja, en, zh, ...}]}) and optionally ``annotations.json`` ({"items": {
"source|id": {...}}}). Folders are found in:

* UI imports in ``scripts/<script_id>/`` beside the current library database,
* ``scripts/<name>/`` inside the reader folder, and
* every path listed (one per line) in ``scripts/paths.txt`` or ``JP_READER_SCRIPTS``.

Scripts stay outside Git: they are personal extractions of commercial games.
"""
import hashlib
import shutil
import tempfile
import json
import os
import re
import threading
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TAG = re.compile(r'<tips,\d+,([^<>]*)>|<[^<>]{0,40}>')
KINDS = ('dialogue', 'mail', 'tip', 'ui', 'extra')


def clean(text):
    """Visible study text: keep TIPS words, drop engine markup."""
    return TAG.sub(lambda m: m.group(1) or '', text or '')


def slug(text):
    text = unicodedata.normalize('NFKC', text).casefold()
    return re.sub(r'[^0-9a-z]+', '-', text).strip('-')[:48] or 'script'


MAX_IMPORT_BYTES = 64 * 1024 * 1024


def template():
    return {'script_id': 'sample-novel', 'game': 'Sample Visual Novel', 'rows': [
        {'source': 'chapter01', 'id': '001', 'kind': 'dialogue', 'speaker': '春',
         'ja': '今日はいい天気ですね。', 'en': 'The weather is lovely today.', 'zh': '今天天氣真好。'},
        {'source': 'chapter01', 'id': '002', 'kind': 'dialogue', 'speaker': '',
         'ja': '窓を開けると、涼しい風が入ってきた。'}]}


def validate_import(data):
    """Validate the entire upload before creating files; keep legacy disk loads compatible."""
    if not isinstance(data, dict) or not isinstance(data.get('game'), str) or not data['game'].strip():
        raise ValueError('A script needs a non-empty game title and a rows array.')
    title = data['game'].strip()
    if len(title) > 200:
        raise ValueError('The game title must be 200 characters or fewer.')
    identity = data.get('script_id', '')
    if not isinstance(identity, str) or (identity and not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,63}', identity)):
        raise ValueError('script_id must use 1–64 lowercase letters, digits, hyphens or underscores.')
    if identity in ('auto', 'off', 'con', 'prn', 'aux', 'nul') or re.fullmatch(r'(com|lpt)[1-9]', identity):
        raise ValueError('This script_id is reserved. Choose a different identifier, such as my-novel.')
    identity = identity or slug(title) + '-' + hashlib.sha256(title.encode('utf-8')).hexdigest()[:8]
    rows = data.get('rows')
    if not isinstance(rows, list) or not rows or len(rows) > 200000:
        raise ValueError('rows must contain between 1 and 200,000 lines.')
    result, seen = [], set()
    for n, row in enumerate(rows, 1):
        if not isinstance(row, dict):
            raise ValueError(f'Line {n}: expected an object.')
        out = {}
        for name in ('source', 'id', 'kind', 'speaker', 'ja', 'en', 'zh'):
            value = row.get(name, '')
            if name == 'id' and isinstance(value, int) and not isinstance(value, bool):
                value = str(value)
            if not isinstance(value, str):
                raise ValueError(f'Line {n}: {name} must be text, not null, a list or an object.')
            if len(value) > 100000:
                raise ValueError(f'Line {n}: {name} exceeds 100,000 characters.')
            out[name] = value
        out['source'] = out['source'] or 'main'
        out['id'] = out['id'] or str(n)
        out['kind'] = out['kind'] or 'dialogue'
        if '|' in out['source'] or '|' in out['id']:
            raise ValueError(f'Line {n}: source and id cannot contain |.')
        if out['kind'] not in KINDS:
            raise ValueError(f'Line {n}: kind must be dialogue, mail, tip, ui or extra.')
        if not any(clean(out[k]).strip() for k in ('ja', 'en', 'zh')):
            raise ValueError(f'Line {n}: provide text in ja, en or zh.')
        key = (out['source'], out['id'])
        if key in seen:
            raise ValueError(f'Line {n}: duplicate source/id pair: {key[0]} | {key[1]}.')
        seen.add(key)
        result.append(out)
    return {'script_id': identity, 'game': title, 'rows': result}



def folders():
    found = []
    base = ROOT / 'scripts'
    lists = [base / 'paths.txt']
    extra = [p for p in os.environ.get('JP_READER_SCRIPTS', '').split(os.pathsep) if p.strip()]
    if base.is_dir():
        found += [p for p in sorted(base.iterdir()) if (p / 'script.json').is_file()]
    for listing in lists:
        try:
            extra += [line.strip().strip('"') for line in listing.read_text(encoding='utf-8-sig').splitlines()
                      if line.strip() and not line.lstrip().startswith('#')]
        except OSError:
            pass
    for raw in extra:
        path = Path(os.path.expandvars(os.path.expanduser(raw)))
        if not path.is_absolute():
            path = base / path
        if (path / 'script.json').is_file():
            found.append(path)
        elif (path / 'corpus' / 'script.json').is_file():
            found.append(path / 'corpus')
    unique = []
    for path in found:
        if path.resolve() not in [p.resolve() for p in unique]:
            unique.append(path)
    return unique


class Script:
    def __init__(self, folder):
        self.folder = Path(folder)
        self.path = self.folder / 'script.json'
        self.lock = threading.Lock()
        self.rows = None
        self.title = self.folder.name
        self.id = slug(self.folder.parent.name if self.folder.name == 'corpus' else self.folder.name)
        self._notes = ({}, None)
        self._cache = (None, [])

    def load(self):
        with self.lock:
            if self.rows is not None:
                return self
            data = json.loads(self.path.read_text(encoding='utf-8-sig'))
            rows = data['rows'] if isinstance(data, dict) else data
            self.title = (data.get('game') if isinstance(data, dict) else None) or self.title
            self.id = (data.get('script_id') if isinstance(data, dict) else None) or slug(self.title)
            if self.id == 'script':
                self.id += '-' + hashlib.sha256(self.title.encode('utf-8')).hexdigest()[:8]
            prepared = []
            for n, r in enumerate(rows, 1):
                ja, en, zh = clean(r.get('ja', '')), clean(r.get('en', '')), clean(r.get('zh', ''))
                prepared.append({
                    'n': n, 'key': f"{r.get('source', '')}|{r.get('id', '')}",
                    'source': r.get('source', ''), 'id': r.get('id', ''), 'kind': r.get('kind', ''),
                    'speaker': r.get('speaker', ''), 'ja': ja, 'en': en, 'zh': zh,
                    'tips': re.findall(r'<tips,\d+,([^<>]*)>', r.get('ja', '')),
                    '_find': unicodedata.normalize('NFKC', ja + '\n' + en + '\n' + zh + '\n' + r.get('speaker', '')).casefold(),
                })
            self.rows = prepared
            self.by_key = {r['key']: r['n'] for r in prepared}
            return self

    def notes(self):
        """Annotations are re-read when their file changes (e.g. after a new study batch)."""
        path = self.folder / 'annotations.json'
        try:
            stamp = path.stat().st_mtime
        except OSError:
            return {}
        if self._notes[1] != stamp:
            try:
                items = json.loads(path.read_text(encoding='utf-8')).get('items', {})
            except (OSError, ValueError, AttributeError):
                items = {}
            self._notes = (items if isinstance(items, dict) else {}, stamp)
        return self._notes[0]

    def info(self):
        self.load()
        kinds = {}
        for r in self.rows:
            kinds[r['kind']] = kinds.get(r['kind'], 0) + 1
        return {'id': self.id, 'title': self.title, 'rows': len(self.rows), 'kinds': kinds,
                'annotated': len(self.notes())}

    def public(self, r, notes):
        row = {k: v for k, v in r.items() if not k.startswith('_')}
        row['annotated'] = r['key'] in notes
        row['source_id'] = self.id + '::' + r['key']
        return row

    def search(self, q='', kinds=None, need='', path='', offset=0, limit=100, annotated=False):
        self.load()
        notes = self.notes()
        q = unicodedata.normalize('NFKC', q or '').strip()
        path = (path or '').strip().casefold()
        kinds = set(kinds or KINDS)
        signature = (q, tuple(sorted(kinds)), need, path, annotated, self._notes[1])
        if self._cache[0] == signature:
            hits = self._cache[1]
        else:
            terms = [t.casefold() for t in q.split()] if q else []
            hits = []
            for r in self.rows:
                if r['kind'] not in kinds and r['kind'] in KINDS:
                    continue
                if need == 'all' and not (r['ja'] and r['en'] and r['zh']):
                    continue
                if need == 'ja-en' and not (r['ja'] and r['en']):
                    continue
                if path and path not in (r['source'] + '|' + r['id']).casefold():
                    continue
                if annotated and r['key'] not in notes:
                    continue
                if terms and not all(t in r['_find'] for t in terms):
                    continue
                hits.append(r['n'])
            self._cache = (signature, hits)
        offset = max(0, int(offset))
        limit = max(1, min(300, int(limit)))
        return {'total': len(hits), 'offset': offset,
                'rows': [self.public(self.rows[n - 1], notes) for n in hits[offset:offset + limit]]}

    def position(self, n, **filters):
        """Offset of script line #n inside a filtered result (for jumping)."""
        self.search(limit=1, **filters)
        hits = self._cache[1]
        lo, hi = 0, len(hits)
        while lo < hi:
            mid = (lo + hi) // 2
            if hits[mid] < n:
                lo = mid + 1
            else:
                hi = mid
        return lo

    def row(self, n):
        self.load()
        if not 1 <= n <= len(self.rows):
            raise ValueError('No such script line.')
        notes = self.notes()
        r = self.rows[n - 1]
        return {**self.public(r, notes), 'note': notes.get(r['key'])}

    def matcher_rows(self):
        self.load()
        return [{'ja': r['ja'], 'id': self.id + '::' + r['key'], 'en': r['en'], 'zh': r['zh']}
                for r in self.rows if r['kind'] in ('dialogue', 'mail') and r['ja']]


class Library:
    def __init__(self, import_dir=None):
        self.import_dir = Path(import_dir) if import_dir is not None else ROOT / 'data' / 'reading' / 'scripts'
        self.lock = threading.Lock()
        self.scripts = {}

    def refresh(self):
        with self.lock:
            known = {s.folder.resolve(): s for s in self.scripts.values()}
            scripts = {}
            imported = [p for p in sorted(self.import_dir.iterdir()) if (p / 'script.json').is_file() and not p.name.startswith('.import-')] if self.import_dir.is_dir() else []
            for folder in dict.fromkeys(folders() + imported):
                script = known.get(folder.resolve()) or Script(folder)
                try:
                    script.load()
                except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
                    print('Script skipped:', folder, error)
                    continue
                if script.id in scripts and scripts[script.id].folder.resolve() != script.folder.resolve():
                    script.id += '-' + hashlib.sha256(str(script.folder.resolve()).encode('utf-8')).hexdigest()[:8]
                scripts[script.id] = script
            self.scripts = scripts
            return list(scripts.values())

    def import_script(self, data):
        data = validate_import(data)
        self.refresh()
        with self.lock:
            destination = self.import_dir / data['script_id']
            if data['script_id'] in self.scripts or destination.exists():
                raise ValueError('This script_id is already loaded. Use a different script_id for another version; existing scripts were not changed.')
            self.import_dir.mkdir(parents=True, exist_ok=True)
            staging = Path(tempfile.mkdtemp(prefix='.import-', dir=self.import_dir))
            try:
                (staging / 'script.json').write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
                script = Script(staging).load()
                staging.rename(destination)
                script.folder = destination
                script.path = destination / 'script.json'
                self.scripts[script.id] = script
                return script.info()
            finally:
                if staging.exists() and staging.parent.resolve() == self.import_dir.resolve() and staging.name.startswith('.import-'):
                    shutil.rmtree(staging)

    def get(self, script_id):
        if script_id not in self.scripts:
            self.refresh()
        if script_id not in self.scripts:
            raise ValueError('Script not found. Check scripts/paths.txt.')
        return self.scripts[script_id]

    def for_window(self, title):
        wanted = slug(title or '')
        for script in self.scripts.values():
            if script.id and (script.id in wanted or wanted and wanted in script.id):
                return script
        return None

    def locate(self, key):
        if '::' in key:
            identity, row_key = key.split('::', 1)
            script = self.scripts.get(identity)
            n = script.by_key.get(row_key) if script else None
            return {'script': identity, 'n': n} if n else None
        for script in self.scripts.values():
            n = script.by_key.get(key)
            if n:
                return {'script': script.id, 'n': n}
        return None
