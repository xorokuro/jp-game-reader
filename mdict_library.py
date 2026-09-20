"""Read indexed local MDX/MDD content in place; no dictionary UI is launched."""
import os,html,json,mimetypes,re,sqlite3,struct,unicodedata,zlib
from contextlib import closing
from functools import lru_cache
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlencode,unquote,urlsplit

INDEX=Path(os.environ.get('JP_READER_DICTIONARY_INDEX',str(Path(__file__).resolve().parent/'dictionaries'/'mdict-index.sqlite3')))
def connect():
    db=sqlite3.connect('file:'+INDEX.as_posix()+'?mode=ro',uri=True);db.row_factory=sqlite3.Row
    return db
def normalize(word):return unicodedata.normalize('NFKC',word).strip().casefold()
def dictionaries():
    if not INDEX.exists():return []
    with closing(connect()) as db:return [dict(r) for r in db.execute('SELECT code,name FROM dictionaries ORDER BY rowid')]
def search(word,codes=None):
    if not INDEX.exists():return []
    result=[];key=normalize(word)
    with closing(connect()) as db:
        for d in db.execute('SELECT code,name FROM dictionaries ORDER BY rowid').fetchall():
            if codes is not None and d['code'] not in codes:continue
            file=db.execute("SELECT id FROM files WHERE code=? AND kind='.mdx'",(d['code'],)).fetchone()
            rows=db.execute('SELECT id,word FROM records WHERE file=? AND norm=? LIMIT 80',(file['id'],key)).fetchall()
            exact=bool(rows)
            if len(rows)<80:
                rows.extend(db.execute('SELECT id,word FROM records WHERE file=? AND norm>? AND norm<? ORDER BY norm,id LIMIT ?', (file['id'],key,key+'\U0010ffff',80-len(rows))).fetchall())
            result.append({'code':d['code'],'name':d['name'],'count':len(rows),'exact':exact,'entries':[{'id':r['id'],'title':r['word'],'anchor':''} for r in rows]})
    return result

@lru_cache(maxsize=12)
def block(path,offset,size,expected,mtime):
    p=Path(path)
    if not p.exists() or p.stat().st_mtime_ns!=mtime:raise ValueError('Dictionary source moved or changed; rebuild its index.')
    with p.open('rb') as f:f.seek(offset);raw=f.read(size)
    mode,checksum=struct.unpack('<I',raw[:4])[0],struct.unpack('>I',raw[4:8])[0]
    if mode==2:data=zlib.decompress(raw[8:])
    elif mode==0:data=raw[8:]
    else:raise ValueError('Unsupported dictionary block encoding.')
    if len(data)!=expected or zlib.adler32(data)&0xffffffff!=checksum:raise ValueError('Dictionary block is damaged.')
    return data
def read_record(db,row):
    source=db.execute('SELECT * FROM files WHERE id=?',(row['file'],)).fetchone()
    spans=db.execute('SELECT * FROM blocks WHERE file=? AND start<? AND end>? ORDER BY start',(row['file'],row['end'],row['start'])).fetchall()
    chunks=[]
    for b in spans:
        raw=block(source['path'],b['offset'],b['size'],b['end']-b['start'],source['mtime'])
        chunks.append(raw[max(0,row['start']-b['start']):min(len(raw),row['end']-b['start'])])
    return b''.join(chunks),source['encoding']
def record(code,entry_id=None,word=None):
    with closing(connect()) as db:
        source=db.execute("SELECT id FROM files WHERE code=? AND kind='.mdx'",(code,)).fetchone()
        if source is None:raise ValueError('Unknown local dictionary.')
        seen=set()
        for _ in range(12):
            if entry_id is not None:row=db.execute('SELECT * FROM records WHERE id=? AND file=?',(int(entry_id),source['id'])).fetchone()
            else:row=db.execute('SELECT * FROM records WHERE file=? AND norm=? LIMIT 1',(source['id'],normalize(word))).fetchone()
            if row is None and word:
                # Some source cross-references use a different dash in bracketed spellings.
                base=re.split('[【〔（]',word,1)[0]
                row=db.execute('SELECT * FROM records WHERE file=? AND norm=? LIMIT 1',(source['id'],normalize(base))).fetchone()
            if row is None:raise ValueError('No matching linked entry in this dictionary.')
            if row['id'] in seen:raise ValueError('Circular dictionary cross-reference.')
            seen.add(row['id']);raw,encoding=read_record(db,row);text=raw.decode(encoding,errors='replace').strip('\x00\r\n ')
            if not text.startswith('@@@LINK='):return row['word'],text
            word=text[len('@@@LINK='):].strip();entry_id=None
        raise ValueError('Dictionary cross-reference is too deep.')

def route(kind,code,**kw):return '/api/dictionary/'+kind+'?'+urlencode({'code':code,**kw})
def resource_name(name):
    name=unquote(name).replace('\\','/').lstrip('/')
    if not name or '\x00' in name or ':' in name or '..' in name.split('/') or len(name)>600:raise ValueError('Invalid resource name.')
    return name
def media(code,name):
    name=resource_name(name)
    with closing(connect()) as db:
        d=db.execute('SELECT * FROM dictionaries WHERE code=?',(code,)).fetchone()
        if d is None:raise ValueError('Unknown dictionary.')
        root=Path(d['root']).resolve();file=(root/name).resolve()
        if file.is_relative_to(root) and file.is_file() and file.suffix.lower() in ('.png','.jpg','.jpeg','.gif','.webp','.svg','.mp3','.wav','.ogg','.spx','.mp4','.woff','.woff2','.ttf','.otf'):
            data=file.read_bytes()
        else:
            row=db.execute("SELECT r.* FROM files f JOIN records r ON r.file=f.id WHERE f.code=? AND f.kind='.mdd' AND r.norm=? ORDER BY f.id LIMIT 1",(code,name.casefold())).fetchone()
            if row is None:raise ValueError('This resource was not included in the supplied dictionary files.')
            data,_=read_record(db,row)
    return data,mimetypes.guess_type(name)[0] or 'application/octet-stream'

class CleanHTML(HTMLParser):
    def __init__(self,code):super().__init__(convert_charrefs=False);self.code=code;self.parts=[];self.skip=[];self.audio=False
    def handle_starttag(self,tag,attrs):
        if tag in ('script','iframe','object','embed','form','title'):
            self.skip.append(tag);return
        if self.skip or self.audio:return
        if tag in ('html','head','body','meta','link','base','input','button'):return
        attrs=dict(attrs);href=attrs.get('href','')
        if tag=='a' and href.lower().startswith('sound://'):
            self.parts.append('<audio controls preload="none" aria-label="Dictionary recording" src="'+html.escape(route('media',self.code,name=href[8:]),quote=True)+'"></audio>');self.audio=True;return
        cleaned=[]
        for key,value in attrs.items():
            if key.startswith('on') or key in ('style','srcdoc','target','action','srcset'):continue
            if key=='href':
                if value.startswith('entry://'):
                    word=unquote(value[8:]).split('#',1)[0];value=route('resolve',self.code,word=word)
                elif not value.startswith('#'):continue
            if key=='src':
                try:value=route('media',self.code,name=resource_name(value))
                except ValueError:continue
            if key not in ('href','src','class','id','title','alt','lang','colspan','rowspan','width','height','data-orgtag','open'):continue
            cleaned.append(key+'="'+html.escape(value or '',quote=True)+'"')
        self.parts.append('<'+tag+(' '+' '.join(cleaned) if cleaned else '')+'>')
    def handle_endtag(self,tag):
        if self.skip:
            if tag==self.skip[-1]:self.skip.pop()
            return
        if self.audio:
            if tag=='a':self.audio=False
            return
        if tag not in ('html','head','body','meta','link','base','input','button'):self.parts.append('</'+tag+'>')
    def handle_data(self,data):
        if not self.skip and not self.audio:self.parts.append(data)
    def handle_entityref(self,name):
        if not self.skip and not self.audio:self.parts.append('&'+name+';')
    def handle_charref(self,name):
        if not self.skip and not self.audio:self.parts.append('&#'+name+';')

def collection_sections(text):
    titles=dict(re.findall(r'<ddudt\b[^>]*id="([^"]+)"[^>]*>(.*?)</ddudt>',text,re.S|re.I))
    text=re.sub(r'<ddudtb\b.*?</ddudtb>|<span class="ddudnav">.*?</span>\s*<hr[^>]*>', '',text,flags=re.S|re.I)
    def section(m):
        key=re.search(r'id="([^"]+)"',m[1]);title=titles.get(key[1].removesuffix('_c') if key else '', 'Dictionary source')
        title=re.sub('<[^>]+>','',title)
        return '<details class="import-source" open><summary>'+html.escape(html.unescape(title))+'</summary>'+m[2]+'</details>'
    return re.sub(r'<ddudc\b([^>]*)>(.*?)</ddudc>',section,text,flags=re.S|re.I)

def entry(code,entry_id=None,word=None):
    title,text=record(code,entry_id,word)
    with closing(connect()) as db:d=dict(db.execute('SELECT * FROM dictionaries WHERE code=?',(code,)).fetchone())
    cssfile=Path(d['root'])/d['css'];css=cssfile.read_text(encoding='utf-8-sig') if cssfile.exists() else ''
    css=re.sub(r'@import[^;]+;','',css,flags=re.I)
    def cssurl(m):
        try:return 'url("'+route('media',code,name=resource_name(m[1].strip(' \"\'')))+'")'
        except ValueError:return 'none'
    css=re.sub(r'url\(([^)]+)\)',cssurl,css,flags=re.I).replace('</style','')
    if code=='MDX_ALL':text=collection_sections(text)
    parser=CleanHTML(code);parser.feed(text)
    return ('<!doctype html><html lang="ja"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><style>'+css+'</style><body class="mdict-entry"><div class="dictionary-source">'+html.escape(d['name'])+' · '+html.escape(title)+'</div>'+''.join(parser.parts)+'<style>.import-source{display:block;margin:14px 0;padding:12px;border:1px solid #526571;border-radius:8px}.import-source>summary{cursor:pointer;font-weight:bold}ddudm,ddudc{display:block!important}img{max-width:100%;height:auto}audio{min-width:180px}table{max-width:100%}</style><link rel="stylesheet" href="/dictionary-entry.css"></body></html>').encode('utf-8')
