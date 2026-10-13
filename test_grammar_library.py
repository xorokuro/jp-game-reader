import tempfile
import unittest
from pathlib import Path

import grammar_library as g


class GrammarLibraryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        base = Path(self.temp.name)
        self.app = base / 'reader'
        self.app.mkdir()
        self.root = base / 'JLPT文法'
        (self.root / 'lessons').mkdir(parents=True)
        (self.root / 'JLPT文法總目錄N5-N1.html').write_text('<html><head><title>目錄</title></head><body>index</body></html>', encoding='utf-8')
        (self.root / '修正前後對照_N1.html').write_text('<p>diff</p>', encoding='utf-8')
        (self.root / 'lessons' / 'manifest.js').write_text('LESSONS["N2|〜ものの"]="N2_ものの.html";', encoding='utf-8')
        (self.root / 'lessons' / 'N2_ものの.html').write_text(
            '<!doctype html><html><head><style>ruby rt{color:red}</style></head><body><ruby>有意<rt>ゆうい</rt></ruby></body></html>', encoding='utf-8')
        (self.root / 'lessons' / 'notes.zip').write_bytes(b'PK')
        self.secret = base / 'secret.txt'
        self.secret.write_text('private', encoding='utf-8')

    def tearDown(self):
        self.temp.cleanup()

    def configure(self, *lines):
        (self.app / g.ROOT_FILE).write_text('\n'.join(lines) + '\n', encoding='utf-8')

    def test_lessons_folder_opens_its_index(self):
        self.configure('# comment', '"' + str(self.root / 'lessons') + '"')
        found = g.collections(self.app, environ={})
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].root, self.root.resolve())
        self.assertTrue(found[0].home().endswith('.html'))
        raw, mime = g.serve('/grammar/0/', self.app, environ={})
        self.assertIn('text/html', mime)
        self.assertIn(b'index', raw)

    def test_lesson_pages_get_frame_tags_without_changing_files(self):
        self.configure(str(self.root))
        raw, _ = g.serve('/grammar/0/lessons/N2_ものの.html', self.app, environ={})
        self.assertIn(b'/grammar-frame.css', raw)
        self.assertLess(raw.index(b'<style>'), raw.index(b'/grammar-frame.js'))
        self.assertNotIn('grammar-frame', (self.root / 'lessons' / 'N2_ものの.html').read_text(encoding='utf-8'))
        script, mime = g.serve('/grammar/0/lessons/manifest.js', self.app, environ={})
        self.assertIn('javascript', mime)
        self.assertNotIn(b'grammar-frame', script)

    def test_nothing_outside_the_folder_or_of_other_types(self):
        self.configure(str(self.root))
        for path in ('/grammar/0/../secret.txt', '/grammar/0/lessons/../../secret.txt', '/grammar/0/lessons/notes.zip',
                     '/grammar/0/C:/Windows/win.ini', '/grammar/1/x.html', '/grammar/0/lessons\\..\\..\\secret.txt'):
            with self.assertRaises(LookupError, msg=path):
                g.serve(path, self.app, environ={})

    def test_folder_without_index_gets_a_listing(self):
        plain = Path(self.temp.name) / 'vocab'
        plain.mkdir()
        (plain / 'a.html').write_text('a', encoding='utf-8')
        (plain / 'b.html').write_text('b', encoding='utf-8')
        self.configure(str(plain))
        raw, _ = g.serve('/grammar/0/', self.app, environ={})
        self.assertIn(b'a.html', raw)
        self.assertIn(b'b.html', raw)

    def test_add_root_remembers_folder_once(self):
        added = g.add_root(str(self.root / 'lessons'), self.app)
        self.assertEqual(added.root, self.root.resolve())
        g.add_root(str(self.root), self.app)
        lines = [line for line in (self.app / g.ROOT_FILE).read_text(encoding='utf-8').splitlines() if line and not line.startswith('#')]
        self.assertEqual(lines, [str(self.root.resolve())])
        with self.assertRaises(ValueError):
            g.add_root(str(Path(self.temp.name) / 'missing'), self.app)
        with self.assertRaises(ValueError):
            g.add_root('relative/folder', self.app)

    def test_environment_and_drop_in_folder(self):
        drop = self.app / 'grammar' / 'mine'
        drop.mkdir(parents=True)
        (drop / 'index.html').write_text('x', encoding='utf-8')
        found = g.collections(self.app, environ={'JP_READER_GRAMMAR': str(self.root)})
        self.assertEqual([c.root for c in found], [self.root.resolve(), drop.resolve()])


if __name__ == '__main__':
    unittest.main()
