"""Export dictionary corpus for JLPT語彙 lessons (runs inside jp-game-reader).

Usage (from this folder, or via "Export vocab sources.cmd"):
  python vocab_sources.py 0001            batch 0001 from master\\批次.tsv
  python vocab_sources.py 0001-0003       batches 0001..0003 (one output per batch)
  python vocab_sources.py 00101 00120     大全編號 range
  python vocab_sources.py 気持ち 心持ち     specific words (語 or 讀音 in master\\語彙大全.tsv)

Output (in the vocab root, default C:\\Users\\sagen\\Desktop\\New folder\\JLPT語彙;
override with vocab_root.txt next to this script or --vocab):
  sources\\批次0001.jsonl          one JSON object per word (all dictionary texts, NHK accent, frequency)
  sources\\批次0001\\00123_語.md     the same, readable per word (what the lesson writer reads)

Everything stays on this computer; sources\\ is personal study material (not for Git).
"""
import argparse, html, json, re, sqlite3, sys, unicodedata
from contextlib import closing
from html.parser import HTMLParser
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import mdict_library          # noqa: E402
import yomitan_library        # noqa: E402

DEFAULT_VOCAB = Path(r'C:\Users\sagen\Desktop\New folder\JLPT語彙')
PER_DICT = 6000        # characters per dictionary (per collection section)
PER_WORD = 45000       # overall budget per word; lower-priority dictionaries are dropped first
PER_RECORD = 4         # entries per dictionary
SKIP_CODES = {'MDX_ALL'}   # dictionaries never exported

# Priority: monolingual → synonym/usage → accent → bilingual with examples → the rest. Skipped: irrelevant directions.
PRIORITY = ['明鏡', '明镜', '三国', '三省堂国語', '大辞泉', '大辞林', '大辭林', '岩波', '広辞苑', '新明解', '類語', '使い分け', '故事ことわざ',
            'NHK', '研究社', '新和英', 'プログレッシブ和英', 'ウィズダム', 'SANWIZ', 'ジーニアス', 'GENIUS', 'オーレックス', 'OLEX', '日米口語',
            '小学館', 'Shogakukan', 'JCD', 'CROWN', 'クラウン', '日汉', '日華', 'デイリー', 'Daily', '斎藤', 'saito', 'JMdict', 'Pixiv',
            'ピクシブ', 'surasura', 'オノマトペ', '複合語']
SKIP = ['英和', 'en-ja', 'English-Jp', 'Longman English', 'Collins', '華日', '华日', '和西', '書き順', '字源', '漢字源', 'JMneDict',
        'JReadability', 'Forvo', '活用', '非辞書形', 'Readability', '文型辞典', 'Grammar', '文法', '言語モジュール', 'ワープロ', 'Tuttle']

KANJI = re.compile(r'[㐀-䶿一-鿿豈-﫿々〆ヶ\U00020000-\U0003FFFF]')
def norm(s): return unicodedata.normalize('NFKC', s or '').strip().casefold()
def hira(s): return ''.join(chr(ord(c) - 0x60) if 'ァ' <= c <= 'ヶ' else c for c in s)

# ------------------------------------------------------------------------------- html -> text
class Text(HTMLParser):
    BLOCK = {'p', 'div', 'br', 'li', 'tr', 'h1', 'h2', 'h3', 'h4', 'dt', 'dd', 'section', 'article', 'blockquote', 'table', 'ul', 'ol',
             'head-g', 'ddudc', 'hr', 'mg', 'meaning', 'subitem', 'subitemh', 'maccentaudiog'}
    SKIP = {'head', 'style', 'script', 'title', 'rt', 'rp', 'sound'}
    def __init__(self):
        super().__init__(convert_charrefs=True); self.out = []; self.skip = 0
    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP: self.skip += 1
        elif tag in self.BLOCK: self.out.append('\n')
        if tag == 'li': self.out.append('・')
    def handle_endtag(self, tag):
        if tag in self.SKIP: self.skip = max(0, self.skip - 1)
        elif tag in self.BLOCK: self.out.append('\n')
    def handle_startendtag(self, tag, attrs):
        if tag in ('br', 'hr'): self.out.append('\n')
    def handle_data(self, data):
        if not self.skip: self.out.append(data)

def plain(markup):
    markup = re.sub(r'(?is)<a\b[^>]*href="sound://[^"]*"[^>]*>.*?</a>', '', markup)
    markup = re.sub(r'(?is)<wari>(.*?)</wari>', r'（\1）', markup)                        # 大辞泉 inline readings
    markup = re.sub(r'(?is)<sub class="rubi">(.*?)</sub>', r'（\1）', markup)             # 広辞苑 inline readings
    markup = re.sub(r'(?is)<header\b[^>]*>.*?</header>|<div class="title">.*?</div>', '', markup)   # repeated title bars
    p = Text(); p.feed(markup); p.close()
    lines = [re.sub(r'[ \t\u3000]+', ' ', l).strip() for l in ''.join(p.out).split('\n')]
    text = '\n'.join(l for l in lines if l)
    return re.sub(r'\n{3,}', '\n\n', text)

def clip(text, limit):
    return text if len(text) <= limit else text[:limit].rsplit('\n', 1)[0] + '\n…（以下略）'

# ------------------------------------------------------------------------------- NHK accent
SMALL = set('ゃゅょぁぃぅぇぉゎャュョァィゥェォヮ')
def morae(kana): return sum(1 for c in kana if c not in SMALL)
def accent_info(markup):
    """[(kana pattern, number, type)] from NHK accent_text markup: ━ = 平板, ＼ = drop after the preceding mora."""
    out = []
    for m in re.finditer(r'<accent_text>(.*?)</accent_text>', markup, re.S):
        raw = re.sub(r'<sound>.*?</sound>', '', m[1], flags=re.S)
        raw = re.sub(r'<round_box>(.*?)</round_box>', r'\1', raw)      # devoiced vowel: keep the kana
        raw = re.sub(r'<symbol_macron>.*?</symbol_macron>', '━', raw)
        raw = re.sub(r'<symbol_backslash>.*?</symbol_backslash>', '＼', raw)
        raw = re.sub(r'<[^>]+>', '', raw).strip()
        kana = raw.replace('━', '').replace('＼', '')
        n = morae(kana)
        if '＼' in raw:
            num = morae(raw.split('＼', 1)[0])
            kind = '頭高' if num == 1 else ('尾高' if num == n else '中高')
        else:
            num, kind = 0, '平板'
        out.append({'pattern': raw, 'accent': num, 'type': kind, 'morae': n})
    return out

def nhk_entries(forms, reading, others=()):
    code = next((d['code'] for d in mdict_library.dictionaries() if 'NHK' in d['name'] or d['code'] == 'MDX_NHK'), None)
    if not code: return []
    found = []
    for key in dict.fromkeys(forms + [reading]):
        for e in _records(code, key):
            title, text = mdict_library.record(code, e)
            for g in re.finditer(r'<head-g\b[^>]*>(.*?)</head-g>', text, re.S):
                block = g[1]
                hw = plain(re.search(r'<h>(.*?)</h>', block, re.S)[1]) if re.search(r'<h>(.*?)</h>', block, re.S) else ''
                spelling = re.search(r'[【《]([^】》]+)[】》]', hw)
                sp = spelling[1].replace('×', '').replace('△', '') if spelling else ''
                head = re.sub(r'[【《（(].*', '', hw).strip()
                if hira(head) != hira(reading):
                    continue
                if sp and any(_odoriji(o).rstrip('ぁ-ん') and re.sub('[ぁ-ん]+$', '', _odoriji(o)) in _odoriji(sp) for o in others) \
                        and not any(re.sub('[ぁ-ん]+$', '', _odoriji(f)) in _odoriji(sp) for f in forms if KANJI.search(f)):
                    continue                          # homophone (暮れる for くれる)
                if forms and sp and not any(f in sp or sp in f for f in forms if KANJI.search(f)) and any(KANJI.search(f) for f in forms):
                    continue
                item = {'headword': hw, 'accents': accent_info(block.split('<con_table>')[0])}
                if item['accents'] and item not in found:
                    found.append(item)
    return found

# ------------------------------------------------------------------------------- MDX
def _records(code, key):
    with closing(mdict_library.connect()) as db:
        f = db.execute("SELECT id FROM files WHERE code=? AND kind='.mdx'", (code,)).fetchone()
        if not f: return []
        return [r[0] for r in db.execute('SELECT id FROM records WHERE file=? AND norm=? LIMIT 12', (f[0], mdict_library.normalize(key)))]

def _sections(code, text):
    """(title, html) parts; the all-in-one collection is split into its member dictionaries."""
    if '<ddudc' not in text:
        return [(None, text)]
    titles = dict(re.findall(r'<ddudt\b[^>]*id="([^"]+)"[^>]*>(.*?)</ddudt>', text, re.S | re.I))
    parts = []
    for m in re.finditer(r'<ddudc\b([^>]*)>(.*?)</ddudc>', text, re.S | re.I):
        key = re.search(r'id="([^"]+)"', m[1])
        title = titles.get(key[1].removesuffix('_c') if key else '', '')
        parts.append((plain(title) or None, m[2]))
    return parts or [(None, text)]

def _odoriji(s):
    """態々 -> 態態; drop dictionary marks (▽△×〈〉‐・)."""
    out = ''
    for c in re.sub(r'[▽△×〈〉‐・\-]', '', s):
        out += out[-1] if c == '々' and out else c
    return out

def relevant(txt, forms, reading, via_kanji, others=()):
    """A record found by a kana key must be this word, not a homophone (こと ≠ 琴, くれる ≠ 暮れる)."""
    if via_kanji: return True
    head = txt[:300]
    brackets = [_odoriji(m[1]) for m in re.finditer(r'[【［〔]([^】］〕]{1,30})[】］〕]', head[:120])]
    kanji_forms = [_odoriji(f) for f in forms if KANJI.search(f)]
    stems = [re.sub('[ぁ-ん]+$', '', f) for f in kanji_forms]
    if any(f in _odoriji(head) for f in kanji_forms): return True
    if any(st and st in b for st in stems for b in brackets): return True       # 送り仮名の揺れ（気持ち／気持）
    other = [re.sub('[ぁ-ん]+$', '', _odoriji(o)) for o in others]
    if any(o and o in b for o in other for b in brackets): return False           # another word with this reading
    if any(o and o in head[:12] for o in other) and not any(st and st in head[:12] for st in stems): return False
    if not kanji_forms: return True                                             # kana word: the reading is the word
    return not brackets                                                         # no spelling shown: keep


def is_jump_list(txt):
    """Only ☞ references, no definition text (e.g. '大辞泉☞くれる【呉れる】大辞泉☞くれる【暮れる】')."""
    if '☞' not in txt: return False
    rest = re.sub(r'☞[^☞\n]*', '', txt)
    return len(re.sub(r'[\s*◀★▶]|[A-Za-z0-9]+', '', rest)) < 40 and len(txt) < 600

def jump_targets(txt):
    """'☞くれる【呉れる】' / '☞態々（わざわざ）' / '☞態態' -> (label, spelling set)."""
    out = []
    parts = txt.split('☞')
    name = re.split(r'[\n*]', parts[0])[-1].strip()          # member dictionary name repeated before each ☞
    for chunk in parts[1:]:
        chunk = chunk.split('\n')[0]
        if name and chunk.endswith(name): chunk = chunk[:-len(name)]
        m = re.match(r'([^\s【（(☞]*【[^】]+】|[^\s【（(☞]+(?:[（(][^）)]+[）)])?)', chunk)
        if not m: continue
        label = m[1]
        br = re.search(r'【([^】]+)】', label)
        spell = re.split(r'[／/・，,┊|｜]', br[1]) if br else [re.sub(r'[（(].*', '', label)]
        spell = [_odoriji(x.strip()) for x in spell if x.strip()]
        head = re.sub(r'【.*|[（(].*', '', label)
        # the label is followed by the member dictionary's name (e.g. 'くれる【呉れる】大辞泉'): keep only a word-like head
        out.append((label, head, spell))
    return out

def follow_jumps(code, sub, txt, forms, reading, others):
    mine = [_odoriji(f) for f in forms if KANJI.search(f)]
    stems = [re.sub('[ぁ-ん]+$', '', f) for f in mine]
    other = [re.sub('[ぁ-ん]+$', '', _odoriji(o)) for o in others]
    texts, seen = [], set()
    for label, head, spell in jump_targets(txt):
        kanji = [x for x in spell if KANJI.search(x)]
        if mine:
            if not any(st and st in k for st in stems for k in kanji) and not any(m in k or k in m for m in mine for k in kanji):
                continue
        elif any(o and o in k for o in other for k in kanji):
            continue
        keys = [label] + ([f'{head}【{"・".join(spell)}】'] if head else []) + spell + ([head] if head else [])
        for key in dict.fromkeys(keys):
            for rid in _records(code, key):
                if rid in seen: continue
                seen.add(rid)
                try: _, raw = mdict_library.record(code, rid)
                except Exception: continue
                for s2, part in _sections(code, raw):
                    if s2 != sub: continue
                    t = plain(part)
                    if t and not is_jump_list(t) and t not in texts:
                        texts.append(t)
            if texts: break
    return texts

def rank(name):
    if any(s.lower() in name.lower() for s in SKIP): return None
    for i, p in enumerate(PRIORITY):
        if p.lower() in name.lower(): return i
    return len(PRIORITY)

def mdx_entries(forms, reading, others=()):
    out = []
    for d in mdict_library.dictionaries():
        if d['code'] == 'MDX_NHK' or 'NHK' in d['name'] or d['code'].startswith('MDX_JLPT'):
            continue                                      # accent handled separately; skip our own dictionary
        if d['code'] in SKIP_CODES or any(x in d['name'] for x in ('All-in-One', 'japaneseAllInOne', '日本語総合')):
            continue                                      # the all-in-one collection is not used
        if rank(d['name']) is None:
            continue
        hits = []
        for key in dict.fromkeys(forms + [reading]):
            hits += [(i, bool(KANJI.search(key))) for i in _records(d['code'], key)]   # kana keys must pass relevant()
        seen_ids, bucket = set(), {}
        for rid, via_kanji in hits:
            if rid in seen_ids: continue
            seen_ids.add(rid)
            try:
                title, raw = mdict_library.record(d['code'], rid)
            except Exception as e:   # damaged/missing source: report and continue
                bucket.setdefault((d['name'], None), []).append(f'（讀取失敗：{e}）'); continue
            for sub, part in _sections(d['code'], raw):
                name = f"{d['name']}／{sub}" if sub else d['name']
                if rank(name) is None: continue
                txt = plain(part)
                if is_jump_list(txt):
                    # the all-in-one collection answers kana keys with "☞くれる【呉れる】…": follow our spelling only
                    for t in follow_jumps(d['code'], sub, txt, forms, reading, others):
                        items = bucket.setdefault((name, sub), [])
                        if t not in items and len(items) < PER_RECORD:
                            items.append(t)
                    continue
                if not txt or not relevant(txt, forms, reading, via_kanji, others): continue
                items = bucket.setdefault((name, sub), [])
                if txt not in items and len(items) < PER_RECORD:
                    items.append(txt)
        for (name, sub), items in bucket.items():
            text = clip('\n\n'.join(items), PER_DICT)
            out.append({'dict': name, 'code': d['code'], 'source': 'mdx', 'rank': rank(name) if rank(name) is not None else 99, 'text': text})
    return out

# ------------------------------------------------------------------------------- Yomitan
def _gloss_text(node):
    if isinstance(node, str): return node
    if isinstance(node, list): return ''.join(_gloss_text(n) for n in node)
    if isinstance(node, dict):
        if node.get('type') == 'image': return ''
        if node.get('tag') == 'rt': return ''
        inner = _gloss_text(node.get('content', node.get('text', '')))
        if node.get('tag') in ('li', 'div', 'p', 'br', 'tr', 'ol', 'ul'): return '\n' + inner + '\n'
        return inner
    return ''

def yomitan_entries(forms, reading):
    if not yomitan_library.available(): return [], []
    out, freqs = [], []
    with closing(yomitan_library.connect()) as db:
        for d in yomitan_library.dictionaries():
            if d['kind'] == 'freq':
                for f in forms:
                    freqs += [dict(x, form=f) for x in yomitan_library._term_freqs(db, f, [d['code']])]
                continue
            if d['kind'] != 'term': continue
            rows = []
            for f in forms:
                rows += db.execute('SELECT * FROM terms WHERE dict=? AND nexp=? ORDER BY score DESC, sequence, id LIMIT 40',
                                   (d['code'], yomitan_library.normalize(f))).fetchall()
            rows = [r for r in rows if not r['reading'] or hira(r['reading']) == hira(reading)] or rows
            if not rows and not any(KANJI.search(f) for f in forms):
                rows = db.execute('SELECT * FROM terms WHERE dict=? AND nread=? ORDER BY score DESC, id LIMIT 20',
                                  (d['code'], yomitan_library.norm_reading(reading))).fetchall()
            if not rows: continue
            lines, seen = [], set()
            for r in rows:
                if r['id'] in seen: continue
                seen.add(r['id'])
                tags = ' '.join(filter(None, [r['def_tags'], r['term_tags']]))
                gloss = plain(_gloss_text(yomitan_library._unpack(r['glossary'])).replace('\n', '<br>'))
                lines.append(f"{r['expression']}【{r['reading']}】" + (f'〔{tags}〕' if tags.strip() else '') + '\n' + gloss)
            name = d['name']
            out.append({'dict': name, 'code': d['code'], 'source': 'yomitan', 'rank': rank(name) if rank(name) is not None else 99,
                        'text': clip('\n\n'.join(lines), PER_DICT)})
    return out, freqs

# ------------------------------------------------------------------------------- master
def read_tsv(path):
    with open(path, encoding='utf-8') as f:
        head = f.readline().rstrip('\n').split('\t')
        return [dict(zip(head, l.rstrip('\n').split('\t'))) for l in f if l.strip()]

def done_ids(vocab):
    """編號 already registered in lessons\\manifest.js (finished lessons)."""
    p = vocab / 'lessons' / 'manifest.js'
    if not p.exists(): return set()
    m = re.search(r'VOCAB_MANIFEST\s*=\s*(\{.*\})\s*;', p.read_text(encoding='utf-8'), re.S)
    try: return set(json.loads(m[1]).get('words', {})) if m else set()
    except ValueError: return set()

def handled_ids(vocab):
    """編號 already written (data\\*.json, even before Build) or parked for later (data\\待補語料\\)."""
    ids = set()
    data = vocab / 'data'
    for p in list(data.glob('*.json')) + list(data.glob('待補語料/*.json')):
        m = re.match(r'(\d{5})_', p.name)
        if m: ids.add(m[1])
        try: d = json.loads(p.read_text(encoding='utf-8'))
        except (OSError, ValueError): continue
        for w in (d.get('words') or []) if isinstance(d, dict) else []:
            if isinstance(w, dict) and re.fullmatch(r'\d{5}', str(w.get('id', ''))): ids.add(str(w['id']))
    return ids

def next_batch(vocab, done):
    """First batch in 批次.tsv that still has words nobody has written or parked."""
    covered = set(done) | handled_ids(vocab)
    for r in read_tsv(vocab / 'master' / '批次.tsv'):
        if any(i not in covered for i in r['編號'].split()):
            return r['批次']
    return None

def ask(question):
    try: return input(question + '（y／N）：').strip().lower() in ('y', 'yes')
    except EOFError: return False

def select(vocab, args):
    rows = read_tsv(vocab / 'master' / '語彙大全.tsv')
    by_id = {r['編號']: r for r in rows}
    if not args or args[0] in ('next', '下一批', '下'):
        nb = next_batch(vocab, done_ids(vocab))
        if not nb: raise SystemExit('所有批次都已完成！')
        print(f'下一批（第一個還有未完成詞的批次）：{nb}')
        args = [nb]
    if len(args) == 1 and re.fullmatch(r'\d{1,4}(-\d{1,4})?', args[0]):
        a, _, b = args[0].partition('-')
        batches = {r['批次']: r for r in read_tsv(vocab / 'master' / '批次.tsv')}
        out = []
        for n in range(int(a), int(b or a) + 1):
            key = '%04d' % n
            if key not in batches: raise SystemExit(f'批次 {key} 不存在於 master\\批次.tsv')
            out.append(('批次' + key, [by_id[i] for i in batches[key]['編號'].split()]))
        return out
    if len(args) == 2 and all(re.fullmatch(r'\d{5}', a) for a in args):
        lo, hi = args
        return [(f'{lo}-{hi}', [r for r in rows if lo <= r['編號'] <= hi])]
    picked = []
    for a in args:
        match = ([r for r in rows if a in (r['語'], r['別表記'], r['編號'])]
                 or [r for r in rows if a == r['讀音']])
        if not match: print('  找不到：', a)
        picked += [m for m in match if m not in picked]
    return [('words_' + '・'.join(args)[:40], picked)]

def group_info(vocab):
    path = vocab / 'master' / '語群.tsv'
    return {r['語群']: r for r in read_tsv(path)} if path.exists() else {}

def export_word(w, groups, homophones):
    forms = [f for f in (w['語'], w['別表記']) if f]
    reading = w['讀音']
    others = [f for r in homophones.get(reading, []) if r['編號'] != w['編號'] for f in (r['語'], r['別表記']) if f and KANJI.search(f)]
    entries = mdx_entries(forms, reading, others)
    yt, freqs = yomitan_entries(forms, reading)
    entries += yt
    entries.sort(key=lambda e: (e['rank'], e['dict']))
    used, kept, dropped = 0, [], []
    for e in entries:
        if used + len(e['text']) > PER_WORD and kept:
            dropped.append(e['dict']); continue
        used += len(e['text']); kept.append({k: v for k, v in e.items() if k != 'rank'})
    gid = {g for g in w.get('所屬語群', '').split() if g} | ({w['語群']} if w.get('語群') else set())
    return {
        'id': w['編號'], 'word': w['語'], 'reading': reading, 'alt': w['別表記'], 'pos': w['品詞'], 'tier': w['層'],
        'jlpt': w['JLPT'], 'style': w.get('語體', ''), 'jmdict': w['JMdict序號'],
        'freq': {'jpdb': w['JPDB頻度'], 'aozora': w['青空頻度'], 'yomitan': freqs},
        'group': w.get('語群', ''),
        'groups': [{'id': g, 'name': groups[g]['意味分類'], 'members': groups[g]['成員（編號:語）'],
                    'wlsp_all': groups[g]['分類語彙表全成員']} for g in sorted(gid) if g in groups],
        'nhk': nhk_entries(forms, reading, others),
        'entries': kept, 'dropped_for_length': dropped,
    }

def as_markdown(rec):
    L = [f"# {rec['id']} {rec['word']}【{rec['reading']}】" + (f"（別表記：{rec['alt']}）" if rec['alt'] else ''),
         f"品詞：{rec['pos']}｜層：{rec['tier']}｜JLPT：{rec['jlpt'] or '—'}｜語體：{rec['style'] or '—'}｜JPDB：{rec['freq']['jpdb'] or '—'}｜青空：{rec['freq']['aozora'] or '—'}",
         '']
    for g in rec['groups']:
        L += [f"## 語群 {g['id']} {g['name']}" + ('（主）' if g['id'] == rec['group'] else ''), f"本表成員：{g['members']}", f"分類語彙表全成員：{g['wlsp_all']}", '']
    L += ['## NHK アクセント']
    L += [f"- {n['headword']}：" + '／'.join(f"{a['pattern']}［{a['accent']}］{a['type']}" for a in n['accents']) for n in rec['nhk']] or ['（NHK 無此詞）']
    if rec['freq']['yomitan']:
        L += ['', '## 頻度（Yomitan）'] + [f"- {f['name']}：{f['display']}（{f['form']}）" for f in rec['freq']['yomitan']]
    for e in rec['entries']:
        L += ['', f"## {e['dict']}", e['text']]
    if rec['dropped_for_length']:
        L += ['', '（因長度省略：' + '、'.join(rec['dropped_for_length']) + '）']
    return '\n'.join(L) + '\n'

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('select', nargs='*', help='批次號／編號範圍／單字；省略或 next＝下一批')
    ap.add_argument('--yes', action='store_true', help='不詢問，直接覆蓋')
    ap.add_argument('--vocab', type=Path)
    a = ap.parse_args()
    if not a.select and sys.stdin.isatty():
        print('匯出 JLPT語彙 的辭典語料')
        print('  直接按 Enter：下一批（自動找第一個還沒完成的批次）')
        print('  批次號：0001  或  0001-0003')
        print('  編號範圍：00101 00120')
        print('  單字：気持ち 心持ち')
        a.select = input('請輸入：').split()
    vocab = a.vocab or (Path((HERE / 'vocab_root.txt').read_text(encoding='utf-8').strip()) if (HERE / 'vocab_root.txt').exists() else DEFAULT_VOCAB)
    if not (vocab / 'master' / '語彙大全.tsv').exists():
        raise SystemExit(f'找不到 {vocab}\\master\\語彙大全.tsv（用 --vocab 或 vocab_root.txt 指定語彙根目錄）')
    if not mdict_library.INDEX.exists():
        raise SystemExit('找不到 dictionaries\\mdict-index.sqlite3')
    if not yomitan_library.available():
        print('注意：沒有 yomitan-index.sqlite3，只匯出 MDX（先執行 Import Yomitan dictionaries.cmd）')
    groups = group_info(vocab)
    homophones = {}
    for r in read_tsv(vocab / 'master' / '語彙大全.tsv'):
        homophones.setdefault(r['讀音'], []).append(r)
    out_dir = vocab / 'sources'
    done = done_ids(vocab)
    for name, words in select(vocab, a.select):
        if not words: print(name, '沒有符合的詞'); continue
        finished = [w for w in words if w['編號'] in done]
        if finished and not a.yes:
            print(f'⚠ {name}：{len(finished)}/{len(words)} 個詞已經做完（' + '・'.join(w['語'] for w in finished[:8]) + ('…' if len(finished) > 8 else '') + '）')
            nb = next_batch(vocab, done)
            if len(finished) == len(words) and nb: print(f'  還沒做的下一批是：{nb}')
            if not ask('  確定還要匯出這一批嗎？'): print('  已略過。'); continue
        if (out_dir / (name + '.jsonl')).exists() and not a.yes:
            print(f'⚠ {name} 的語料已經存在：sources\\{name}.jsonl')
            if not ask('  要重新匯出並覆蓋嗎？'): print('  已略過（保留原檔）。'); continue
        md_dir = out_dir / name; md_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / (name + '.jsonl')
        with open(path, 'w', encoding='utf-8') as f:
            for i, w in enumerate(words, 1):
                rec = export_word(w, groups, homophones)
                f.write(json.dumps(rec, ensure_ascii=False) + '\n')
                safe = re.sub(r'[\\/:*?"<>|]', '_', rec['word'])
                (md_dir / f"{rec['id']}_{safe}.md").write_text(as_markdown(rec), encoding='utf-8')
                size = sum(len(e['text']) for e in rec['entries'])
                print(f"  [{i}/{len(words)}] {rec['id']} {rec['word']}：{len(rec['entries'])} 本辭典，{size:,} 字，NHK {len(rec['nhk'])}")
        print('完成：', path)

if __name__ == '__main__':
    main()
