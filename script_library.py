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
import struct
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

# ------------------------------------------------------------------ voice
# A row may name its voice clip ("voice": "VO04_0018"). script.json says where the clips live
# ("voice": {"archives": ["voice.pac"]}, relative to the game folder), and voice.json beside it
# says where this computer keeps the game ({"game_dir": "C:\\...\\game"}). The installer writes
# voice.json; the game link also fills it in the first time it follows the running game.
# Archives are read in place (Pal engine .pac, or a plain folder of audio files); nothing is copied.
VOICE_NAME = re.compile(r'[A-Za-z0-9_\-]{1,64}')
VOICE_SPEC = re.compile(r'[A-Za-z0-9_\-]{1,64}(?:\+[A-Za-z0-9_\-]{1,64}){0,7}')   # "A+B": clips heard together
AUDIO_TYPES = {'.ogg': 'audio/ogg', '.opus': 'audio/ogg', '.wav': 'audio/wav', '.mp3': 'audio/mpeg',
               '.m4a': 'audio/mp4', '.flac': 'audio/flac'}
MAX_CLIP_BYTES = 64 * 1024 * 1024


def voice_config(value):
    """The script-wide voice settings, cleaned: {'archives': [...], 'ext': [...]} or {}."""
    if not isinstance(value, dict):
        return {}
    archives = [a for a in value.get('archives', []) if isinstance(a, str) and 0 < len(a) <= 260][:8] \
        if isinstance(value.get('archives'), list) else []
    exts = [e for e in value.get('ext', []) if isinstance(e, str) and e.lower() in AUDIO_TYPES][:6] \
        if isinstance(value.get('ext'), list) else []
    return {'archives': archives, 'ext': exts} if archives else {}


class PalPac:
    """Read-only index of a Pal engine .pac archive (name -> offset, size); clips are read on demand.

    "PAC " | 0 | count | 255 x (start, count) name buckets | count x (name[32], size, offset) | data."""

    def __init__(self, path):
        self.path = Path(path)
        st = self.path.stat()
        self.stamp = (st.st_size, st.st_mtime_ns)
        with open(self.path, 'rb') as f:
            head = f.read(0x804)
            if len(head) < 0x804 or head[:4] != b'PAC ':
                raise ValueError('不是 PAC 封包：' + str(self.path))
            count = struct.unpack_from('<I', head, 8)[0]
            if count > 1000000:
                raise ValueError('PAC 封包的目錄不正確：' + str(self.path))
            index = f.read(40 * count)
        if len(index) < 40 * count:
            raise ValueError('PAC 封包的目錄不完整：' + str(self.path))
        self.files = {}
        for i in range(count):
            name = index[i * 40:i * 40 + 32].split(b'\0')[0].decode('cp932', 'replace').upper()
            self.files[name] = struct.unpack_from('<II', index, i * 40 + 32)[::-1]   # (offset, size)

    def read(self, name):
        offset, size = self.files[name.upper()]
        if size > MAX_CLIP_BYTES:
            raise ValueError('語音檔太大：' + name)
        with open(self.path, 'rb') as f:
            f.seek(offset)
            data = f.read(size)
        if len(data) != size:
            raise ValueError('語音檔讀不完整（遊戲檔案可能損壞）：' + name)
        return data


_archives = {}
_archives_lock = threading.Lock()


def _pac(path):
    st = path.stat()
    with _archives_lock:
        pac = _archives.get(path)
        if pac is None or pac.stamp != (st.st_size, st.st_mtime_ns):
            pac = _archives[path] = PalPac(path)
        return pac


def sniff(data):
    """MIME type from the first bytes of an audio clip stored without a file extension."""
    return 'audio/ogg' if data[:4] == b'OggS' else 'audio/wav' if data[:4] == b'RIFF' else \
        'audio/mpeg' if data[:3] == b'ID3' or data[:2] in (b'\xff\xfb', b'\xff\xf3') else 'application/octet-stream'


def voice_clip(sources, name, exts=None):
    """(audio bytes, MIME type) of one voice clip, looked up in the archives in order."""
    if not isinstance(name, str) or not VOICE_NAME.fullmatch(name):
        raise ValueError('語音檔名不正確。')
    exts = list(exts or ['.ogg', '.wav'])
    if not sources:
        raise ValueError('還不知道這台電腦的遊戲裝在哪裡，所以找不到語音。'
                         '開著遊戲、用一次「遊戲連動」就會記住（或重新執行這款遊戲的 install.cmd）。')
    missing, lacking, failed = [], [], []
    for source in sources:
        try:
            if source.is_dir():
                for ext in exts + [e.upper() for e in exts]:
                    clip = source / (name + ext)
                    if clip.is_file():
                        if clip.stat().st_size > MAX_CLIP_BYTES:
                            raise ValueError('語音檔太大：' + name)
                        return clip.read_bytes(), AUDIO_TYPES[ext.lower()]
            elif source.is_file():
                pac = _pac(source)
                for ext in exts:
                    if (name + ext).upper() in pac.files:
                        return pac.read(name + ext), AUDIO_TYPES[ext.lower()]
                if name.upper() in pac.files:                 # stored without an extension
                    data = pac.read(name)
                    return data, sniff(data)
            else:
                missing.append(str(source))
                continue
            lacking.append(str(source))
        except OSError as error:
            failed.append(f'{source}（{error.strerror or error}）')
        except ValueError as error:
            failed.append(str(error))
    if lacking:
        raise ValueError(f'遊戲的語音檔裡沒有 {name}。')
    if failed:
        raise ValueError('讀不到語音檔：' + '、'.join(failed) + '。遊戲正在更新或檔案被鎖住的話，等一下再試。')
    raise ValueError('找不到語音檔：' + '、'.join(missing) + '。遊戲搬家或重灌的話，開著遊戲用一次「遊戲連動」就會更新位置。')



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
        voice = row.get('voice', '')
        if voice:
            if not isinstance(voice, str) or not VOICE_SPEC.fullmatch(voice):
                raise ValueError(f'Line {n}: voice must be a clip name such as VO04_0018 (letters, digits, _ or -; A+B for clips heard together).')
            out['voice'] = voice
        result.append(out)
    script = {'script_id': identity, 'game': title, 'rows': result}
    if voice_config(data.get('voice')):
        script['voice'] = voice_config(data.get('voice'))
    return script



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
        self.voice_cfg = {}

    def load(self):
        with self.lock:
            if self.rows is not None:
                return self
            data = json.loads(self.path.read_text(encoding='utf-8-sig'))
            rows = data['rows'] if isinstance(data, dict) else data
            self.voice_cfg = voice_config(data.get('voice')) if isinstance(data, dict) else {}
            self.title = (data.get('game') if isinstance(data, dict) else None) or self.title
            self.id = (data.get('script_id') if isinstance(data, dict) else None) or slug(self.title)
            if self.id == 'script':
                self.id += '-' + hashlib.sha256(self.title.encode('utf-8')).hexdigest()[:8]
            prepared = []
            for n, r in enumerate(rows, 1):
                ja, en, zh = clean(r.get('ja', '')), clean(r.get('en', '')), clean(r.get('zh', ''))
                voice = r.get('voice')
                prepared.append({
                    'n': n, 'key': f"{r.get('source', '')}|{r.get('id', '')}",
                    'source': r.get('source', ''), 'id': r.get('id', ''), 'kind': r.get('kind', ''),
                    'speaker': r.get('speaker', ''), 'ja': ja, 'en': en, 'zh': zh,
                    'tips': re.findall(r'<tips,\d+,([^<>]*)>', r.get('ja', '')),
                    '_find': unicodedata.normalize('NFKC', ja + '\n' + en + '\n' + zh + '\n' + r.get('speaker', '')).casefold(),
                })
                if isinstance(voice, str) and VOICE_SPEC.fullmatch(voice) and self.voice_cfg:
                    prepared[-1]['voice'] = voice
            self.rows = prepared
            self.by_key = {r['key']: r['n'] for r in prepared}
            return self

    def located(self, n):
        """Where a line is ({'script', 'n'}), plus 'voice': how many clips it has (clips heard together)."""
        voice = self.rows[n - 1].get('voice')
        return {'script': self.id, 'n': n, **({'voice': voice.count('+') + 1} if voice else {})}

    def voice_sources(self):
        """Where this computer keeps the voice archives: script.json "voice" + voice.json in this folder."""
        try:
            local = json.loads((self.folder / 'voice.json').read_text(encoding='utf-8-sig'))
        except (OSError, ValueError):
            local = {}
        if not isinstance(local, dict):
            local = {}
        game = local.get('game_dir') if isinstance(local.get('game_dir'), str) else ''
        found = []
        for item in [a for a in local.get('archives', []) if isinstance(a, str)] if isinstance(local.get('archives'), list) else []:
            found.append(Path(item))
        for item in self.voice_cfg.get('archives', []):
            path = Path(item)
            if not path.is_absolute():
                if not game:
                    continue
                path = Path(game) / path
            found.append(path)
        return list(dict.fromkeys(found))

    def voice(self, n, part=0):
        """(audio bytes, MIME type) of script line #n's voice clip (part: which of the clips heard together)."""
        self.load()
        if not 1 <= n <= len(self.rows):
            raise ValueError('No such script line.')
        name = self.rows[n - 1].get('voice')
        if not name:
            raise ValueError('這句沒有語音。')
        names = name.split('+')
        if not 0 <= part < len(names):
            raise ValueError('No such voice clip.')
        return voice_clip(self.voice_sources(), names[part], self.voice_cfg.get('ext'))

    def needs_game_dir(self):
        """True when this script has voices but none of its archives can be found on this computer."""
        self.load()
        return bool(self.voice_cfg) and not any(p.exists() for p in self.voice_sources())

    def remember_game_dir(self, folder):
        """Save where the game is (from the running game's .exe) if its voice archives are there."""
        folder = Path(folder)
        relative = [a for a in self.voice_cfg.get('archives', []) if not Path(a).is_absolute()]
        if not relative or not any((folder / a).exists() for a in relative):
            return False
        target = self.folder / 'voice.json'
        tmp = target.with_name('voice.json.tmp')
        tmp.write_text(json.dumps({'game_dir': str(folder)}, ensure_ascii=False, indent=1), encoding='utf-8')
        os.replace(tmp, target)
        return True

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
                'annotated': len(self.notes()), 'voice': bool(self.voice_cfg)}

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
        # Japanese window titles have no ASCII to compare: match the script's game title instead.
        def plain(text):
            return re.sub(r'\s+', '', unicodedata.normalize('NFKC', text or '').casefold())
        wanted = plain(title)
        for script in self.scripts.values():
            name = plain(script.title)
            if wanted and len(name) >= 2 and (name in wanted or wanted in name):
                return script
        return None

    def locate(self, key):
        if '::' in key:
            identity, row_key = key.split('::', 1)
            script = self.scripts.get(identity)
            n = script.by_key.get(row_key) if script else None
            return script.located(n) if n else None
        for script in self.scripts.values():
            n = script.by_key.get(key)
            if n:
                return script.located(n)
        return None
