import tempfile
import unittest
import threading
from pathlib import Path
from unittest.mock import patch
from unittest.mock import Mock
import local_translate
import preferences
import mdict_library
import translation_backends


class Reader(unittest.TestCase):
    def test_translation_chunks_preserve_long_block(self):
        text=('今日はいい天気です。\n図書館で本を読みます。\n\n'*200)+'最後の一行。'
        chunks=local_translate.translation_chunks(text)
        self.assertGreater(len(chunks),1)
        self.assertEqual(''.join(chunks),text)
        self.assertTrue(all(len(c)<=1200 for c in chunks))
        with patch.object(local_translate,'translate_selected',side_effect=lambda s:{'en-US':'EN:'+s,'zh-Hant':'ZH:'+s}):
            output=local_translate.translate(text)
        self.assertEqual(output['en-US'],'\n\n'.join('EN:'+c for c in chunks))

    def test_no_ai_server_is_supported(self):
        with patch.object(local_translate.urllib.request,'urlopen',side_effect=OSError('No local model')):
            result=local_translate.models()
        self.assertFalse(result['available'])
        self.assertEqual(result['models'],[])

    def test_manual_translation_queues_with_loaded_model(self):
        journal=Mock();journal.get.return_value={'id':1}
        with patch.object(local_translate.threading,'Thread'):
            translator=local_translate.Translator(journal,threading.Event(),{},threading.RLock())
        with patch.object(translation_backends,'selected',return_value=translation_backends.LMStudio()),patch.object(local_translate,'models',return_value={'available':True,'selected':local_translate.MODEL,'models':[{'id':local_translate.MODEL,'state':'loaded'}]}):
            translator.request(1)
        self.assertEqual(list(translator.pending),[1])
        with patch.object(translation_backends,'selected',return_value=translation_backends.LMStudio()),patch.object(local_translate,'models',return_value={'available':False,'message':'No local AI','models':[]}):
            with self.assertRaisesRegex(ValueError,'No local AI'):translator.request(1)

    def test_preferences_move_with_folder(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'preferences.json'
            preferences.save(path,{'fortune-dictionary-zoom':'120'})
            self.assertIn(b'120',preferences.bootstrap(path))
            with self.assertRaises(ValueError):preferences.save(path,{'secret':'not a reader preference'})

    def test_relative_dictionary_paths(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(mdict_library,'INDEX',Path(folder)/'mdict-index.sqlite3'):
                self.assertEqual(mdict_library.source_path('sources/example.mdx'),Path(folder)/'sources/example.mdx')
                with self.assertRaises(ValueError):mdict_library.source_path('../outside.mdx')


if __name__=='__main__':unittest.main()
