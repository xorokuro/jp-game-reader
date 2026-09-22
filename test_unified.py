"""Unified input regressions; all journals and servers are disposable."""
import json,os,socket,subprocess,sys,tempfile,time,unittest,urllib.request,urllib.error
from pathlib import Path
from unittest.mock import Mock
from journal import Journal,Recorder,Matcher
from capture_sources import select

class UnifiedReader(unittest.TestCase):
    def test_manual_retry_waits_for_stable_text(self):
        journal=Mock();journal.record.return_value={'id':1}
        recorder=Recorder(journal,Matcher([]))
        self.assertIsNone(recorder.sample('不完全','obs64',force=True))
        for _ in range(2):self.assertIsNone(recorder.sample('完全な文章です。','obs64',force=True))
        self.assertEqual(recorder.sample('完全な文章です。','obs64',force=True),{'id':1})
        journal.record.assert_called_once()
        self.assertIsNone(recorder.sample('完全な文章です。','obs64'))

    def test_window_target_must_still_exist(self):
        row={'handle':7,'pid':8,'title':'Game','process':'game.exe'}
        self.assertEqual(select({'mode':'window','handle':7,'pid':8},[row])['window_title'],'Game')
        for body in ({'mode':'bad'},{'mode':'window','handle':7,'pid':9},{'mode':'window','handle':1,'pid':8}):
            with self.assertRaises(ValueError):select(body,[row])
        self.assertEqual(select({'mode':'paste'},[])['window_handle'],0)

    def test_explicit_save_keeps_capture_temporary(self):
        with tempfile.TemporaryDirectory() as folder:
            journal=Journal(Path(folder)/'test.sqlite3');journal.save_text=False
            self.assertTrue(journal.record('仮の文章')['temporary'])
            saved=journal.record('保存する文章',save=True)
            self.assertGreater(saved['id'],0)
            self.assertFalse(journal.save_text)
            self.assertTrue(journal.record('次の仮の文章')['temporary'])

    def test_sources_and_paste_in_one_server(self):
        with tempfile.TemporaryDirectory() as folder:
            with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
            origin=f'http://127.0.0.1:{port}'
            def request(path,body=None,request_origin=None):
                req=urllib.request.Request(origin+'/api/'+path,data=None if body is None else json.dumps(body).encode(),headers={'Origin':request_origin or origin,'Content-Type':'application/json'})
                with urllib.request.urlopen(req,timeout=5) as response:return json.load(response)
            proc=subprocess.Popen([sys.executable,str(Path(__file__).parent/'journal.py'),'--port',str(port),'--database',str(Path(folder)/'test.sqlite3'),'--no-browser','--no-capture'],env=dict(os.environ,JP_READER_DATA=folder,JP_READER_DICTIONARY_INDEX=str(Path(folder)/'none.sqlite3')),stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
            try:
                for _ in range(100):
                    try:state=request('state');break
                    except OSError:
                        if proc.poll() is not None:self.fail(proc.stderr.read().decode())
                        time.sleep(.1)
                else:self.fail('Server did not start')
                self.assertFalse(state['capture_enabled'])
                temp=request('add',{'japanese':'これは仮の文章です。'})['row']
                self.assertTrue(temp['temporary'])
                self.assertEqual(request('sentences')['total'],0)
                saved=request('add',{'japanese':temp['japanese'],'save':True,'temporary_id':temp['id']})['row']
                self.assertGreater(saved['id'],0)
                self.assertFalse(request('state')['save_text'])
                request('capture-source',{'mode':'obs'})
                self.assertTrue(request('state')['capture_enabled'])
                self.assertTrue(request('state')['save_text'])
                self.assertTrue(request('state')['paused'])
                request('capture-source',{'mode':'paste'})
                self.assertFalse(request('state')['capture_enabled'])
                self.assertFalse(request('state')['save_text'])
                self.assertEqual(request('sentence?id='+str(saved['id']))['japanese'],temp['japanese'])
                for path,body in [('retry',{}),('capture-source',{'mode':'window','handle':0,'pid':0}),('add',{'japanese':'文章','save':'yes'})]:
                    with self.assertRaises(urllib.error.HTTPError):request(path,body)
                with self.assertRaises(urllib.error.HTTPError):request('add',{'japanese':'文章'},'http://example.invalid')
                self.assertEqual(request('sentences')['total'],1)
            finally:
                try:request('stop',{})
                except OSError:proc.terminate()
                _,errors=proc.communicate(timeout=15)
                self.assertEqual(proc.returncode,0,errors.decode())

if __name__=='__main__':unittest.main()
