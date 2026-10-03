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
