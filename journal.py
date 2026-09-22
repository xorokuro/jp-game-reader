"""Persistent local Japanese sentence journal. Standard-library only."""
import local_dictionary
import argparse,collections,difflib,json,re,socket,sqlite3,subprocess,threading,time,unicodedata,webbrowser
from contextlib import contextmanager,closing
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib.parse import urlparse,parse_qs
HERE=Path(__file__).resolve().parent
DATA=HERE/'saved_sentences'
def visible_text(text):
    text=re.sub(r'<br\s*/?>', '\n', text, flags=re.I)
    # Dictionary highlights and ruby-reading controls are not dialogue text.
    return re.sub(r'</?(?:d\d*|r[^<>]*)>', '', text, flags=re.I)

def norm(text):
    text=visible_text(text)
    return ''.join(c for c in unicodedata.normalize('NFKC',text) if c.isalnum())
def sentence_key(text):
    lines=visible_text(text).splitlines()
    lines=[line for line in lines if re.search('[\u3040-\u30ff\u3400-\u9fff]',line)]
    return norm(''.join(lines))

class Journal:
    def __init__(self,path):
        self.save_text=True;self.temporary={};self.temporary_id=0
        self.path=path
        self.export_lock=threading.Lock()
        self.export_pending=threading.Event();self.export_stop=threading.Event();self.export_error='';self.exported_at=None
        with self.connect() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS sentences(id INTEGER PRIMARY KEY, game TEXT NOT NULL, identity TEXT NOT NULL, japanese TEXT NOT NULL, original TEXT NOT NULL, source_id TEXT, confidence REAL, kind TEXT NOT NULL, first_seen TEXT NOT NULL, last_seen TEXT NOT NULL, encounters INTEGER NOT NULL DEFAULT 1, note TEXT NOT NULL DEFAULT '', starred INTEGER NOT NULL DEFAULT 0, studied INTEGER NOT NULL DEFAULT 0, UNIQUE(game,identity))''')
            columns={r['name'] for r in db.execute('PRAGMA table_info(sentences)')}
            for field in ('english','traditional_chinese'):
                if field not in columns:db.execute(f"ALTER TABLE sentences ADD COLUMN {field} TEXT NOT NULL DEFAULT ''")
            if 'duplicate_of' not in columns:db.execute('ALTER TABLE sentences ADD COLUMN duplicate_of INTEGER')
            if 'deleted' not in columns:db.execute('ALTER TABLE sentences ADD COLUMN deleted INTEGER NOT NULL DEFAULT 0')
            if 'match_key' not in columns:
                db.execute("ALTER TABLE sentences ADD COLUMN match_key TEXT NOT NULL DEFAULT ''")
                db.executemany('UPDATE sentences SET match_key=? WHERE id=?',[(sentence_key(r['japanese']),r['id']) for r in db.execute('SELECT id,japanese FROM sentences')])
            db.execute('CREATE INDEX IF NOT EXISTS sentence_match ON sentences(game,match_key)')
            db.execute('CREATE INDEX IF NOT EXISTS sentence_source ON sentences(game,source_id)')
            db.execute('CREATE INDEX IF NOT EXISTS sentence_visible ON sentences(duplicate_of,id)')
            db.execute('CREATE TABLE IF NOT EXISTS encounters(seq INTEGER PRIMARY KEY, sentence_id INTEGER NOT NULL, seen_at TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS pending_ocr(id INTEGER PRIMARY KEY, identity TEXT UNIQUE NOT NULL, text TEXT NOT NULL, created TEXT NOT NULL)')
            if not db.execute('SELECT 1 FROM encounters LIMIT 1').fetchone():
                db.execute('INSERT INTO encounters(sentence_id,seen_at) SELECT id,last_seen FROM sentences WHERE duplicate_of IS NULL AND deleted=0 ORDER BY last_seen,id')

    @contextmanager
    def connect(self):
        db=sqlite3.connect(self.path,timeout=15);db.row_factory=sqlite3.Row
        try:
            with db:yield db
        finally:db.close()
    def reconcile(self):
        # Keep duplicate records on disk; only consolidate the normal reader view.
        with self.connect() as db:
            groups={}
            for row in db.execute('SELECT * FROM sentences WHERE duplicate_of IS NULL AND deleted=0 ORDER BY id').fetchall():
                key=(row['game'],sentence_key(row['japanese']))
                prior=groups.get(key)
                if prior is None:groups[key]=dict(row);continue
                if any(prior[f] and row[f] and prior[f]!=row[f] for f in ('english','traditional_chinese','note')):continue
                for f in ('english','traditional_chinese','note'):
                    if not prior[f] and row[f]:
                        db.execute(f'UPDATE sentences SET {f}=? WHERE id=?',(row[f],prior['id']));prior[f]=row[f]
                db.execute('UPDATE sentences SET duplicate_of=? WHERE id=?',(prior['id'],row['id']))
    def get(self,rowid):
        if rowid<0:return self.temporary.get(rowid)
        with self.connect() as db:
            r=db.execute('SELECT * FROM sentences WHERE id=?',(rowid,)).fetchone()
            if r and r['duplicate_of']:r=db.execute('SELECT * FROM sentences WHERE id=?',(r['duplicate_of'],)).fetchone()
            return dict(r) if r and not r['deleted'] else None
    def known_ocr(self,text):
        with self.connect() as db:
            r=db.execute('SELECT id FROM sentences WHERE game=? AND deleted=0 AND (identity=? OR match_key=?) ORDER BY id LIMIT 1',('obs64',norm(text),sentence_key(text))).fetchone()
            return r is not None
    def propose(self,text):
        with self.connect() as db:
            if db.execute('SELECT 1 FROM sentences WHERE deleted=1 AND identity=?',(norm(text),)).fetchone():return
            db.execute('INSERT OR IGNORE INTO pending_ocr(identity,text,created) VALUES(?,?,?)',(norm(text),text,time.strftime('%Y-%m-%d %H:%M:%S')))
    def pending(self):
        with self.connect() as db:
            return {'count':db.execute('SELECT COUNT(*) FROM pending_ocr').fetchone()[0],'rows':[dict(r) for r in db.execute('SELECT * FROM pending_ocr ORDER BY id LIMIT 5')]}
    def decide(self,token,keep,correction=None,edited=None):
        with self.connect() as db:r=db.execute('SELECT * FROM pending_ocr WHERE id=?',(token,)).fetchone()
        if not r:raise ValueError('這筆待確認文字已處理，請重新整理。')
        if edited is not None and (not isinstance(edited,str) or not norm(edited)):raise ValueError('請輸入日文台詞。')
        saved=self.record(edited.strip(),kind='manual',raw=r['text']) if keep and edited is not None else self.record(correction['text'],source_id=correction['id'],kind='manual',raw=r['text']) if correction else self.record(r['text'],kind='manual' if keep else 'ocr',discard_new=not keep)
        with self.connect() as db:db.execute('DELETE FROM pending_ocr WHERE id=?',(token,))
        return saved if keep else None
    def record(self,text,game='obs64',source_id=None,confidence=0,kind='ocr',raw=None,discard_new=False,save=None):
        if not norm(text):raise ValueError('Enter a sentence first.')
        if not (self.save_text if save is None else save):
            self.temporary_id-=1
            row=dict(id=self.temporary_id,japanese=text,original=raw or text,kind=kind,game=game,source_id=source_id,confidence=confidence,english='',traditional_chinese='',note='',starred=0,studied=0,encounters=1,first_seen='',last_seen='',temporary=True)
            self.temporary[row['id']]=row
            if len(self.temporary)>100:self.temporary.pop(next(iter(self.temporary)))
            return row
        stamp=time.strftime('%Y-%m-%d %H:%M:%S');key=sentence_key(text)
        with self.connect() as db:
            # Serialize lookup and insert, including across recorder processes.
            db.execute('BEGIN IMMEDIATE')
            previous=db.execute('SELECT * FROM sentences WHERE game=? AND source_id=? AND duplicate_of IS NULL ORDER BY id LIMIT 1',(game,source_id)).fetchone() if source_id else None
            if previous is None:
                previous=db.execute('SELECT * FROM sentences WHERE game=? AND match_key=? AND duplicate_of IS NULL ORDER BY id LIMIT 1',(game,key)).fetchone()
            if previous is None:
                previous=db.execute('SELECT * FROM sentences WHERE game=? AND identity=?',(game,norm(text))).fetchone()
                visited=set()
                while previous and previous['duplicate_of'] and previous['id'] not in visited:
                    visited.add(previous['id'])
                    parent=db.execute('SELECT * FROM sentences WHERE id=? AND game=?',(previous['duplicate_of'],game)).fetchone()
                    if parent is None:break
                    previous=parent
            if previous and discard_new:return None
            if previous:
                rowid=previous['id']
                db.execute('UPDATE sentences SET deleted=0 WHERE id=?',(rowid,))
                db.execute('UPDATE sentences SET last_seen=?,encounters=encounters+1 WHERE id=?',(stamp,rowid))
                if source_id and not previous['source_id']:
                    db.execute('UPDATE sentences SET source_id=?,confidence=?,kind=? WHERE id=?',(source_id,confidence,kind,rowid))
            else:
                cur=db.execute('INSERT INTO sentences(game,identity,japanese,original,source_id,confidence,kind,first_seen,last_seen) VALUES(?,?,?,?,?,?,?,?,?)',(game,norm(text),text,raw or text,source_id,confidence,kind,stamp,stamp));rowid=cur.lastrowid
            db.execute('UPDATE sentences SET match_key=? WHERE id=?',(sentence_key(db.execute('SELECT japanese FROM sentences WHERE id=?',(rowid,)).fetchone()[0]),rowid))
            if discard_new:
                db.execute('UPDATE sentences SET deleted=1 WHERE id=?',(rowid,))
                self.export_pending.set()
                return None
            recent=db.execute('SELECT sentence_id FROM encounters ORDER BY seq DESC LIMIT 1').fetchone()
            if not recent or recent[0]!=rowid:db.execute('INSERT INTO encounters(sentence_id,seen_at) VALUES(?,?)',(rowid,stamp))
            row=dict(db.execute('SELECT * FROM sentences WHERE id=?',(rowid,)).fetchone())
        self.export_pending.set()
        return row
    def snapshot(self):
        with self.export_lock:
            self.export_pending.clear()
            folder=Path(self.path).parent
            try:
                with self.connect() as db, (folder/'sentences.json.tmp').open('w',encoding='utf8') as js, (folder/'sentences.txt.tmp').open('w',encoding='utf8') as txt:
                    js.write('[\n');first=True
                    for row in db.execute('SELECT * FROM sentences WHERE duplicate_of IS NULL AND deleted=0 ORDER BY id'):
                        r=dict(row)
                        if not first:js.write(',\n');txt.write('\n\n')
                        js.write(json.dumps(r,ensure_ascii=False))
                        txt.write(f"#{r['id']} | {r['first_seen']} | {r['kind']}\n{r['japanese']}"+(f"\nEnglish: {r['english']}" if r['english'] else '')+(f"\nTraditional Chinese: {r['traditional_chinese']}" if r['traditional_chinese'] else '')+(f"\nNotes: {r['note']}" if r['note'] else ''))
                        first=False
                    js.write('\n]')
                for name in ('sentences.json','sentences.txt'):(folder/(name+'.tmp')).replace(folder/name)
                self.export_error='';self.exported_at=time.strftime('%Y-%m-%d %H:%M:%S')
            except Exception as e:
                self.export_pending.set();self.export_error=str(e);raise
    def start_exports(self):
        def run():
            while not self.export_stop.wait(30):
                if self.export_pending.is_set():
                    try:self.snapshot()
                    except Exception:pass
        self.export_thread=threading.Thread(target=run,daemon=True);self.export_thread.start()
    def close_exports(self):
        self.export_stop.set()
        if hasattr(self,'export_thread'):self.export_thread.join()
        if self.export_pending.is_set():self.snapshot()
    def page(self,q='',filter='all',order='newest',page=0):
        conditions=['duplicate_of IS NULL', 'deleted=0'];params=[]
        if q:
            conditions.append("instr(lower(japanese||' '||note||' '||english||' '||traditional_chinese),lower(?))>0");params.append(q)
        if filter=='new':conditions.append('studied=0')
        elif filter=='star':conditions.append('starred=1')
        elif filter=='ocr':conditions.append("kind='ocr'")
        where=' AND '.join(conditions)
        with self.connect() as db:
            total=db.execute('SELECT COUNT(*) FROM sentences WHERE duplicate_of IS NULL AND deleted=0').fetchone()[0]
            count=db.execute('SELECT COUNT(*) FROM sentences WHERE '+where,params).fetchone()[0]
            page=max(0,min(page,max(0,(count-1)//20)))
            direction='ASC' if order=='oldest' else 'DESC'
            rows=[dict(r) for r in db.execute('SELECT * FROM sentences WHERE '+where+' ORDER BY id '+direction+' LIMIT 20 OFFSET ?',params+[page*20])]
        return {'rows':rows,'total':total,'count':count,'page':page}
    def recent(self):
        with self.connect() as db:
            return [dict(r) for r in db.execute('SELECT e.seq,e.seen_at,s.id,s.japanese FROM encounters e JOIN sentences s ON s.id=e.sentence_id WHERE s.deleted=0 AND s.duplicate_of IS NULL ORDER BY e.seq DESC LIMIT 30')]
    def navigate(self,seq,direction):
        with self.connect() as db:
            if direction=='previous':r=db.execute('SELECT * FROM encounters WHERE sentence_id IN (SELECT id FROM sentences WHERE deleted=0 AND duplicate_of IS NULL) AND seq<? ORDER BY seq DESC LIMIT 1',(seq,)).fetchone()
            elif direction=='next':r=db.execute('SELECT * FROM encounters WHERE sentence_id IN (SELECT id FROM sentences WHERE deleted=0 AND duplicate_of IS NULL) AND seq>? ORDER BY seq LIMIT 1',(seq,)).fetchone()
            else:r=db.execute('SELECT * FROM encounters WHERE sentence_id IN (SELECT id FROM sentences WHERE deleted=0 AND duplicate_of IS NULL) AND seq=?',(seq,)).fetchone()
        return {'seq':r['seq'],'row':self.get(r['sentence_id'])} if r else None
    def rows(self):
        with self.connect() as db:return [dict(r) for r in db.execute('SELECT * FROM sentences WHERE duplicate_of IS NULL AND deleted=0 ORDER BY id DESC')]
    def set_deleted(self,rowid,deleted):
        with self.connect() as db:
            row=db.execute('SELECT id FROM sentences WHERE id=? AND duplicate_of IS NULL',(rowid,)).fetchone()
            if not row:raise ValueError('Sentence not found.')
            db.execute('UPDATE sentences SET deleted=? WHERE id=?',(int(deleted),rowid))
        self.export_pending.set()
    def edit(self,item):
        if int(item['id'])<0:
            row=self.temporary.get(int(item['id']))
            if row is None:raise ValueError('Temporary text is no longer available.')
            for key in ('japanese','english','traditional_chinese','note','starred','studied'):
                if key in item:row[key]=item[key]
            return
        with self.connect() as db:
            old=db.execute('SELECT * FROM sentences WHERE id=?',(int(item['id']),)).fetchone()
            if not old:raise ValueError('Sentence not found.')
            text=item.get('japanese',old['japanese']).strip()
            if not text:raise ValueError('The sentence cannot be empty.')
            db.execute('UPDATE sentences SET japanese=?,note=?,starred=?,studied=? WHERE id=?',(text,str(item.get('note',old['note'])),int(bool(item.get('starred',old['starred']))),int(bool(item.get('studied',old['studied']))),old['id']))
            db.execute('UPDATE sentences SET match_key=? WHERE id=?',(sentence_key(text),old['id']))
            for field in ('english','traditional_chinese'):
                if field in item:
                    if not isinstance(item[field],str):raise ValueError('Translation must be text.')
                    db.execute(f'UPDATE sentences SET {field}=? WHERE id=?',(item[field],old['id']))
        self.export_pending.set()
    def backup(self):
        dest=Path(self.path).parent/'backups';dest.mkdir(exist_ok=True)
        path=dest/(time.strftime('journal-%Y%m%d-%H%M%S')+'.sqlite3')
        with self.connect() as source,closing(sqlite3.connect(path)) as target:source.backup(target)
        return path.name
class Matcher:
    kana_sizes=str.maketrans('ぁぃぅぇぉゃゅょっゎァィゥェォャュョッヮ', 'あいうえおやゆよつわアイウエオヤユヨツワ')
    def __init__(self,rows):
        self.items={};self.index=collections.defaultdict(set);self.short_kana=collections.defaultdict(set)
        for r in rows:
            text=visible_text(r.get('japanese',r.get('ja','')));n=norm(text).casefold()
            if len(n)<6 and not (len(n)>=2 and (text.lstrip().startswith(('「','『')) or text.rstrip().endswith(('。','！','？','!','?')))):continue
            self.items.setdefault(n,{'text':text,'id':r.get('id','')})
        for n in self.items:
            if 2<=len(n)<6:self.short_kana[n.translate(self.kana_sizes)].add(n)
            for i in range(len(n)-1):self.index[n[i:i+2]].add(n)
    def suggest(self,raw):
        # Incomplete quotes are allowed for user-reviewed suggestions, never auto-matches.
        raw=re.sub(r'([」』])[^\n]*$',r'\1',raw)
        q=norm(raw).casefold()
        if not 2<=len(q)<6:return []
        folded=q.translate(self.kana_sizes)
        candidates=set(self.short_kana.get(folded,set()))
        # OCR can lose a tiny leading/trailing kana entirely (「……っ、くそ！」).
        # Offer these for review rather than silently inserting missing dialogue.
        for n in self.items:
            if len(n)!=len(q)+1 or len(n)>5:continue
            for i,c in enumerate(n):
                if c in 'ぁぃぅぇぉゃゅょっゎァィゥェォャュョッヮ' and (n[:i]+n[i+1:]).translate(self.kana_sizes)==folded:
                    candidates.add(n);break
        return [self.items[n] for n in sorted(candidates,key=lambda n:(len(n)!=len(q),n))][:5]

    def match(self,raw):
        # The animated advance indicator after a closing quote is not dialogue.
        raw=re.sub(r'([」』])[^\n]*$',r'\1',raw)
        lines=[x for x in raw.splitlines() if norm(x)];queries=[norm(''.join(lines[i:j])).casefold() for i in range(len(lines)) for j in range(i+1,min(len(lines),i+4)+1)]
        best={};coverage={}
        for q in queries:
            if q in self.items:
                if len(q)>=6 or re.search('[「」『』。！？!?]',raw):
                    best[q]=1.;coverage[q]=len(q)
                continue
            if len(q)<6:
                # Only correct kana size in a complete quoted short utterance.
                # General fuzzy matching is too permissive for such short text.
                if q==norm(raw).casefold() and re.fullmatch(r'\s*[「『].*[」』]\s*',raw,re.S):
                    candidates=self.short_kana.get(q.translate(self.kana_sizes),set())
                    if len(candidates)==1:
                        n=next(iter(candidates));best[n]=.97;coverage[n]=len(q)
                continue
            votes=collections.Counter()
            for g in set(q[i:i+2] for i in range(len(q)-1)):votes.update(self.index.get(g,()))
            for n,_ in votes.most_common(15):
                if min(len(n),len(q))/max(len(n),len(q))<.82:continue
                score=difflib.SequenceMatcher(None,q,n,autojunk=False).ratio()
                # Windows OCR often drops a dakuten mark (げ -> け).
                unvoiced=lambda t: ''.join(c for c in unicodedata.normalize('NFD',t.translate(self.kana_sizes)) if c not in '\u3099\u309a')
                if unvoiced(q)==unvoiced(n):score=max(score,.97)
                elif score>=.85:
                    # A dropped dakuten may occur together with a missing long-vowel mark.
                    score=max(score,.97*difflib.SequenceMatcher(None,unvoiced(q),unvoiced(n),autojunk=False).ratio())
                if score>=.92:
                    # Prefer a reliable match covering more of the captured dialogue.
                    # A standalone first line can also exist in the corpus.
                    if len(q)>coverage.get(n,0):best[n]=score;coverage[n]=len(q)
                    elif len(q)==coverage.get(n,0):best[n]=max(score,best.get(n,0))
        ranked=sorted(best,key=lambda n:(coverage[n],best[n]),reverse=True)
        if not ranked:return None
        n=ranked[0];score=best[n]
        if score<.92:return None
        if score<1 and len(ranked)>1 and coverage[ranked[1]]==coverage[n] and best[ranked[1]]>score-.05:return None
        return {**self.items[n],'confidence':score}
class Recorder:
    def __init__(self,journal,matcher):
        self.journal=journal;self.matcher=matcher;self.candidate='';self.repeats=0;self.last='';self.ignored=False;self.last_sample_at=0
    def sample(self,raw,game,force=False):
        if not norm(raw):
            if time.monotonic()-self.last_sample_at>3:self.candidate='';self.repeats=0;self.last='';self.ignored=False
            return None
        self.last_sample_at=time.monotonic()
        match=self.matcher.match(raw)
        text=match['text'] if match else re.sub(r'(?<=[\u3040-\u30ff\u3400-\u9fff]) +| +(?=[\u3040-\u30ff\u3400-\u9fff])', '', raw.strip())
        identity=norm(text)
        if not identity or not re.search('[\u3040-\u30ff\u3400-\u9fff]',text):return None
        if identity!=self.candidate:self.ignored=False
        self.repeats=self.repeats+1 if identity==self.candidate else 1;self.candidate=identity
        # Manual retries bypass duplicate suppression, never the stability check.
        required=3 if not match else 2
        if self.repeats<required or (not force and identity==self.last):return None
        result=self.journal.record(text,game,match['id'] if match else None,match['confidence'] if match else 0,'corpus' if match else 'ocr',raw)
        self.ignored=result is None
        self.last=identity
        return result
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--port',type=int,default=18744);ap.add_argument('--no-browser',action='store_true');ap.add_argument('--no-capture',action='store_true');ap.add_argument('--database',default=str(DATA/'sentences.sqlite3'));args=ap.parse_args()
    Path(args.database).parent.mkdir(parents=True,exist_ok=True)
    journal=Journal(args.database)
    journal.save_text=False
    journal.backup()
    journal.reconcile()
    journal.snapshot()
    preferences_path=Path(args.database).parent/'preferences.json'
    config_path=Path(args.database).parent/'settings.json';settings={'process':'obs64','crop_top':.55,'crop_height':.43}
    if config_path.exists():settings.update(json.loads(config_path.read_text(encoding='utf-8')))
    settings.setdefault('capture_mode','obs' if not args.no_capture else 'paste')
    if args.no_capture:settings['capture_mode']='paste'
    corpus=[] # This game has no supplied extracted script.
    matcher=Matcher(corpus);recorder=Recorder(journal,matcher)
    state={'status':'Starting recorder','paused':True,'raw':'','last':journal.get(journal.recent()[0]['id']) if journal.recent() else None,'version':0,'retry':{'pending':False,'message':''}};lock=threading.RLock();stop=threading.Event();restart=threading.Event();worker=[None]
    origin=f'http://127.0.0.1:{args.port}'
    import deepl_web
    web_queue=deepl_web.Queue(journal)

    def capture():
        while not stop.is_set():
            restart.clear()
            with lock:
                cfg=dict(settings)
                full_frame=bool(state['retry']['pending'] and state['retry'].get('full_frame'))
                if full_frame:cfg.update(crop_top=0,crop_height=1)
                should_capture=settings['capture_mode']!='paste' and (not state['paused'] or state['retry']['pending'])
                if not should_capture:state['status']='Paste Japanese to read and look up words.' if settings['capture_mode']=='paste' else '手動辨識：等待按下辨識按鈕。'
            if not should_capture:
                restart.wait(.5)
                continue
            cmd=['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(HERE/'ocr.ps1'),'-ProcessName',cfg['process'],'-CropTop',str(cfg['crop_top']),'-CropHeight',str(cfg['crop_height'])]
            cmd+=['-CaptureMode',cfg['capture_mode'],'-WindowHandle',str(cfg.get('window_handle',0)),'-WindowProcessId',str(cfg.get('window_pid',0))]
            try:
                proc=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace',creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0));worker[0]=proc
                for line in proc.stdout:
                    if stop.is_set() or restart.is_set():break
                    try:sample=json.loads(line)
                    except ValueError:
                        with lock:state['status']='OCR startup/error: '+line.strip()[:250]
                        continue
                    with lock:
                        if restart.is_set():break
                        state.update(status=sample.get('status','Reading'),raw=sample.get('text',''))
                        retry=state['retry']
                        forced=retry['pending']
                        if forced and time.monotonic()>retry['deadline']:
                            retry.update(pending=False,message=('讀到文字，但未能確認原文。請在待確認區保留或標記雜訊。' if state['retry'].get('text') else '未能讀到文字。請把遊戲切到前景、停在台詞畫面，再按一次。'))
                            forced=False
                        if (full_frame or state['paused']) and not forced:
                            restart.set()
                            break
                        if not state['paused'] or forced:
                            try:result=recorder.sample(sample.get('text',''),cfg['process'],force=forced)
                            except (sqlite3.Error,OSError) as e:
                                state['status']='Save failed; retrying next observation: '+str(e)
                                continue
                            if forced and re.search('[\u3040-\u30ff\u3400-\u9fff]',sample.get('text','')):
                                retry.update(pending=not bool(result or recorder.ignored),result_id=result['id'] if result else None,text=sample['text'],message=(('已辨識（暫存，不儲存）' if result.get('temporary') else '已重新辨識並儲存 #'+str(result['id'])) if result else '已略過這筆雜訊。' if recorder.ignored else '已讀到文字，正在重新確認原文；請保持遊戲台詞不動。'))
                            if result:state.update(last=result,version=state['version']+1)
                            elif recorder.ignored:state['status']='已略過這筆雜訊。'
                        if (full_frame or state['paused']) and not retry['pending']:
                            recorder.candidate='';recorder.repeats=0
                            restart.set()
                            break
                if proc.poll() is None:proc.terminate()
                proc.wait(timeout=5)
            except Exception as e:
                with lock:state['status']='Recorder error: '+str(e)
            finally:
                if worker[0] and worker[0].poll() is None:
                    worker[0].terminate()
                    worker[0].wait(timeout=5)
            if not restart.is_set():
                with lock:state['status']='OCR stopped. '+state['status']
                break
    class Handler(BaseHTTPRequestHandler):
        def send(self,obj,status=200,mime='application/json; charset=utf-8'):
            raw=obj if isinstance(obj,bytes) else json.dumps(obj,ensure_ascii=False).encode('utf-8');self.send_response(status);self.send_header('Content-Type',mime);self.send_header('Content-Length',str(len(raw)));self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.send_header('Content-Security-Policy',"default-src 'none'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; media-src 'self'; frame-ancestors 'self'" if self.path.startswith(('/api/dictionary/entry','/api/dictionary/resolve')) else "frame-ancestors 'self'");self.end_headers();self.wfile.write(raw)
        def allowed(self):return self.headers.get('Host')==f'127.0.0.1:{args.port}'
        def do_GET(self):
            if not self.allowed():return self.send({'error':'Invalid host'},403)
            p=urlparse(self.path).path
            if p=='/portable-preferences.js':
                import preferences
                return self.send(preferences.bootstrap(preferences_path),mime='text/javascript; charset=utf-8')
            if p=='/api/state':
                with lock:
                    if state['retry']['pending'] and time.monotonic()>state['retry']['deadline']:
                        state['retry'].update(pending=False,message=('讀到文字，但未能確認原文。請在待確認區保留或標記雜訊。' if state['retry'].get('text') else '未能讀到文字。請把遊戲切到前景、停在台詞畫面，再按一次。'))
                    current=journal.get(state['last']['id']) if state['last'] else None
                    if current is None:
                        recent=journal.recent();current=journal.get(recent[0]['id']) if recent else None
                    pending=journal.pending()
                    for item in pending['rows']:item['suggestions']=matcher.suggest(item['text'])
                    return self.send({**state,'workspace':str(Path(args.database).parent.resolve()),'save_text':journal.save_text,'capture_enabled':settings['capture_mode']!='paste','last':current,'settings':settings,'translation_fields':True,'pending_ocr':pending,'recent':journal.recent(),'exports':{'pending':journal.export_pending.is_set(),'updated_at':journal.exported_at,'error':journal.export_error}})
            query=parse_qs(urlparse(self.path).query)
            try:
                if p=='/api/capture-sources':
                    import capture_sources
                    return self.send({'windows':capture_sources.windows()})
                if p=='/api/translation-options':
                    import translation_backends
                    return self.send(translation_backends.catalog())
                if p=='/api/local-models':
                    import local_translate
                    return self.send(local_translate.models())
                if p=='/api/dictionary/catalog':
                    return self.send({'dictionaries':local_dictionary.catalog()})
                if p=='/api/dictionary/resolve':
                    raw=local_dictionary.mdict_library.entry(query['code'][0],word=query['word'][0])
                    return self.send(raw,mime='text/html; charset=utf-8')
                if p=='/api/dictionary/entry':
                    raw=local_dictionary.entry(query['code'][0],int(query['id'][0]),query.get('anchor',[''])[0])
                    return self.send(raw,mime='text/html; charset=utf-8')
                if p=='/api/dictionary/media':
                    raw,mime=local_dictionary.media(query['code'][0],query['name'][0])
                    return self.send(raw,mime=mime)
                if p=='/api/batch-lines':
                    after=max(0,int(query.get('after',['0'])[0]));until=int(query.get('until',['9223372036854775807'])[0])
                    with journal.connect() as db:
                        head=db.execute('SELECT COALESCE(MAX(seq),0) FROM encounters').fetchone()[0]
                        events=[dict(r) for r in db.execute('SELECT e.seq,s.* FROM encounters e JOIN sentences s ON s.id=e.sentence_id WHERE e.seq>? AND e.seq<=? AND s.deleted=0 AND s.duplicate_of IS NULL ORDER BY e.seq LIMIT 500',(after,until))]
                    return self.send({'head':head,'rows':events})
                if p=='/api/sentences':return self.send(journal.page(query.get('q',[''])[0],query.get('filter',['all'])[0],query.get('order',['newest'])[0],int(query.get('page',['0'])[0])))
                if p=='/api/sentence':return self.send(journal.get(int(query['id'][0])))
                if p=='/api/navigate':return self.send(journal.navigate(int(query['seq'][0]),query.get('direction',['at'])[0]))
                if p=='/api/export':
                    journal.snapshot()
                    name='sentences.txt' if query.get('format',['json'])[0]=='txt' else 'sentences.json'
                    with journal.export_lock, (Path(journal.path).parent/name).open('rb') as stream:
                        self.send_response(200);self.send_header('Content-Type','application/octet-stream');self.send_header('Content-Disposition','attachment; filename="'+name+'"');self.end_headers()
                        while chunk:=stream.read(65536):self.wfile.write(chunk)
                    return
            except (ValueError,KeyError) as e:return self.send({'error':str(e)},400)
            if p in ['/','/index.html','/app.js','/translations.js','/style.css','/dictionary.js','/dictionary.css','/dictionary-entry.css','/deepl-web.js','/reader.js']:
                name='index.html' if p=='/' else p[1:];mime={'html':'text/html','js':'text/javascript','css':'text/css'}[name.rsplit('.',1)[1]]
                return self.send((HERE/name).read_bytes(),mime=mime+'; charset=utf-8')
            self.send({'error':'Not found'},404)
        def do_POST(self):
            if not self.allowed() or self.headers.get('Origin')!=origin:return self.send({'error':'Local requests only'},403)
            try:
                length=int(self.headers.get('Content-Length','0'))
                if length>1000000:raise ValueError('Request too large')
                body=json.loads(self.rfile.read(length) or b'{}')
                if self.path=='/api/preferences':
                    import preferences
                    with lock:preferences.save(preferences_path,body)
                    return self.send({'ok':True})
                elif self.path=='/api/capture-source':
                    import capture_sources
                    selected=capture_sources.select(body)
                    with lock:
                        settings.update(selected)
                        config_path.write_text(json.dumps(settings,indent=2),encoding='utf-8')
                        state['paused']=True;state['retry']={'pending':False,'message':''};state['raw']=''
                        recorder.candidate='';recorder.last='';recorder.repeats=0
                        restart.set()
                        if worker[0] and worker[0].poll() is None:worker[0].terminate()
                    return self.send({'ok':True,'settings':settings})
                elif self.path=='/api/save-text':
                    if not isinstance(body.get('enabled'),bool):raise ValueError('Expected enabled true or false.')
                    with lock:journal.save_text=body['enabled']
                    return self.send({'enabled':journal.save_text})
                elif self.path=='/api/translation':
                    with lock:
                        state['translation']['enabled']=bool(body['enabled'])
                        settings['auto_translate']=state['translation']['enabled']
                        config_path.write_text(json.dumps(settings,indent=2),encoding='utf-8')
                        state['translation']['status']='Enabled' if body['enabled'] else 'Automatic translation paused'
                    return self.send({'ok':True})
                elif self.path=='/api/translation-engine':
                    import translation_backends
                    result=translation_backends.select(body.get('engine'),body.get('model'))
                    with lock:
                        state['translation']['provider']=translation_backends.selected().label
                        state['translation']['status']='Ready: '+translation_backends.selected().label
                    return self.send(result)
                elif self.path=='/api/local-model':
                    import local_translate
                    import translation_backends
                    translation_backends.select('lm-studio',body.get('model'))
                    result=local_translate.models()
                    with lock:
                        state['translation']['provider']=translation_backends.selected().label
                        state['translation']['status']='Model loaded: '+local_translate.MODEL
                    return self.send(result)
                elif self.path=='/api/local-translate':
                    local_translator.request(body.get('id'))
                    return self.send({'ok':True})
                elif self.path=='/api/deepl-web/claim':
                    return self.send({'error':'Translation now uses local LM Studio. Refresh the reader.'},409)
                elif self.path=='/api/deepl-web/result':
                    return self.send({'error':'DeepL is no longer active. Refresh the reader.'},409)
                elif self.path=='/api/deepl-key':
                    import auto_translate
                    auto_translate.save_key(body.get('key'))
                    with lock:state['translation']['status']='DeepL key saved. Translation will start automatically when enabled.'
                    return self.send({'ok':True})
                elif self.path=='/api/dictionary/search':
                    return self.send(local_dictionary.search(str(body.get('word','')),body.get('codes')))
                elif self.path=='/api/retry':
                    with lock:
                        if settings['capture_mode']=='paste':raise ValueError('Choose OBS or a game window before recognizing.')
                        if not state['retry']['pending']:
                            full_frame=body.get('full_frame') is True
                            state['retry']={'pending':True,'full_frame':full_frame,'deadline':time.monotonic()+25,'message':('正在辨識整個 OBS 遊戲畫面；請保持投影視窗完整可見。完成後自動恢復原本範圍。' if full_frame else '正在重新擷取遊戲畫面；若讀不到，請切回遊戲並停留幾秒。'),'text':''}
                            recorder.candidate='';recorder.repeats=0
                            restart.set()
                            if worker[0] and worker[0].poll() is None:worker[0].terminate()
                    return self.send({'ok':True,'retry':dict(state['retry'])})
                elif self.path=='/api/pause':
                    with lock:
                        if settings['capture_mode']=='paste' and not body['paused']:raise ValueError('Choose a capture source first.')
                        state['paused']=bool(body['paused']);recorder.candidate='';recorder.repeats=0
                        if state['paused']:state['retry']['pending']=False
                        restart.set()
                        if worker[0] and worker[0].poll() is None:worker[0].terminate()
                elif self.path=='/api/add':
                    text=body.get('japanese')
                    if not isinstance(text,str) or not text.strip() or len(text)>12000:raise ValueError('Paste between 1 and 12,000 characters.')
                    if 'save' in body and not isinstance(body['save'],bool):raise ValueError('Expected save true or false.')
                    with lock:
                        previous=journal.get(body['temporary_id']) if type(body.get('temporary_id')) is int and body['temporary_id']<0 else None
                        if previous and previous['japanese']!=text:raise ValueError('Temporary text changed; open it again before saving.')
                        state['last']=journal.record(text.strip(),previous['game'] if previous else settings['process'],kind=previous['kind'] if previous else 'manual',raw=previous['original'] if previous else text,save=body.get('save'))
                        state['version']+=1;row=state['last']
                    return self.send({'ok':True,'row':row})
                elif self.path=='/api/decide-ocr':
                    if body.get('choice') not in ('keep','ignore','correct'):raise ValueError('Invalid choice')
                    with lock:
                        correction=None
                        if body['choice']=='correct':
                            with journal.connect() as db:pending=db.execute('SELECT text FROM pending_ocr WHERE id=?',(int(body['id']),)).fetchone()
                            if not pending:raise ValueError('這筆待確認文字已處理，請重新整理。')
                            correction=next((r for r in matcher.suggest(pending['text']) if r['id']==body.get('source_id')),None)
                            if correction is None:raise ValueError('Invalid correction')
                        result=journal.decide(int(body['id']),body['choice']!='ignore',correction,body.get('japanese') if body['choice']=='keep' else None)
                        if result:state['last']=result
                        state['version']+=1;recorder.last=''
                    return self.send({'ok':True,'row':result})
                elif self.path in ('/api/remove','/api/restore'):

                    journal.set_deleted(int(body['id']),self.path=='/api/remove')
                    with lock:state['version']+=1;recorder.last=''
                elif self.path=='/api/batch-translations':
                    items=body['items'];expected=body['ids']
                    if not isinstance(items,list) or not items or len(items)>1000:raise ValueError('Invalid batch size')
                    ids=[r['id'] for r in items]
                    if len(set(ids))!=len(ids) or set(ids)!=set(expected):raise ValueError('翻譯編號與這一批不一致，尚未儲存。')
                    for r in items:
                        if type(r['id']) is not int or any(not isinstance(r.get(k),str) or not r[k].strip() for k in ('english','traditional_chinese')):raise ValueError('翻譯欄位不完整')
                    with journal.connect() as db:
                        db.execute('BEGIN IMMEDIATE')
                        for r in items:
                            found=db.execute('SELECT id FROM sentences WHERE id=? AND deleted=0 AND duplicate_of IS NULL',(r['id'],)).fetchone()
                            if not found:raise ValueError('句子已移除或不存在：'+str(r['id']))
                        for r in items:db.execute('UPDATE sentences SET english=?,traditional_chinese=? WHERE id=?',(r['english'],r['traditional_chinese'],r['id']))
                    journal.export_pending.set()
                    with lock:state['version']+=1
                elif self.path=='/api/edit':
                    journal.edit(body)
                    with lock:state['version']+=1
                elif self.path=='/api/backup':return self.send({'file':journal.backup()})
                elif self.path=='/api/settings':
                    name=str(body['process']).removesuffix('.exe')
                    if not re.fullmatch(r'[A-Za-z0-9_ -]{1,80}',name):raise ValueError('Use a process name without a path.')
                    top=float(body['crop_top']);height=float(body['crop_height'])
                    if not 0<=top<.95 or not .05<=height<=1-top:raise ValueError('Capture region must fit inside the game window.')
                    if name!='obs64':raise ValueError('This journal follows obs64 only.')
                    with lock:
                        settings.update(process=name,crop_top=top,crop_height=height)
                        config_path.write_text(json.dumps(settings,indent=2),encoding='utf-8')
                        recorder.candidate='';recorder.last='';recorder.repeats=0
                    restart.set()
                    if worker[0] and worker[0].poll() is None:worker[0].terminate()
                elif self.path=='/api/stop':
                    self.send({'ok':True});threading.Thread(target=server.shutdown,daemon=True).start();return
                else:return self.send({'error':'Not found'},404)
                self.send({'ok':True})
            except (ValueError,KeyError,TypeError,sqlite3.Error) as e:self.send({'error':str(e)},400)
        def log_message(self,*args):pass
    class LocalServer(ThreadingHTTPServer):
        allow_reuse_address=False
        def server_bind(self):
            if hasattr(socket,'SO_EXCLUSIVEADDRUSE'):
                self.socket.setsockopt(socket.SOL_SOCKET,socket.SO_EXCLUSIVEADDRUSE,1)
            super().server_bind()
    try:server=LocalServer(('127.0.0.1',args.port),Handler)
    except OSError:
        if not args.no_browser:webbrowser.open(origin)
        return
    journal.start_exports()
    import auto_translate
    if not settings.get('local_translation_initialized'):
        settings.update(auto_translate=False,local_translation_initialized=True)
        config_path.write_text(json.dumps(settings,indent=2),encoding='utf-8')
    state['translation']={'enabled':settings.get('auto_translate',True),'provider':'LM Studio · Qwen3-14B (local)','status':'Local translation is optional. Copy a learning prompt if no model is installed.'}
    import local_translate
    import translation_backends
    state['translation']['provider']=translation_backends.selected().label
    state['translation']['status']='Ready: '+translation_backends.selected().label
    local_translator=local_translate.Translator(journal,stop,state,lock)
    threading.Thread(target=capture,daemon=True).start()
    if not args.no_browser:webbrowser.open(origin)
    try:server.serve_forever()
    finally:
        stop.set()
        if worker[0] and worker[0].poll() is None:worker[0].terminate()
        journal.close_exports()
        server.server_close()
if __name__=='__main__':main()
