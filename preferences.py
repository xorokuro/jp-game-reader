"""Keep appearance and dictionary preferences with the portable journal."""
import json


def allowed(key):
    return isinstance(key,str) and key.startswith(('fortune-', 'dimension-journal-', 'jp-reader-'))


def save(path, values):
    if not isinstance(values,dict) or len(values)>150:
        raise ValueError('Invalid reader preferences.')
    if any(not allowed(k) or not isinstance(v,str) or len(v)>20000 for k,v in values.items()):
        raise ValueError('Invalid reader preference.')
    pending=path.with_suffix('.tmp')
    pending.write_text(json.dumps(values,ensure_ascii=False),encoding='utf-8')
    pending.replace(path)


def bootstrap(path):
    try:values=json.loads(path.read_text(encoding='utf-8'))
    except (OSError,ValueError):values={}
    values={k:v for k,v in values.items() if allowed(k) and isinstance(v,str)}
    return ('''(() => {
      const saved='''+json.dumps(values,ensure_ascii=True)+''';
      const allowed=k=>/^(fortune-|dimension-journal-|jp-reader-)/.test(k);
      try {
        if(Object.keys(saved).length)for(const key of Object.keys(localStorage))if(allowed(key))localStorage.removeItem(key);
        for(const [key,value] of Object.entries(saved))localStorage.setItem(key,value);
      } catch {}
      const set=Storage.prototype.setItem, remove=Storage.prototype.removeItem;
      let timer;
      function persist(){
        const values={};
        try{for(const key of Object.keys(localStorage))if(allowed(key))values[key]=localStorage.getItem(key);}catch{return;}
        fetch('/api/preferences',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(values),keepalive:true}).catch(()=>{});
      }
      function schedule(){clearTimeout(timer);timer=setTimeout(persist,200);}
      Storage.prototype.setItem=function(k,v){set.call(this,k,v);if(this===localStorage&&allowed(k))schedule();};
      Storage.prototype.removeItem=function(k){remove.call(this,k);if(this===localStorage&&allowed(k))schedule();};
      addEventListener('pagehide',persist);
    })();''').encode('utf-8')
