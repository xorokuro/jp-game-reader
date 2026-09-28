"""Translation engine registry: add providers without changing the reading UI."""
import json
import os
from pathlib import Path
import subprocess
import threading

ROOT=Path(__file__).resolve().parent
CONFIG=Path(os.environ.get('JP_READER_DATA',str(ROOT/'saved_sentences')))/'translation-engine.json'
ENGINE_LOCK=threading.Lock()


class Argos:
    id='argos'
    label='Argos Translate · offline CPU'
    model='ja-en-zt'

    def home(self):return Path(os.environ.get('JP_READER_ARGOS_HOME',str(ROOT/'translation'/'argos')))

    def options(self):
        home=self.home()
        available=(home/'runtime'/'python.exe').is_file() and (home/'ready.json').is_file()
        return {'id':self.id,'label':self.label,'available':available,'selected':self.model,
                'message':'Japanese → English; 繁體中文 via English. Fully offline; no LM Studio or GPU needed.' if available else 'Argos is not bundled here. Copy the complete updated portable folder, including translation/argos.',
                'models':[{'id':self.model,'label':'Japanese → English + 繁體中文 (via English)','state':'ready'}] if available else []}

    def ready(self):
        info=self.options()
        if not info['available']:raise ValueError(info['message'])

    def select(self,model):
        if model!=self.model:raise ValueError('Choose an installed Argos language package.')
        self.ready()

    def translate(self,text):
        self.ready()
        from local_translate import translation_chunks
        command=[str(self.home()/'runtime'/'python.exe'),str(ROOT/'argos_worker.py'),'--home',str(self.home())]
        try:
            result=subprocess.run(command,input=json.dumps({'chunks':translation_chunks(text,600)},ensure_ascii=True),capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=900,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        except subprocess.TimeoutExpired:
            raise ValueError('Argos took too long. Try a smaller passage; your original text is saved.') from None
        lines=[line[len('JP_READER_RESULT='):] for line in result.stdout.splitlines() if line.startswith('JP_READER_RESULT=')]
        if not lines:raise ValueError('Argos could not start. Check that the complete translation/argos folder was copied.')
        data=json.loads(lines[-1])
        if result.returncode or data.get('error'):raise ValueError('Argos: '+str(data.get('error','translation failed')))
        if any(not isinstance(data.get(key),str) or not data[key].strip() for key in ('en-US','zh-Hant')):raise ValueError('Argos returned an incomplete translation.')
        return data


class LMStudio:
    id='lm-studio'
    label='LM Studio · local LLM'

    def options(self):
        import local_translate
        info=local_translate.models()
        return {**info,'id':self.id,'label':self.label,
                'message':'Uses your LM Studio server and downloaded models.' if info['available'] else info['message'],
                'models':[dict(m,label=m['id']+(' · loaded' if m['state']=='loaded' else ' · not loaded')) for m in info['models']]}

    def ready(self):
        info=self.options()
        if not info['available']:raise ValueError(info['message'])
        if not any(m['id']==info['selected'] and m['state']=='loaded' for m in info['models']):raise ValueError('Load your selected model in LM Studio or choose Argos Translate.')

    def select(self,model):
        import local_translate
        local_translate.switch_model(model)

    def translate(self,text):
        import local_translate
        return local_translate.translate(text)


ENGINES={engine.id:engine for engine in (Argos(),LMStudio())}


def selected_id():
    try:
        value=json.loads(CONFIG.read_text(encoding='utf-8'))['engine']
        if value in ENGINES:return value
    except (OSError,ValueError,KeyError,TypeError):pass
    return 'argos' if ENGINES['argos'].options()['available'] else 'lm-studio'


def selected():return ENGINES[selected_id()]


def catalog():
    options=[engine.options() for engine in ENGINES.values()]
    return {'selected_engine':selected_id(),'engines':options}


def select(engine_id,model):
    if engine_id not in ENGINES:raise ValueError('Choose a supported translation engine.')
    if not ENGINE_LOCK.acquire(blocking=False):raise ValueError('Translation is running. Wait for it to finish before changing engines.')
    try:
        ENGINES[engine_id].select(model)
        CONFIG.parent.mkdir(parents=True,exist_ok=True)
        pending=CONFIG.with_suffix('.tmp')
        pending.write_text(json.dumps({'engine':engine_id}),encoding='utf-8');pending.replace(CONFIG)
    finally:ENGINE_LOCK.release()
    return catalog()


def ready():selected().ready()


def translate(text):
    with ENGINE_LOCK:
        engine=selected()
        return engine.label,engine.translate(text)
