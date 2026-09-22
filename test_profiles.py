"""Smoke tests using temporary copies; never touch personal journals."""
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from launch import profile_folder


class Profiles(unittest.TestCase):
    def test_reject_unsafe_names(self):
        for name in ('../escape', '', 'CON', 'con', 'a/b', 'lpt1', 'two words'):
            with self.assertRaises(ValueError):
                profile_folder(name)
        self.assertEqual(profile_folder('my-vn').name, 'my-vn')

    def test_separate_games_and_resume(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for source in Path(__file__).parent.glob('*.py'):
                shutil.copy2(source, root/source.name)
            with socket.socket() as probe:
                probe.bind(('127.0.0.1', 0))
                port = probe.getsockname()[1]
            origin = f'http://127.0.0.1:{port}'

            def request(path, payload=None):
                data = None if payload is None else json.dumps(payload).encode()
                req = urllib.request.Request(origin+path, data=data, headers={'Origin':origin, 'Content-Type':'application/json'})
                with urllib.request.urlopen(req, timeout=3) as response:
                    return json.load(response)

            for game, expected in [('game-a', 0), ('game-b', 0), ('game-a', 1)]:
                proc = subprocess.Popen([sys.executable, str(root/'launch.py'), '--profile', game, '--port', str(port), '--no-browser', '--no-capture'], stdout=subprocess.PIPE, stderr=subprocess.PIPE,env=dict(os.environ,JP_READER_DICTIONARY_INDEX=str(root/'empty-index.sqlite3')))
                ready = False
                try:
                    for _ in range(100):
                        try:
                            request('/api/state'); ready = True; break
                        except (urllib.error.URLError, TimeoutError):
                            if proc.poll() is not None:
                                self.fail(str(proc.communicate()))
                            time.sleep(.1)
                    self.assertTrue(ready, 'Server did not start')
                    self.assertFalse(request('/api/state')['capture_enabled'])
                    self.assertFalse(request('/api/state')['save_text'])
                    temporary=request('/api/add', {'japanese':'一時的な文章です。'})
                    self.assertTrue(temporary['row']['temporary'])
                    self.assertEqual(request('/api/sentences')['total'], expected)
                    request('/api/save-text', {'enabled':True})
                    request('/api/translation', {'enabled':False})
                    self.assertEqual(request('/api/sentences')['total'], expected)
                    self.assertEqual(request('/api/dictionary/catalog'), {'dictionaries': []})
                    if expected == 0:
                        block='今日はいい天気ですね。\n図書館で本を読みます。'
                        saved=request('/api/add', {'japanese':block})
                        self.assertEqual(saved['row']['japanese'],block)
                        request('/api/preferences',{'fortune-dictionary-zoom':'120'})
                        self.assertEqual(request('/api/sentences')['total'], 1)
                        with self.assertRaises(urllib.error.HTTPError):request('/api/add',{'japanese':'あ'*12001})
                finally:
                    if ready:
                        request('/api/stop', {})
                    else:
                        proc.terminate()
                    proc.communicate(timeout=15)
                self.assertEqual(proc.returncode, 0)
            self.assertTrue((root/'data/game-a/sentences.sqlite3').exists())
            self.assertTrue((root/'data/game-b/sentences.sqlite3').exists())


if __name__ == '__main__':
    unittest.main()
