"""game_link without Windows: a fake process with the Pal engine's memory layout."""
import struct
import unittest

import game_link


class FakeProcess:
    def __init__(self, blocks):
        self.blocks = blocks            # {address: bytes}

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
        self.assertIs(game_link.engines_for('totsulover.exe')[0], game_link.PalEngine)
        self.assertEqual(set(game_link.engines_for('other.exe')), set(game_link.ENGINES))


class GameLinkSettings(unittest.TestCase):
    def test_select_game_window(self):
        import capture_sources
        rows = [{'handle': 5, 'pid': 9, 'process': 'totsulover.exe', 'title': 'ディメンション凸ラバース!!'}]
        chosen = capture_sources.select({'mode': 'game', 'handle': 5, 'pid': 9}, rows)
        self.assertEqual((chosen['capture_mode'], chosen['window_pid'], chosen['window_process']), ('game', 9, 'totsulover.exe'))
        with self.assertRaises(ValueError):
            capture_sources.select({'mode': 'game', 'handle': 6, 'pid': 9}, rows)

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
