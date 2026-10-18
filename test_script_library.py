"""Script import regressions: synthetic text and disposable folders only."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import script_library as scripts


class ScriptImports(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.patch = patch.object(scripts, 'folders', return_value=[])
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.library = scripts.Library(self.root / 'imports')

    def test_import_restart_search_and_duplicate_do_not_overwrite(self):
        data = scripts.template()
        first = self.library.import_script(data)
        path = self.root / 'imports' / first['id'] / 'script.json'
        before = path.read_bytes()
        with self.assertRaisesRegex(ValueError, 'already loaded'):
            self.library.import_script({**data, 'rows': [{'ja': 'changed'}]})
        self.assertEqual(before, path.read_bytes())
        reopened = scripts.Library(self.root / 'imports')
        self.assertEqual(len(reopened.refresh()), 1)
        self.assertEqual(reopened.get(first['id']).search(q='weather')['total'], 1)
        self.assertEqual(reopened.get(first['id']).search(need='all')['total'], 1)

    def test_two_titles_with_same_row_keys_locate_independently(self):
        for identity in ('novel-a', 'novel-b'):
            self.library.import_script({'game': identity, 'script_id': identity,
                                        'rows': [{'source': 'ch1', 'id': '1', 'ja': identity}]})
        for identity in ('novel-a', 'novel-b'):
            script = self.library.get(identity)
            row = script.row(1)
            self.assertEqual(self.library.locate(row['source_id']), {'script': identity, 'n': 1})
            self.assertEqual(self.library.locate(script.matcher_rows()[0]['id']), {'script': identity, 'n': 1})

    def test_minimal_unicode_titles_get_different_persistent_ids(self):
        a = self.library.import_script({'game': '春の物語', 'rows': [{'ja': '春。'}]})
        b = self.library.import_script({'game': '夏の物語', 'rows': [{'en': 'Summer.'}]})
        self.assertNotEqual(a['id'], b['id'])
        row = self.library.get(a['id']).row(1)
        self.assertEqual((row['source'], row['id'], row['kind']), ('main', '1', 'dialogue'))
        self.assertEqual(row['en'], '')

    def test_invalid_files_write_nothing(self):
        cases = [None, [], {}, {'game': 'X', 'rows': []}, {'game': 'X', 'rows': [None]},
                 {'game': 'X', 'rows': [{'ja': None}]}, {'game': 'X', 'rows': [{'ja': []}]},
                 {'game': 'X', 'rows': [{'ja': 'x', 'kind': 'invalid'}]},
                 {'game': 'X', 'rows': [{'ja': 'x', 'source': 'a|b'}]},
                 {'game': 'X', 'rows': [{'ja': 'x', 'id': True}]},
                 {'game': 'X', 'rows': [{'ja': 'x', 'id': 1}, {'ja': 'y', 'id': '1'}]},
                 {'game': 'X', 'script_id': '../../escape', 'rows': [{'ja': 'x'}]},
                 {'game': 'X', 'script_id': 'con', 'rows': [{'ja': 'x'}]},
                 {'game': 'X', 'script_id': 'auto', 'rows': [{'ja': 'x'}]},
                 {'game': 'X', 'script_id': {}, 'rows': [{'ja': 'x'}]},
                 {'game': 'X', 'rows': [{'ja': ' '}]},
                 {'game': 'X', 'rows': [{'ja': 'x' * 100001}]}]
        for data in cases:
            with self.subTest(data=str(data)[:100]), self.assertRaises(ValueError):
                self.library.import_script(data)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_legacy_arrays_bom_annotations_and_original_order(self):
        folder = self.root / 'legacy'
        folder.mkdir()
        rows = [{'source': 'ch', 'id': '20', 'kind': 'dialogue', 'ja': '先。'},
                {'source': 'ch', 'id': '3', 'kind': 'dialogue', 'ja': '後。'}]
        (folder / 'script.json').write_text(json.dumps(rows), encoding='utf-8-sig')
        (folder / 'annotations.json').write_text(json.dumps({'items': {'ch|3': {'tr': '後'}}}), encoding='utf-8')
        script = scripts.Script(folder).load()
        self.assertEqual([r['id'] for r in script.search()['rows']], ['20', '3'])
        self.assertTrue(script.row(2)['annotated'])


if __name__ == '__main__':
    unittest.main()


class ScriptVoices(unittest.TestCase):
    """台本 voices: clips are read in place from the game's archive (synthetic PAC files only)."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.patch = patch.object(scripts, 'folders', return_value=[])
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.library = scripts.Library(self.root / 'imports')
        self.game = self.root / 'game'
        self.game.mkdir()
        self.pac(self.game / 'voice.pac', {'VO04_0018.OGG': b'OggS-first', 'VO05_0103.OGG': b'OggS-second'})

    @staticmethod
    def pac(path, files):
        import struct
        names = sorted(files)
        out = bytearray(b'PAC ' + struct.pack('<II', 0, len(names)) + bytes(0x804 - 12))
        offset = 0x804 + 40 * len(names)
        for name in names:
            out += name.encode('cp932').ljust(32, b'\0') + struct.pack('<II', len(files[name]), offset)
            offset += len(files[name])
        for name in names:
            out += files[name]
        path.write_bytes(bytes(out) + b'\0\0\0\0EOF ')

    def script(self, voice_config=True):
        data = {'game': 'Voices', 'script_id': 'voices', 'rows': [
            {'source': 'main', 'id': '1', 'ja': '一', 'voice': 'VO04_0018'},
            {'source': 'main', 'id': '2', 'ja': '二', 'voice': 'VO09_9999'},
            {'source': 'main', 'id': '3', 'ja': '三'},
            {'source': 'main', 'id': '4', 'ja': '四', 'voice': 'VO05_0103+VO04_0018'}]}
        if voice_config:
            data['voice'] = {'archives': ['voice.pac']}
        self.library.import_script(data)
        return self.library.get('voices')

    def test_clip_is_read_from_the_game_archive_once_the_game_folder_is_known(self):
        script = self.script()
        self.assertEqual(script.row(1)['voice'], 'VO04_0018')
        self.assertNotIn('voice', script.row(3))
        self.assertTrue(script.info()['voice'])
        self.assertEqual(self.library.locate('voices::main|1')['voice'], 1)
        self.assertNotIn('voice', self.library.locate('voices::main|3'))
        with self.assertRaisesRegex(ValueError, '遊戲裝在哪裡'):
            script.voice(1)
        self.assertTrue(script.needs_game_dir())
        self.assertFalse(script.remember_game_dir(self.root))        # no voice.pac there: nothing saved
        self.assertTrue(script.remember_game_dir(self.game))
        self.assertFalse(script.needs_game_dir())
        self.assertEqual(json.loads((script.folder / 'voice.json').read_text(encoding='utf-8')), {'game_dir': str(self.game)})
        self.assertEqual(script.voice(1), (b'OggS-first', 'audio/ogg'))
        with self.assertRaisesRegex(ValueError, 'VO09_9999'):
            script.voice(2)
        with self.assertRaisesRegex(ValueError, '沒有語音'):
            script.voice(3)
        # a group line: several clips heard together
        self.assertEqual(self.library.locate('voices::main|4')['voice'], 2)
        self.assertEqual(script.voice(4, 0)[0], b'OggS-second')
        self.assertEqual(script.voice(4, 1)[0], b'OggS-first')
        with self.assertRaisesRegex(ValueError, 'No such voice clip'):
            script.voice(4, 2)

    def test_archive_changes_are_picked_up_and_folders_work_too(self):
        script = self.script()
        script.remember_game_dir(self.game)
        self.pac(self.game / 'voice.pac', {'VO04_0018.OGG': b'OggS-patched-and-longer'})
        self.assertEqual(script.voice(1)[0], b'OggS-patched-and-longer')
        loose = self.root / 'loose'
        loose.mkdir()
        (loose / 'VO09_9999.wav').write_bytes(b'RIFF')
        (script.folder / 'voice.json').write_text(json.dumps({'archives': [str(loose)], 'game_dir': str(self.game)}), encoding='utf-8')
        self.assertEqual(script.voice(2), (b'RIFF', 'audio/wav'))

    def test_voice_needs_a_script_wide_setting_and_a_safe_name(self):
        script = self.script(voice_config=False)
        self.assertNotIn('voice', script.row(1))
        self.assertFalse(script.info()['voice'])
        with self.assertRaisesRegex(ValueError, 'clip name'):
            self.library.import_script({'game': 'Bad', 'script_id': 'bad', 'rows': [{'ja': 'x', 'voice': '../../secret'}]})
        with self.assertRaisesRegex(ValueError, '檔名'):
            scripts.voice_clip([self.game / 'voice.pac'], '..\\VO04_0018')
