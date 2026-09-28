import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock,patch
import translation_backends as engines


class Backends(unittest.TestCase):
    def test_selection_persists_without_lm_studio(self):
        with tempfile.TemporaryDirectory() as folder:
            argos=Mock(id='argos',label='Argos');argos.options.return_value={'id':'argos','available':True}
            lm=Mock(id='lm-studio');lm.options.return_value={'id':'lm-studio','available':False}
            with patch.object(engines,'CONFIG',Path(folder)/'selection.json'),patch.dict(engines.ENGINES,{'argos':argos,'lm-studio':lm},clear=True):
                self.assertEqual(engines.selected_id(),'argos')
                engines.select('argos','ja-en-zt')
                argos.select.assert_called_once_with('ja-en-zt')
                argos.options.return_value['available']=False
                self.assertEqual(engines.selected_id(),'argos','Do not silently change a saved provider')

    def test_busy_selection_and_unknown_engine_rejected(self):
        with self.assertRaises(ValueError):engines.select('unknown','anything')
        with engines.ENGINE_LOCK:
            with self.assertRaisesRegex(ValueError,'running'):engines.select('argos','ja-en-zt')

    def test_translation_is_routed_to_selected_engine(self):
        engine=Mock(label='Argos');engine.translate.return_value={'en-US':'Hello','zh-Hant':'你好'}
        with patch.object(engines,'selected',return_value=engine):
            label,result=engines.translate('こんにちは')
        engine.translate.assert_called_once_with('こんにちは')
        self.assertEqual((label,result['zh-Hant']),('Argos','你好'))

    def test_argos_reports_worker_failure(self):
        engine=engines.Argos()
        process=Mock(stdout='JP_READER_RESULT='+json.dumps({'error':'Missing model'}),returncode=1)
        with patch.object(engine,'ready'),patch.object(engines.subprocess,'run',return_value=process):
            with self.assertRaisesRegex(ValueError,'Missing model'):engine.translate('こんにちは')

    def test_argos_worker_receives_entire_block(self):
        engine=engines.Argos();text='日本語の本を読みます。\n'*200
        process=Mock(stdout='JP_READER_RESULT='+json.dumps({'en-US':'Books','zh-Hant':'書籍'}),returncode=0)
        with patch.object(engine,'ready'),patch.object(engines.subprocess,'run',return_value=process) as run:
            engine.translate(text)
        self.assertEqual(''.join(json.loads(run.call_args.kwargs['input'])['chunks']),text)
        self.assertNotIn('--prepare',run.call_args.args[0],'Reading must never trigger model downloads')


if __name__=='__main__':unittest.main()
