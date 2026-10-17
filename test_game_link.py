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
        self.assertEqual(line, {'number': 1, 'text': '「逃げろー！」', 'speaker': '住人Ａ'})
        struct.pack_into('<I', self.context, engine.CURRENT, self.offsets[3])
        struct.pack_into('<I', self.context, engine.NAME, 0x0FFFFFFF)
        self.process.blocks[0x100000] = bytes(self.context)
        self.assertEqual(engine.current(), {'number': 3, 'text': '『瓦礫を見ろ』\n　反現実だ', 'speaker': ''})

    def test_no_line_yet(self):
        engine = game_link.PalEngine.detect(self.process)
        struct.pack_into('<I', self.context, engine.CURRENT, 0)
        self.process.blocks[0x100000] = bytes(self.context)
        self.assertIsNone(engine.current())

    def test_not_pal(self):
        self.assertIsNone(game_link.PalEngine.detect(FakeProcess({0x1000: b'nothing here'})))


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
