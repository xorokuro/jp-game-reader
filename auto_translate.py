import json,threading,time,urllib.request,urllib.parse,urllib.error,os
from pathlib import Path

KEY_FILE=Path(os.environ.get('JP_READER_DATA',str(Path(__file__).resolve().parent/'saved_sentences')))/'deepl-key.txt'
def get_key():
    return (KEY_FILE.read_text(encoding='utf-8').strip() if KEY_FILE.exists() else os.environ.get('DEEPL_AUTH_KEY','').strip())

def save_key(key):
    if not isinstance(key,str) or not key.strip() or len(key)>256 or any(c.isspace() for c in key.strip()):raise ValueError('Enter a valid DeepL API key.')
    KEY_FILE.parent.mkdir(parents=True,exist_ok=True)
    temporary=KEY_FILE.with_suffix('.tmp');temporary.write_text(key.strip(),encoding='utf-8');temporary.replace(KEY_FILE)

def translate(text,target):
    key=get_key()
    if not key:raise ValueError('Add your DeepL API key in Translation setup.')
    payload={'text':[text],'source_lang':'JA','target_lang':{'en':'EN-US','zh-TW':'ZH-HANT'}[target]}
    endpoint='https://api-free.deepl.com' if key.endswith(':fx') else 'https://api.deepl.com'
    req=urllib.request.Request(endpoint+'/v2/translate',data=json.dumps(payload).encode('utf-8'),headers={'Authorization':'DeepL-Auth-Key '+key,'Content-Type':'application/json'})
    try:
        with urllib.request.urlopen(req,timeout=25) as response:data=json.load(response)
    except urllib.error.HTTPError as exc:
        raise ValueError({403:'DeepL rejected the API key.',456:'DeepL character allowance reached.',429:'DeepL is busy; retrying later.'}.get(exc.code,'DeepL request failed (HTTP '+str(exc.code)+').')) from None
    result=data['translations'][0]['text']
    if not result.strip():raise ValueError('Empty translation received')
    return result

def start(journal,stop,state,lock,enabled=True):
    state['translation']={'enabled':enabled,'status':'Waiting for saved Japanese text','provider':'DeepL API'}
    retry={}
    def run():
        while not stop.wait(1):
            with lock:
                if not state['translation']['enabled']:continue
                if not get_key():
                    state['translation']['status']='DeepL setup needed: add your API key. Japanese text is still saved.'
                    continue
            with journal.connect() as db:
                rows=db.execute("SELECT id,japanese,english,traditional_chinese FROM sentences WHERE deleted=0 AND duplicate_of IS NULL AND (english='' OR traditional_chinese='') ORDER BY id DESC LIMIT 100").fetchall()
            row=next((r for r in rows if time.monotonic()>=retry.get(r['id'],0)),None)
            if row is None:continue
            try:
                for field,target in [('english','en'),('traditional_chinese','zh-TW')]:
                    if row[field]:continue
                    with lock:
                        if stop.is_set() or not state['translation']['enabled']:break
                        state['translation']['status']='Translating sentence #'+str(row['id'])
                    translated=translate(row['japanese'],target)
                    with journal.connect() as db:
                        db.execute(f"UPDATE sentences SET {field}=? WHERE id=? AND japanese=? AND {field}='' AND deleted=0",(translated,row['id'],row['japanese']))
                    journal.export_pending.set()
                    with lock:state['version']+=1
                with lock:state['translation']['status']='Translation saved · machine translation may contain errors'
            except Exception as exc:
                retry[row['id']]=time.monotonic()+60
                with lock:state['translation']['status']='Translation unavailable; will retry: '+str(exc)[:160]
    threading.Thread(target=run,daemon=True).start()
