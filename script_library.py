"""Extracted game scripts (personal study corpora) for reading, search and OCR matching.

A script folder contains ``script.json`` ({"game": ..., "rows": [{source, id, kind,
speaker, ja, en, zh, ...}]}) and optionally ``annotations.json`` ({"items": {
"source|id": {...}}}). Folders are found in:

* ``scripts/<name>/`` inside the reader folder, and
* every path listed (one per line) in ``scripts/paths.txt`` or ``JP_READER_SCRIPTS``.

Scripts stay outside Git: they are personal extractions of commercial games.
"""
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
            data = json.loads(self.path.read_text(encoding='utf-8'))
            rows = data['rows'] if isinstance(data, dict) else data
            self.title = (data.get('game') if isinstance(data, dict) else None) or self.title
            self.id = slug(self.title)
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
        return [{'ja': r['ja'], 'id': r['key'], 'en': r['en'], 'zh': r['zh']}
                for r in self.rows if r['kind'] in ('dialogue', 'mail') and r['ja']]


class Library:
    def __init__(self):
        self.lock = threading.Lock()
        self.scripts = {}

    def refresh(self):
        with self.lock:
            known = {s.folder.resolve(): s for s in self.scripts.values()}
            scripts = {}
            for folder in folders():
                script = known.get(folder.resolve()) or Script(folder)
                try:
                    script.load()
                except (OSError, ValueError, KeyError) as error:
                    print('Script skipped:', folder, error)
                    continue
                scripts[script.id] = script
            self.scripts = scripts
            return list(scripts.values())

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
        for script in self.scripts.values():
            n = script.by_key.get(key)
            if n:
                return {'script': script.id, 'n': n}
        return None
