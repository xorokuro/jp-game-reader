// 台本 · Script view: read, search and study an extracted game script inside the reader.
// Selecting Japanese (or EN/繁中) text looks it up in your dictionaries, like the reading card.
(() => {
 const panel=document.querySelector('#reader-workspace section.current');
 const head=panel?.querySelector('.card-head');
 if(!panel||!head)return;
 const icon=name=>window.readerIcon?readerIcon(name):'';
 const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 // Annotations may use a few inline tags; everything else is shown as text.
 const safe=s=>esc(s).replace(/&lt;(\/?)(b|br|i|u|strong|em|ruby|rt|sup|sub)\s*\/?&gt;/gi,'<$1$2>').replace(/\n/g,'<br>');
 const rubyHtml=s=>esc(s).replace(/([㐀-鿿々〆ヵヶ]+)（([ぁ-ゖァ-ヺー]+)）/g,'<ruby>$1<rt>$2</rt></ruby>').replace(/\n/g,'<br>');
 const KIND={dialogue:'對話',mail:'郵件',tip:'TIPS',ui:'介面',extra:'其他'};
 const PAGE=80;
 const store={get(k,d){try{const v=localStorage.getItem(k);return v===null?d:JSON.parse(v);}catch{return d;}},set(k,v){try{localStorage.setItem(k,JSON.stringify(v));}catch{}}};

 // ------------------------------------------------------------- view tabs
 const title=head.querySelector('.hand-title');
 const tabs=E('div');tabs.className='view-tabs';tabs.setAttribute('role','tablist');
 const readTab=E('button'),scriptTab=E('button');
 readTab.innerHTML='<span lang="ja">読む</span><small>Reading</small>';scriptTab.innerHTML='<span lang="ja">台本</span><small>Script</small>';
 for(const [b,v] of [[readTab,'read'],[scriptTab,'script']]){b.type='button';b.className='view-tab';b.dataset.view=v;b.setAttribute('role','tab');b.onclick=()=>setView(v);}
 tabs.append(readTab,scriptTab);title.replaceWith(tabs);
 scriptTab.hidden=false;

 // ------------------------------------------------------------- script view skeleton
 const view=E('div');view.id='script-view';view.hidden=true;
 view.innerHTML=`
  <div class="script-bar">
   <label class="script-search"><span class="sr-only">搜尋台本</span><input id="script-q" type="search" lang="ja" autocomplete="off" spellcheck="false" placeholder="搜尋台本 · JA / EN / 繁中 …  (Ctrl+K)"></label>
   <select id="script-pick" aria-label="Script"></select>
   <button id="script-import" type="button">載入台本 · Load script</button>
   <input id="script-file" type="file" accept=".json,application/json" hidden>
   <button id="script-filter-toggle" type="button" class="icon-button" title="篩選與設定 · Filters" aria-expanded="false"></button>
  </div>
  <details class="script-format"><summary>台本格式與範例 · Script format</summary>
   <p>載入任何遊戲的 UTF-8 JSON 台本。必要欄位：game（名稱）、rows（依閱讀順序排列的台詞）；每句至少提供 ja、en 或 zh 其中一種。其他語言、說話者與章節可省略。</p>
   <p>上限 64 MiB / 200,000 句。每部作品使用不同 script_id；重複 ID 不會覆蓋原稿。</p>
   <button id="script-template" type="button">下載範例 JSON</button>
   <a href="https://github.com/xorokuro/jp-game-reader/blob/main/SCRIPT-FORMAT.md" target="_blank" rel="noopener noreferrer">完整格式說明 · Format guide</a>
  </details>
  <div id="script-import-status" class="muted" role="status"></div>
  <div id="script-filters" class="script-filters" hidden>
   <div class="chip-row" id="script-kinds" role="group" aria-label="Kinds"></div>
   <div class="chip-row">
    <select id="script-need" aria-label="Languages required"><option value="">全部語言</option><option value="ja-en">需要 JA + EN</option><option value="all">需要三語齊全</option></select>
    <input id="script-path" type="search" placeholder="路徑篩選 · e.g. resg01_05" aria-label="Path filter" spellcheck="false">
    <label><input id="script-annotated" type="checkbox"> 只看有精讀註解</label>
    <label><input id="script-blur" type="checkbox"> 模糊翻譯（滑過才顯示）</label>
   </div>
   <div class="chip-row script-match">
    <span>OCR 對照台本</span>
    <select id="script-match" aria-label="Script used to correct OCR"><option value="auto">自動（依遊戲視窗）</option><option value="off">關閉</option></select>
    <small id="script-match-status"></small>
   </div>
  </div>
  <div class="script-status"><span id="script-count"></span><span class="script-jump"><label for="script-jump">跳到 #</label><input id="script-jump" type="number" min="1" inputmode="numeric"><button id="script-jump-go" type="button">Go</button></span></div>
  <div id="script-list" class="script-list" tabindex="-1" aria-live="polite"></div>`;
 head.after(view);
 const $s=id=>view.querySelector('#'+id);
 const list=$s('script-list'),q=$s('script-q'),pick=$s('script-pick'),count=$s('script-count');
 $s('script-filter-toggle').innerHTML=icon('list');

 let scripts=[],script=store.get('jp-reader-script-id',''),kinds=new Set(store.get('jp-reader-script-kinds',['dialogue','mail','tip','ui','extra']));
 const positions=store.get('jp-reader-script-positions',{}),viewOffsets=store.get('jp-reader-script-offsets',{});
 let total=0,start=0,end=0,loading=false,token=0,activeN=positions[script]||store.get('jp-reader-script-pos',0);
 function rememberPosition(){
  if(!script)return;
  const top=list.getBoundingClientRect().top;
  const first=[...list.querySelectorAll('.script-line')].find(el=>el.getBoundingClientRect().bottom>top+8);
  if(first){activeN=Number(first.dataset.n);viewOffsets[script]={n:activeN,offset:first.getBoundingClientRect().top-top};store.set('jp-reader-script-offsets',viewOffsets);}
  positions[script]=activeN;store.set('jp-reader-script-positions',positions);
 }
 function switchScript(id){
  rememberPosition();script=id;pick.value=id;store.set('jp-reader-script-id',script);
  activeN=positions[script]||1;end=0;
  q.value='';$s('script-path').value='';$s('script-need').value='';$s('script-annotated').checked=false;
  kinds=new Set(Object.keys(KIND));drawKinds();
  const info=scripts.find(s=>s.id===script);q.placeholder=info?'搜尋《'+info.title+'》· JA / EN / 繁中 … (Ctrl+K)':'搜尋台本';
  reload(activeN,true);
 }
 $s('script-blur').checked=store.get('jp-reader-script-blur',false);list.classList.toggle('blur-tr',$s('script-blur').checked);

 function setView(v){
  const script=v==='script'&&!scriptTab.hidden;
  panel.dataset.view=script?'script':'read';view.hidden=!script;
  readTab.setAttribute('aria-selected',String(!script));scriptTab.setAttribute('aria-selected',String(script));
  store.set('jp-reader-view',script?'script':'read');
  if(script&&!end)reload(activeN||1,true);
  window.dispatchEvent(new Event('reader-layout'));
 }

 // ------------------------------------------------------------- data
 function params(extra={}){
  return new URLSearchParams({script,q:q.value.trim().replace(/^#\d+$/,''),kinds:[...kinds].join(','),need:$s('script-need').value,path:$s('script-path').value.trim(),annotated:$s('script-annotated').checked?'1':'',...extra});
 }
 async function fetchRows(offset,limit=PAGE){return api('script/search?'+params({offset,limit}));}
 async function reload(aroundN,restore=false){
  if(!script){list.replaceChildren(emptyNote());count.textContent='尚未載入台本 · Load a script to start';return;}
  const my=++token;loading=true;list.classList.add('loading');
  try{
   let offset=0;
   if(aroundN){offset=(await api('script/position?'+params({n:aroundN}))).offset;if(my!==token)return;offset=Math.max(0,offset-10);}
   const data=await fetchRows(offset);if(my!==token)return;
   total=data.total;start=offset;end=offset+data.rows.length;
   list.replaceChildren(topSentinel,...data.rows.map(card),bottomSentinel);
   if(!data.rows.length)list.append(emptyNote());
   status();
   const target=aroundN&&list.querySelector(`[data-n="${aroundN}"]`);
   if(target){const saved=restore&&viewOffsets[script];const offset=saved&&saved.n===aroundN?saved.offset:list.clientHeight/2-target.clientHeight/2;list.scrollTop+=target.getBoundingClientRect().top-list.getBoundingClientRect().top-offset;mark(target);}else list.scrollTop=0;
  }catch(e){count.textContent=e.message;}
  finally{if(my===token){loading=false;list.classList.remove('loading');}}
 }
 async function more(direction){
  if(loading||!script)return;
  if(direction>0&&end>=total)return;if(direction<0&&start<=0)return;
  loading=true;const my=token;
  try{
   const offset=direction>0?end:Math.max(0,start-PAGE),limit=direction>0?PAGE:start-offset;
   const data=await fetchRows(offset,limit);if(my!==token)return;
   const cards=data.rows.map(card);
   if(direction>0){bottomSentinel.before(...cards);end=offset+data.rows.length;}
   else{const before=list.scrollHeight;topSentinel.after(...cards);start=offset;list.scrollTop+=list.scrollHeight-before;}
   status();
  }catch(e){count.textContent=e.message;}
  finally{if(my===token)loading=false;}
 }
 const topSentinel=E('div'),bottomSentinel=E('div');topSentinel.className=bottomSentinel.className='script-sentinel';
 const observer=new IntersectionObserver(entries=>{for(const e of entries)if(e.isIntersecting)more(e.target===bottomSentinel?1:-1);},{root:list,rootMargin:'600px 0px'});
 observer.observe(topSentinel);observer.observe(bottomSentinel);
 function status(){
  const info=scripts.find(s=>s.id===script);
  count.innerHTML=total?`<b>${(start+1).toLocaleString()}–${end.toLocaleString()}</b> / ${total.toLocaleString()} 句${info&&total!==info.rows?` <small>（全 ${info.rows.toLocaleString()}）</small>`:''} · 捲動載入更多`:'沒有符合的台詞';
 }
 function emptyNote(){const p=E('div');p.className='script-empty';p.innerHTML=script?'<b>找不到符合的台詞</b><span>換個關鍵字，或在篩選中放寬條件。</span>':'<b>載入你的台本 · Bring your own script</b><span>按「載入台本」選取 JSON 檔案，或先下載範例。可載入多部作品並隨時切換。</span>';return p;}

 // ------------------------------------------------------------- line cards
 function highlighted(text,tips){
  const terms=q.value.trim().replace(/^#\d+$/,'').split(/\s+/).filter(Boolean);
  const parts=[...tips.filter(Boolean).map(t=>({t,tip:true})),...terms.map(t=>({t,tip:false}))].sort((a,b)=>b.t.length-a.t.length);
  const frag=document.createDocumentFragment();
  if(!parts.length){frag.append(text);return frag;}
  const rx=new RegExp('('+parts.map(p=>p.t.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')).join('|')+')','gi');
  let last=0;
  for(const m of text.matchAll(rx)){
   frag.append(text.slice(last,m.index));
   const isTerm=terms.some(t=>t.toLowerCase()===m[0].toLowerCase());
   const el=E(isTerm?'mark':'span',m[0]);if(!isTerm){el.className='tip-word';el.title='TIPS 用語';}
   frag.append(el);last=m.index+m[0].length;
  }
  frag.append(text.slice(last));return frag;
 }
 function prompt(r){
  const context=[r.en&&'官方英譯（參考，不一定逐字）：'+r.en,r.zh&&'官方繁中譯（參考，不一定逐字）：'+r.zh].filter(Boolean).join('\n');
  return japaneseAnalysisPrompt(r.ja+(r.speaker?'\n（說話者：'+r.speaker+'）':''),true)+(context?'\n\n'+context:'');
 }
 function card(r){
  const el=E('article');el.className='script-line';el.dataset.n=r.n;el.dataset.kind=r.kind;
  const top=E('header');
  const no=E('button','#'+r.n);no.type='button';no.className='line-no';no.title='前後文 · Show in context';no.onclick=()=>context(r.n);
  const kind=E('span',KIND[r.kind]||r.kind);kind.className='kind-chip';
  top.append(no,kind);
  if(r.speaker){const who=E('span',r.speaker);who.className='speaker';who.lang='ja';top.append(who);}
  const src=E('span',r.source.replace(/^scenario\//,'').replace(/\.ks$/,'').replace(/^config\//,'')+' · '+r.id);src.className='src';top.append(src);
  if(r.annotated){const star=E('span','精讀');star.className='note-badge';star.title='有精讀註解';top.append(star);}
  el.append(top);
  for(const [cls,text,lang,label] of [['sl-ja',r.ja,'ja','JA'],['sl-en',r.en,'en','EN'],['sl-zh',r.zh,'zh-Hant','中']]){
   if(!text)continue;
   const row=E('div');row.className='sl-row '+cls;
   const tag=E('span',label);tag.className='sl-lang';tag.setAttribute('aria-hidden','true');
   const p=E('p');p.lang=lang;p.dataset.lookup='';p.append(highlighted(text,cls==='sl-ja'?r.tips||[]:[]));
   row.append(tag,p);el.append(row);
  }
  const bar=E('div');bar.className='sl-actions';
  const open=E('button');open.type='button';open.innerHTML=icon('book')+'<span>開到閱讀卡</span>';open.title='在閱讀卡打開（可儲存到日誌）';open.onclick=()=>openInReader(r);
  const copyBtn=E('button');copyBtn.type='button';copyBtn.innerHTML=icon('paste')+'<span>複製</span>';
  copyBtn.onclick=async()=>{try{await navigator.clipboard.writeText(r.ja);copyBtn.querySelector('span').textContent='已複製';setTimeout(()=>copyBtn.querySelector('span').textContent='複製',1400);}catch{copy(r.ja);}};
  const gpt=sendButton('只傳日文',()=>prompt(r),{raw:true});gpt.type='button';gpt.title='傳到 ChatGPT（附官方譯文參考）';
  const claude=claudeButton(()=>prompt(r),{raw:true});
  bar.append(open,copyBtn,gpt,claude);
  if(r.annotated){
   const noteBtn=E('button');noteBtn.type='button';noteBtn.className='note-toggle';noteBtn.innerHTML=icon('note')+'<span>精讀註解</span>';noteBtn.setAttribute('aria-expanded','false');
   noteBtn.onclick=()=>toggleNote(el,r,noteBtn);bar.append(noteBtn);
  }
  el.append(bar);
  el.addEventListener('pointerdown',()=>mark(el));
  return el;
 }
 function mark(el){
  list.querySelectorAll('.script-line.active').forEach(x=>x.classList.remove('active'));
  el.classList.add('active');activeN=Number(el.dataset.n);store.set('jp-reader-script-pos',activeN);positions[script]=activeN;store.set('jp-reader-script-positions',positions);
 }
 async function toggleNote(el,r,button){
  let box=el.querySelector('.sl-note');
  if(box){box.hidden=!box.hidden;button.setAttribute('aria-expanded',String(!box.hidden));return;}
  box=E('div');box.className='sl-note';box.textContent='載入註解…';el.append(box);button.setAttribute('aria-expanded','true');
  try{
   const note=(await api('script/row?'+new URLSearchParams({script,n:r.n}))).note||{};
   let html='';
   if(note.ruby)html+=`<div class="note-ruby" lang="ja">${rubyHtml(note.ruby)}</div>`;
   if(note.note_src)html+=`<p class="note-src">${safe(note.note_src)}</p>`;
   if(note.ja_tr)html+=`<h4>精讀直譯</h4><p class="note-tr">${esc(note.ja_tr).replace(/\n/g,'<br>')}</p>`;
   if(Array.isArray(note.vocab)&&note.vocab.length){
    html+='<h4>語彙</h4><div class="note-table-wrap"><table class="note-vocab"><thead><tr><th>詞</th><th>讀音</th><th>詞性</th><th>語義</th><th>級</th><th>類義辨析</th></tr></thead><tbody>'+
     note.vocab.map(v=>'<tr>'+[0,1,2,3,4].map(i=>`<td${i<2?' lang="ja"':''}>${esc(v[i]??'')}</td>`).join('')+`<td>${safe(v[5]??'')}</td></tr>`).join('')+'</tbody></table></div>';
   }
   if(Array.isArray(note.grammar)&&note.grammar.length)html+='<h4>文法</h4>'+note.grammar.map(g=>`<details class="note-grammar"><summary>${safe(g[0])}</summary><div>${safe(g[1]??'')}</div></details>`).join('');
   for(const [key,label] of [['style','文體'],['gap','譯文落差']])if(Array.isArray(note[key])&&note[key].length)html+=`<h4>${label}</h4><ul>${note[key].map(x=>`<li>${safe(x)}</li>`).join('')}</ul>`;
   if(Array.isArray(note.ex)&&note.ex.length)html+='<h4>例句</h4><ul class="note-ex">'+note.ex.map((x,i)=>`<li><span lang="ja">${rubyHtml(x)}</span><small>${esc(note.ex_tr?.[i]??'')}</small></li>`).join('')+'</ul>';
   box.innerHTML=html||'（這句的註解是空的）';
   box.querySelectorAll('.note-ruby,.note-tr,.note-ex span,.note-vocab td').forEach(n=>n.dataset.lookup='');
  }catch(e){box.textContent=e.message;}
 }
 function openInReader(r){
  if(dirty())return msg('請先儲存閱讀卡的編輯內容。');
  following=false;navSeq=null;
  showCurrent({id:-Date.now(),kind:'script',temporary:true,localDraft:true,japanese:r.ja,english:r.en,traditional_chinese:r.zh,note:'',source_id:r.source_id||script+'::'+r.key});
  rememberPin();setView('read');window.scrollTo({top:0});
  $('paste-status').textContent='台本 #'+r.n+' · 選取單字即可查詢；按「儲存」可加入日誌（連同官方譯文）。';
  $('latest').focus({preventScroll:true});
 }
 async function context(n){
  q.value='';$s('script-path').value='';$s('script-need').value='';$s('script-annotated').checked=false;
  kinds=new Set(['dialogue','mail','tip','ui','extra']);drawKinds();store.set('jp-reader-script-kinds',[...kinds]);
  await reload(n);
 }
 window.readerScript={open:async(key)=>{const at=await api('script/locate?'+new URLSearchParams({key})).catch(()=>null);if(!at)return false;rememberPosition();script=at.script;pick.value=script;store.set('jp-reader-script-id',script);drawKinds();setView('script');await context(at.n);return true;}};

 // ------------------------------------------------------------- filters & controls
 function drawKinds(){
  const host=$s('script-kinds');host.replaceChildren();
  const info=scripts.find(s=>s.id===script)?.kinds||{};
  for(const k of Object.keys(KIND)){
   if(!info[k])continue;
   const b=E('button');b.type='button';b.className='kind-toggle';b.dataset.kind=k;b.setAttribute('aria-pressed',String(kinds.has(k)));
   b.innerHTML=`${KIND[k]} <small>${info[k].toLocaleString()}</small>`;
   b.onclick=()=>{kinds.has(k)?kinds.delete(k):kinds.add(k);if(!kinds.size)kinds.add(k);store.set('jp-reader-script-kinds',[...kinds]);drawKinds();reload();};
   host.append(b);
  }
 }
 let timer;
 q.addEventListener('input',()=>{clearTimeout(timer);timer=setTimeout(()=>{const m=q.value.trim().match(/^#(\d+)$/);m?context(Number(m[1])):reload();},220);});
 q.addEventListener('keydown',e=>{if(e.key==='Enter'){clearTimeout(timer);const m=q.value.trim().match(/^#(\d+)$/);m?context(Number(m[1])):reload();}if(e.key==='Escape'&&q.value){q.value='';reload(activeN);}});
 for(const id of ['script-need','script-annotated'])$s(id).addEventListener('change',()=>reload());
 $s('script-path').addEventListener('input',()=>{clearTimeout(timer);timer=setTimeout(()=>reload(),260);});
 $s('script-blur').onchange=()=>{list.classList.toggle('blur-tr',$s('script-blur').checked);store.set('jp-reader-script-blur',$s('script-blur').checked);};
 $s('script-filter-toggle').onclick=()=>{const f=$s('script-filters');f.hidden=!f.hidden;$s('script-filter-toggle').setAttribute('aria-expanded',String(!f.hidden));};
 const jump=()=>{const n=Number($s('script-jump').value);if(n>0)reload(n);};
 $s('script-jump-go').onclick=jump;$s('script-jump').addEventListener('keydown',e=>{if(e.key==='Enter')jump();});
 pick.onchange=()=>switchScript(pick.value);
 $s('script-match').onchange=async()=>{try{await api('script/match',{mode:$s('script-match').value});$s('script-match-status').textContent='套用中…';setTimeout(loadList,2500);}catch(e){$s('script-match-status').textContent=e.message;}};
 // Ctrl+K jumps to the script search, like the standalone viewer.
 document.addEventListener('keydown',e=>{
  if(scriptTab.hidden||!(e.ctrlKey||e.metaKey)||e.altKey||e.key.toLowerCase()!=='k')return;
  e.preventDefault();setView('script');q.focus();q.select();
 });
 // Mark taken over by the reading card: link a script-matched line back to its place in the script.
 const back=E('button');back.type='button';back.className='script-link';back.hidden=true;
 back.onclick=()=>window.readerScript.open(back.dataset.key);
 $('latestmeta').after(back);
 window.addEventListener('reader-current',e=>{
  const key=e.detail?.source_id||'';back.hidden=!(key.includes('|')&&scripts.length);back.dataset.key=key;
  back.innerHTML=icon('book')+'<span>在台本中查看前後文</span>';
 });

 async function loadList(preferred){
  try{
   const data=await api('script/list');scripts=data.scripts||[];
   scriptTab.hidden=false;
   pick.replaceChildren(...scripts.map(s=>{const o=E('option',s.title);o.value=s.id;return o;}));pick.hidden=false;pick.disabled=!scripts.length;
   if(!scripts.length){const o=E('option','尚未載入台本');o.value='';pick.append(o);}
   const match=$s('script-match');for(const o of [...match.options].slice(2))o.remove();
   for(const s of scripts){const o=E('option','《'+s.title+'》');o.value=s.id;match.append(o);}
   match.value=data.match?.mode||'auto';
   $s('script-match-status').textContent=data.match?.status||'';
   if(preferred&&scripts.some(s=>s.id===preferred))script=preferred;
   if(!scripts.some(s=>s.id===script))script=scripts[0]?.id||'';
   store.set('jp-reader-script-id',script);activeN=positions[script]||1;
   pick.value=script;drawKinds();
   const info=scripts.find(s=>s.id===script);
   q.placeholder=info?`搜尋《${info.title}》· JA / EN / 繁中 …  (Ctrl+K)`:q.placeholder;
   if(store.get('jp-reader-view','read')==='script'&&scripts.length&&panel.dataset.view!=='script')setView('script');
   if(!scripts.length)reload();
  }catch(e){$s('script-import-status').textContent='無法讀取台本清單：'+e.message;}
 }
 const importButton=$s('script-import'),fileInput=$s('script-file'),importStatus=$s('script-import-status');
 importButton.onclick=()=>fileInput.click();
 fileInput.onchange=async()=>{
  const file=fileInput.files[0];if(!file)return;
  rememberPosition();
  importButton.disabled=true;importStatus.textContent='正在檢查與載入台本…';
  try{
   if(file.size>64*1024*1024)throw Error('檔案超過 64 MiB，請分成不同章節的台本。');
   let data;try{data=JSON.parse((await file.text()).replace(/^\uFEFF/,''));}catch{throw Error('JSON 格式無效。請使用 UTF-8 JSON；可先下載範例。');}
   const result=await api('script/import',data);
   await loadList(result.script.id);
   q.value='';$s('script-path').value='';$s('script-need').value='';$s('script-annotated').checked=false;
   kinds=new Set(Object.keys(KIND));drawKinds();await reload(1);
   importStatus.textContent='已載入《'+result.script.title+'》 · '+result.script.rows.toLocaleString()+' 句；已儲存在本機，可隨時切換。';
  }catch(e){importStatus.textContent=e.message;}
  finally{fileInput.value='';importButton.disabled=false;}
 };
 $s('script-template').onclick=async()=>{
  try{
   const data=await api('script/template'),url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}));
   const a=E('a');a.href=url;a.download='script-template.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  }catch(e){importStatus.textContent=e.message;}
 };
 addEventListener('pagehide',rememberPosition);
 panel.dataset.view='read';readTab.setAttribute('aria-selected','true');
 loadList();
})();
