"""game_link without Windows: a fake process with the Pal engine's memory layout."""
import struct
import unittest

import game_link


class FakeProcess:
    def __init__(self, blocks, exe=''):
        self.blocks = blocks            # {address: bytes}
        self.exe = exe

    def image_path(self):
        return self.exe

    def regions(self, private_only=True):
        return [(base, len(data)) for base, data in sorted(self.blocks.items())]

    def committed(self, address, size):
        parts = []
        for base, data in sorted(self.blocks.items()):
            lo, hi = max(address, base), min(address + size, base + len(data))
            if hi > lo:
                parts.append((lo, hi - lo))
        return parts

    def read(self, address, size):
        for base, data in self.blocks.items():
            if base <= address < base + len(data):
                return data[address - base:address - base + size]
        return None

    def u32(self, address):
        raw = self.read(address, 4)
        return struct.unpack('<I', raw)[0] if raw and len(raw) == 4 else None

    def find(self, needle, aligned=1, limit=8):
        hits = []
        for base, data in self.blocks.items():
            at = data.find(needle)
            while at != -1:
                if (base + at) % aligned == 0:
                    hits.append(base + at)
                at = data.find(needle, at + 1)
        return hits[:limit]

    def scan(self, pattern, aligned=1, limit=32, overlap=1024):
        hits = []
        for base, data in self.blocks.items():
            for match in pattern.finditer(data):
                if (base + match.start()) % aligned == 0:
                    hits.append(base + match.start())
        return hits[:limit]

    def alive(self):
        return True


def text_dat(strings):
    out = bytearray(b'_TEXT_LIST__' + struct.pack('<I', len(strings)))
    offsets = []
    for i, s in enumerate(strings):
        offsets.append(len(out))
        out += struct.pack('<I', i) + s.encode('cp932') + b'\0'
    return bytes(out), offsets


class PalLink(unittest.TestCase):
    def setUp(self):
        self.text, self.offsets = text_dat(['システム', '「逃げろー！」<br><s20>快逃！</s>', '住人Ａ',
                                           '『<rウィドウ>瓦礫を見ろ</r>』<br>　<d0005>反現実</d>だ'])
        engine = game_link.PalEngine
        context = bytearray(0x60000)
        struct.pack_into('<I', context, engine.TEXT_PTR, 0x200000)
        struct.pack_into('<I', context, engine.TEXT_SIZE, len(self.text))
        struct.pack_into('<I', context, engine.SCRIPT_PTR, 0x300000)
        struct.pack_into('<I', context, engine.CURRENT, self.offsets[1])
        struct.pack_into('<I', context, engine.NAME, self.offsets[2])
        self.context = context
        stray = struct.pack('<I', 0x200000) + b'\0' * 12          # another pointer to TEXT that is not the VM
        self.process = FakeProcess({0x100000: bytes(context), 0x200000: self.text,
                                    0x300000: b'Sv20' + b'\0' * 12, 0x400000: stray})

    def test_detect_and_follow(self):
        engine = game_link.PalEngine.detect(self.process)
        self.assertEqual(engine.context, 0x100000)
        line = engine.current()
        self.assertEqual(line, {'key': 'main|1', 'label': '#1', 'number': 1, 'text': '「逃げろー！」', 'speaker': '住人Ａ'})
        struct.pack_into('<I', self.context, engine.CURRENT, self.offsets[3])
        struct.pack_into('<I', self.context, engine.NAME, 0x0FFFFFFF)
        self.process.blocks[0x100000] = bytes(self.context)
        self.assertEqual(engine.current(), {'key': 'main|3', 'label': '#3', 'number': 3, 'text': '『瓦礫を見ろ』\n　反現実だ', 'speaker': ''})

    def test_no_line_yet(self):
        engine = game_link.PalEngine.detect(self.process)
        struct.pack_into('<I', self.context, engine.CURRENT, 0)
        self.process.blocks[0x100000] = bytes(self.context)
        self.assertIsNone(engine.current())

    def test_not_pal(self):
        self.assertIsNone(game_link.PalEngine.detect(FakeProcess({0x1000: b'nothing here'})))


def sq_value(kind, value=0):
    """A 16-byte Squirrel value: type tag, padding, 8-byte payload (32-bit integers)."""
    return struct.pack('<II', kind, 0) + (struct.pack('<iI', value, 0) if kind == game_link.KaleidoEngine.INTEGER else
                                         struct.pack('<Q', value))


def sq_string(text):
    """A Squirrel string object: byte length at +0x28, UTF-8 text at +0x38."""
    raw = text.encode('utf-8')
    head = bytearray(0x38)
    struct.pack_into('<Q', head, 0, 0x7FF600001234)           # vtable
    struct.pack_into('<I', head, 0x28, len(raw))
    return bytes(head) + raw + b'\0'


def scene_player(scene_address, text_id, null_scene=False):
    """Fields curSceneName … outlineCur of a Kaleido ScenePlayer, with unrelated fields before them."""
    k = game_link.KaleidoEngine
    fields = [sq_value(k.NULL) if null_scene else sq_value(k.STRING, scene_address), sq_value(k.INTEGER, 28),
              sq_value(0x0A008000, 0x900000), sq_value(k.BOOL, 0), sq_value(k.INTEGER, 1), sq_value(k.INTEGER, 97),
              sq_value(k.INTEGER, 31), sq_value(k.INTEGER, 98), sq_value(k.INTEGER, text_id), sq_value(k.BOOL, 0),
              sq_value(k.BOOL, 0), sq_value(k.INTEGER, -1), sq_value(0x0A000020, 0x910000), sq_value(0x0A000020, 0x920000),
              sq_value(k.BOOL, 0), sq_value(k.INTEGER, 0), sq_value(k.INTEGER, 310546)]
    before = sq_value(k.BOOL, 1) * 3 + sq_value(k.INTEGER, 5) * 2 + sq_value(k.NULL) * 3
    return before + b''.join(fields), len(before)


class KaleidoLink(unittest.TestCase):
    """STEINS;GATE RE:BOOT layout: curSceneName "resg01_06.ks*start", curTextId 16 → 台本 *start#15."""

    def setUp(self):
        player, self.offset = scene_player(0x300000, 16)
        self.process = FakeProcess({0x100000: b'\xaa' * 8 + sq_string('curTextId'), 0x200000: player,
                                    0x300000: sq_string('resg01_06.ks*start'), 0x310000: sq_string('resg00_01.ks')})
        self.field = 0x200000 + self.offset

    def set_text(self, text_id, block=0x200000, scene=0x300000):
        self.process.blocks[block] = scene_player(scene, text_id)[0]

    def test_detect_and_follow(self):
        engine = game_link.KaleidoEngine.detect(self.process)
        self.assertEqual(engine.player, self.field)
        line = engine.current()
        self.assertEqual(line['key'], 'scenario/resg01_06.ks|*start#15')
        self.assertEqual((line['number'], line['label'], line['text']), (15, 'resg01_06.ks *start#15', ''))
        self.set_text(17)
        self.assertEqual(engine.current()['key'], 'scenario/resg01_06.ks|*start#16')

    def test_scene_without_label(self):
        self.set_text(4, scene=0x310000)
        line = game_link.KaleidoEngine.detect(self.process).current()
        self.assertEqual(line['key'], 'scenario/resg00_01.ks|#3')

    def test_title_screen_then_new_player(self):
        # No story yet: the scene name is null. The engine attaches and waits.
        self.process.blocks[0x200000] = scene_player(0, 0, null_scene=True)[0]
        engine = game_link.KaleidoEngine.detect(self.process)
        self.assertIsNotNone(engine)
        self.assertIsNone(engine.current())
        # Loading a save: the old player is emptied and a new one appears elsewhere.
        self.process.blocks[0x200000] = sq_value(game_link.KaleidoEngine.NULL) * 40
        self.process.blocks[0x400000] = scene_player(0x300000, 3)[0]
        engine.next_search = 0
        self.assertEqual(engine.current()['key'], 'scenario/resg01_06.ks|*start#2')
        self.assertEqual(engine.player, 0x400000 + self.offset)

    def test_waits_between_searches(self):
        engine = game_link.KaleidoEngine.detect(self.process)
        self.process.blocks[0x200000] = sq_value(game_link.KaleidoEngine.NULL) * 40
        self.assertIsNone(engine.current())             # searched now, nothing found
        self.process.blocks[0x400000] = scene_player(0x300000, 3)[0]
        self.assertIsNone(engine.current())             # too soon to search again
        engine.next_search = 0
        self.assertIsNotNone(engine.current())

    def test_rejects_other_memory(self):
        self.assertIsNone(game_link.KaleidoEngine.detect(FakeProcess({0x1000: b'nothing here'})))
        # The field name alone (not a Squirrel string) is not enough.
        self.assertIsNone(game_link.KaleidoEngine.detect(FakeProcess({0x1000: b'\0' * 0x40 + b'curTextId\0'})))
        # A field block whose scene name is not a scene name is not the player.
        engine = game_link.KaleidoEngine(FakeProcess({0x300000: sq_string('hello world'), 0x200000: scene_player(0x300000, 2)[0]}))
        self.assertIsNone(engine.current())
        self.assertIsNone(engine.player)

    def test_engine_order(self):
        self.assertIs(game_link.engines_for('SGRE_Steam.exe')[0], game_link.KaleidoEngine)
        self.assertIs(game_link.engines_for('P3R.exe')[0], game_link.AtlusBmdEngine)
        self.assertIs(game_link.engines_for('totsulover.exe')[0], game_link.PalEngine)
        self.assertEqual(set(game_link.engines_for('other.exe')), set(game_link.ENGINES))


def msg1(dialogs, speakers=()):
    """A converted Atlus message file as P3R keeps it in memory: "MSG1", little-endian, self-relative offsets
    (the text size after each page table stays big-endian). dialogs: [(name, [page bytes], speaker index)]."""
    count = len(dialogs)
    out = bytearray(0x20 + 8 * count + 16)
    out[8:12] = b'MSG1'
    struct.pack_into('<I', out, 0x18, count)
    rel = lambda at, target: struct.pack_into('<I', out, at, target - at)
    for k, (name, pages, speaker) in enumerate(dialogs):
        while len(out) % 4:
            out += b'\0'
        o = len(out)
        struct.pack_into('<I', out, 0x20 + 8 * k, 0)
        rel(0x20 + 8 * k + 4, o)
        out += name.ljust(24, b'\0') + struct.pack('<HH', len(pages), speaker)
        head = len(out)
        out += b'\0' * (4 * len(pages)) + struct.pack('>I', sum(len(p) for p in pages))
        for j, page in enumerate(pages):
            rel(head + 4 * j, len(out))
            out += page
    while len(out) % 4:
        out += b'\0'
    so = 0x20 + 8 * count
    table = len(out)
    rel(so, table)
    struct.pack_into('<I', out, so + 4, len(speakers))
    out += b'\0' * (4 * len(speakers))
    for k, name in enumerate(speakers):
        rel(table + 4 * k, len(out))
        out += name.encode('utf-8') + b'\0'
    struct.pack_into('<I', out, 4, len(out))
    return bytes(out)


def work(copy, page, state=0, open_=True, pending=False, colour=0xF0F3FCFF):
    """A P3R "message work" from 16 bytes before its (copy, page) pair: 0x28 while its message is open, 1, copy
    start, page start, ..., 01 01 20 00 + text colour, state (0 = page of the open message), bit 16 = next page."""
    return (b'\0' * 7 + (b'\x28' if open_ else b'\0') + struct.pack('<QQQ', 1, copy, page) + b'\0' * 16 +
            b'\x01\x01\x20\x00' + struct.pack('<I', colour) + struct.pack('<II', 1, state) +
            struct.pack('<II', 0xF761, 0x10000 if pending else 0) + b'\0' * 8)


ME = b'\xfe\xf1\x81'                     # the protagonist's name (function 4, 1)
ZH = b'\xfe\xf2\x01\x16\x01'            # a bilingual patch's colour 21: its Chinese line starts here


class AtlusLink(unittest.TestCase):
    COPY, WORKS = 0x30000000, 0x40000000

    def setUp(self):
        self.pages = [ME + 'さん、おはよう。'.encode() + b'\n' + ZH + '早安。'.encode() + b'\xfe\xf2\x01\x1c\x01\0',
                      'もう寝よう…'.encode() + b'\r\n' + b'\0', '……'.encode() + b'\0']
        self.copy = msg1([(b'MSG_000_0_0', self.pages[:2], 0), (b'MND_001_0_0', self.pages[2:], 1)], ['山田', '主人公'])
        self.page_at = []
        at = self.copy.index(self.pages[0])
        for p in self.pages:
            at = self.copy.index(p, at)
            self.page_at.append(self.COPY + at)
        self.process = FakeProcess({self.COPY: self.copy, 0x50000000: b'\0' * 64}, exe='C:\\Games\\P3R\\P3R.exe')

    def engine(self, file='Xrd777/Events/BMD_Test'):
        engine = game_link.AtlusBmdEngine.detect(self.process)
        engine.full_index, engine.first_index = ({self.fingerprint(): file} if file else {}), {}
        return engine

    def fingerprint(self):
        import hashlib
        e = game_link.AtlusBmdEngine
        h = hashlib.sha1()
        for name, pages in ((b'MSG_000_0_0', self.pages[:2]), (b'MND_001_0_0', self.pages[2:])):
            h.update(name + b'|')
            for p in pages:
                h.update(e.japanese(p) + b'#')
        return h.hexdigest()

    def show(self, *works):
        block = b'\0' * 0x40 + b''.join(w.ljust(0xA0, b'\0') for w in works)
        self.process.blocks[self.WORKS] = block

    def test_detect_by_executable(self):
        self.assertIsNotNone(game_link.AtlusBmdEngine.detect(FakeProcess({}, exe='D:\\SteamLibrary\\P3R.exe')))
        self.assertIsNone(game_link.AtlusBmdEngine.detect(FakeProcess({0x1000: b'nothing'}, exe='C:\\notepad.exe')))
        self.assertIs(game_link.engines_for('P3R.exe')[0], game_link.AtlusBmdEngine)
        self.assertIn('ペルソナ３ リロード', game_link.supported_games())

    def test_follow_pages(self):
        engine = self.engine()
        self.assertIsNone(engine.current())                  # nothing on screen yet
        self.show(work(self.COPY, self.page_at[0]))
        engine.next_full = 0
        line = engine.current()
        self.assertEqual(line, {'key': 'Xrd777/Events/BMD_Test|0:MSG_000_0_0#0', 'label': 'BMD_Test MSG_000_0_0#0',
                                'number': 0, 'text': '〈主人公〉さん、おはよう。', 'speaker': '山田'})
        self.show(work(self.COPY, self.page_at[1]))           # same work, next page: no full scan needed
        self.assertEqual(engine.current()['key'], 'Xrd777/Events/BMD_Test|0:MSG_000_0_0#1')
        self.assertEqual(engine.current()['text'], 'もう寝よう…')
        self.show(work(self.COPY, self.page_at[2]))
        line = engine.current()
        self.assertEqual((line['key'], line['speaker'], line['text']), ('Xrd777/Events/BMD_Test|1:MND_001_0_0#0', '主人公', '……'))
        self.process.blocks[self.WORKS] = b'\0' * 0x200        # the message closed: its work is freed
        self.assertIsNone(engine.current())

    def test_newest_work_on_screen_wins(self):
        engine = self.engine()
        self.show(work(self.COPY, self.page_at[0]), work(self.COPY, self.page_at[2], state=5))
        engine.next_full = 0
        self.assertEqual(engine.current()['key'], 'Xrd777/Events/BMD_Test|0:MSG_000_0_0#0')
        # the next message gets a work of its own; the old one is still there for a moment
        self.show(work(self.COPY, self.page_at[0]), work(self.COPY, self.page_at[2], state=0))
        self.assertEqual(engine.current()['key'], 'Xrd777/Events/BMD_Test|1:MND_001_0_0#0')

    def test_next_page_waits_until_shown(self):
        # events: the next page's work exists early, marked as "next"; the line moves when it is shown
        engine = self.engine()
        white = 0xFFFFFFFF
        self.show(work(self.COPY, self.page_at[0], colour=white), work(self.COPY, self.page_at[1], pending=True, colour=white))
        engine.next_full = 0
        self.assertEqual(engine.current()['key'], 'Xrd777/Events/BMD_Test|0:MSG_000_0_0#0')
        self.show(work(self.COPY, self.page_at[0], colour=white), work(self.COPY, self.page_at[1], colour=white))
        self.assertEqual(engine.current()['key'], 'Xrd777/Events/BMD_Test|0:MSG_000_0_0#1')
        # connecting while both pages were already shown: the later page is the one on screen
        fresh = self.engine()
        fresh.next_full = 0
        self.assertEqual(fresh.current()['key'], 'Xrd777/Events/BMD_Test|0:MSG_000_0_0#1')

    def test_field_next_page_uncoloured_until_shown(self):
        # field messages: the next page's work has no colour yet
        engine = self.engine()
        self.show(work(self.COPY, self.page_at[0]), work(self.COPY, self.page_at[1], colour=0xFFFFFFFF))
        engine.next_full = 0
        self.assertEqual(engine.current()['key'], 'Xrd777/Events/BMD_Test|0:MSG_000_0_0#0')
        self.show(work(self.COPY, self.page_at[0]), work(self.COPY, self.page_at[1]))
        self.assertEqual(engine.current()['key'], 'Xrd777/Events/BMD_Test|0:MSG_000_0_0#1')

    def test_next_message_elsewhere_found_right_away(self):
        import time
        engine = self.engine()
        self.show(work(self.COPY, self.page_at[0]))
        engine.next_full = 0
        self.assertEqual(engine.current()['key'], 'Xrd777/Events/BMD_Test|0:MSG_000_0_0#0')
        engine.next_full, engine.last_full = time.monotonic() + 60, -1.0     # no scan due for a while
        self.process.blocks[self.WORKS] = b'\0' * 0x200                     # that message ended…
        self.process.blocks[0x60000000] = b'\0' * 0x40 + work(self.COPY, self.page_at[2]).ljust(0xA0, b'\0')   # …the next is elsewhere
        self.assertEqual(engine.current()['key'], 'Xrd777/Events/BMD_Test|1:MND_001_0_0#0')

    def test_new_work_in_a_known_page_needs_no_full_scan(self):
        import time
        engine = self.engine()
        self.show(work(self.COPY, self.page_at[0]))
        engine.next_full = 0
        self.assertEqual(engine.current()['key'], 'Xrd777/Events/BMD_Test|0:MSG_000_0_0#0')
        engine.next_full, engine.last_full = time.monotonic() + 60, time.monotonic()   # no full scan now
        # the next page's work lands in another part of the same 64 KB page
        self.process.blocks[self.WORKS + 0x8000] = b'\0' * 0x40 + work(self.COPY, self.page_at[1]).ljust(0xA0, b'\0')
        self.assertEqual(engine.current()['key'], 'Xrd777/Events/BMD_Test|0:MSG_000_0_0#1')

    def test_closed_or_finished_messages_are_not_shown(self):
        engine = self.engine()
        self.show(work(self.COPY, self.page_at[0], open_=False), work(self.COPY, self.page_at[2], state=5))
        engine.next_full = 0
        self.assertIsNone(engine.current())

    def test_unknown_file_still_has_text(self):
        engine = self.engine(file=None)
        self.show(work(self.COPY, self.page_at[0]))
        engine.next_full = 0
        line = engine.current()
        self.assertEqual((line['key'], line['text']), ('?|0:MSG_000_0_0#0', '〈主人公〉さん、おはよう。'))

    def test_fingerprint_ignores_bilingual_line(self):
        e = game_link.AtlusBmdEngine
        self.assertEqual(e.japanese(self.pages[0]), e.japanese(ME + 'さん、おはよう。'.encode() + b'\r\n\0'))
        self.assertEqual(e.first_line(self.pages[0]), 'さん、おはよう。'.encode())
        self.assertEqual(e.first_line(self.pages[1]), e.first_line('もう寝よう…'.encode() + b'\n' + ZH + b'x\0'))

    def test_work_must_point_into_a_message_file(self):
        engine = self.engine()
        self.show(work(0x50000000, 0x50000010))               # not a converted message file
        engine.next_full = 0
        self.assertIsNone(engine.current())


class GameLinkSettings(unittest.TestCase):
    def test_select_game_window(self):
        import capture_sources
        rows = [{'handle': 5, 'pid': 9, 'process': 'totsulover.exe', 'title': 'ディメンション凸ラバース!!'}]
        chosen = capture_sources.select({'mode': 'game', 'handle': 5, 'pid': 9}, rows)
        self.assertEqual((chosen['capture_mode'], chosen['window_pid'], chosen['window_process']), ('game', 9, 'totsulover.exe'))
        # A window that closed, or none picked ("automatic"): game link finds the running game by itself.
        for body in ({'mode': 'game', 'handle': 6, 'pid': 9}, {'mode': 'game'}):
            auto = capture_sources.select(body, rows)
            self.assertEqual((auto['capture_mode'], auto['window_pid'], auto['window_process']), ('game', 0, ''))
        with self.assertRaises(ValueError):
            capture_sources.select({'mode': 'window', 'handle': 6, 'pid': 9}, rows)

    def test_candidates_find_running_games(self):
        alive = [(4, 'ApplicationFrameHost.exe'), (7, 'chrome.exe'), (9, 'totsulover.exe'), (12, 'sgre_steam.exe')]
        # Nothing picked: every running supported game, in process order.
        self.assertEqual(game_link.candidates(alive), [(9, 'totsulover.exe'), (12, 'sgre_steam.exe')])
        # The picked window comes first, even when it is not a known game.
        self.assertEqual(game_link.candidates(alive, 4, 'ApplicationFrameHost.exe')[0], (4, 'ApplicationFrameHost.exe'))
        # Once it turned out not to be a game, it is skipped and the running game is used.
        skip = {(4, 'applicationframehost.exe')}
        self.assertEqual(game_link.candidates(alive, 4, 'ApplicationFrameHost.exe', skip)[0], (9, 'totsulover.exe'))
        # The picked game restarted with a new pid: found again by its executable name.
        self.assertEqual(game_link.candidates([(20, 'sgre_steam.exe'), (21, 'totsulover.exe')], 12, 'sgre_steam.exe')[0],
                         (20, 'sgre_steam.exe'))
        self.assertEqual(game_link.candidates([(7, 'chrome.exe')]), [])
        self.assertIn('ディメンション凸ラバース!!', game_link.supported_games())

    def test_game_link_survives_restart(self):
        import journal
        self.assertEqual(journal.startup_capture_mode({'capture_mode': 'game'}, True), 'game')
        self.assertEqual(journal.startup_capture_mode({'capture_mode': 'window'}, True), 'paste')
        self.assertEqual(journal.startup_capture_mode({'capture_mode': 'obs'}, True), 'paste')
        self.assertEqual(journal.startup_capture_mode({}, True), 'paste')
        self.assertEqual(journal.startup_capture_mode({}, False), 'obs')
        self.assertEqual(journal.startup_capture_mode({'capture_mode': 'window'}, False), 'window')

    def test_japanese_window_title_finds_script(self):
        import json, tempfile
        from pathlib import Path
        import script_library
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary) / 'dimension-totsu-lovers'
            folder.mkdir()
            (folder / 'script.json').write_text(json.dumps({'script_id': 'dimension-totsu-lovers', 'game': 'ディメンション凸ラバース!!',
                                                            'rows': [{'ja': 'テスト。'}]}, ensure_ascii=False), encoding='utf-8')
            library = script_library.Library(Path(temporary))
            library.refresh()
            self.assertEqual(library.for_window('ディメンション凸ラバース!!').id, 'dimension-totsu-lovers')
            self.assertIsNone(library.for_window('メモ帳'))


if __name__ == '__main__':
    unittest.main()
