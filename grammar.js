// 文法 · Grammar view: your own lesson pages (總目錄 + lessons) inside the reading card,
// beside the dictionary. Selecting a word in a lesson looks it up, furigana left out.
(() => {
 const views=window.readerViews;
 if(!views)return;
 const icon=name=>window.readerIcon?readerIcon(name):'';
 const store={get(k,d){try{const v=localStorage.getItem(k);return v===null?d:JSON.parse(v);}catch{return d;}},set(k,v){try{localStorage.setItem(k,JSON.stringify(v));}catch{}}};
 // Scroll positions change constantly, so they stay in this browser instead of the portable preferences.
 const MEMORY='reader-grammar-pages-v1';
 const memory=new Map(Object.entries(store.get(MEMORY,{})||{}));
 const saveMemory=()=>{const recent=[...memory.entries()].slice(-80);store.set(MEMORY,Object.fromEntries(recent));};

 // ------------------------------------------------------------- view skeleton
 const view=E('div');view.id='grammar-view';
 view.innerHTML=`
  <div class="grammar-bar">
   <span class="grammar-nav">
    <button id="grammar-back" type="button" class="icon-button" title="上一頁 · Back" aria-label="Back" disabled></button>
    <button id="grammar-forward" type="button" class="icon-button" title="下一頁 · Forward" aria-label="Forward" disabled></button>
   </span>
   <button id="grammar-home" type="button" title="回總目錄（回到上次的位置）· Index"><span>目錄</span></button>
   <select id="grammar-pick" aria-label="講義集 · Lesson collection" hidden></select>
   <span id="grammar-title" class="grammar-title"></span>
   <span class="grammar-zoom" role="group" aria-label="講義字級 · Lesson text size">
    <button id="grammar-zoom-out" type="button" title="縮小字級">A−</button><button id="grammar-zoom-reset" type="button" title="恢復 100%">100%</button><button id="grammar-zoom-in" type="button" title="放大字級">A＋</button>
   </span>
   <label class="grammar-follow" title="講義配色跟隨閱讀器主題；取消則顯示講義原本的樣式"><input id="grammar-follow" type="checkbox"> 跟隨主題</label>
   <button id="grammar-folders-toggle" type="button" class="icon-button" title="講義資料夾 · Lesson folders" aria-label="Lesson folders" aria-expanded="false"></button>
  </div>
  <div id="grammar-setup" class="grammar-setup" hidden>
   <p class="grammar-setup-lead"><b>把文法講義放進閱讀器</b><span>選取講義裡的單字就會在右邊辭典查詢，假名注音不會被選進去。</span></p>
   <p class="muted">貼上放「總目錄」和 <code>lessons</code> 的那一層資料夾（例如 <code>C:\\Users\\你\\Desktop\\New folder\\JLPT文法</code>）。路徑會記在閱讀器資料夾的 <code>grammar_root.txt</code>，不會進 Git；講義檔案本身不會被修改。</p>
   <div class="grammar-add">
    <input id="grammar-path" type="text" spellcheck="false" autocomplete="off" placeholder="C:\\…\\JLPT文法" aria-label="講義資料夾路徑">
    <button id="grammar-add" type="button" class="primary">加入 · Add</button>
   </div>
   <p id="grammar-status" class="muted" role="status"></p>
   <ul id="grammar-folders" class="grammar-folders"></ul>
  </div>
  <iframe id="grammar-frame" title="文法講義 · Grammar lessons" hidden></iframe>`;
 const $g=id=>view.querySelector('#'+id);
 const frame=$g('grammar-frame'),pick=$g('grammar-pick'),title=$g('grammar-title'),setup=$g('grammar-setup'),status=$g('grammar-status');
 const back=$g('grammar-back'),forward=$g('grammar-forward'),follow=$g('grammar-follow'),foldersToggle=$g('grammar-folders-toggle');
 back.innerHTML=icon('left');forward.innerHTML=icon('right');foldersToggle.innerHTML=icon('list');
 $g('grammar-home').insertAdjacentHTML('afterbegin',icon('book'));

 let collections=[],current=null,loaded=false,loading=null,restoreNext=false,stack=[],at=-1,pendingOpen=null;
 let zoom=Number(store.get('jp-reader-grammar-zoom',100))||100;
 follow.checked=store.get('jp-reader-grammar-follow',true)!==false;

 // ------------------------------------------------------------- colours (跟隨主題)
 const valid=v=>/^#[0-9a-f]{6}$/i.test(String(v||'').trim());
 const rgb=h=>[1,3,5].map(i=>parseInt(h.slice(i,i+2),16));
 const mix=(a,b,t)=>'#'+rgb(a).map((v,i)=>Math.round(v*(1-t)+rgb(b)[i]*t).toString(16).padStart(2,'0')).join('');
 const lum=h=>{const c=rgb(h).map(v=>{v/=255;return v<=.04045?v/12.92:((v+.055)/1.055)**2.4;});return .2126*c[0]+.7152*c[1]+.0722*c[2];};
 const contrast=(a,b)=>{const x=lum(a),y=lum(b);return (Math.max(x,y)+.05)/(Math.min(x,y)+.05);};
 const legible=(color,bg,toward,min)=>{let c=color;for(let i=0;i<16&&contrast(c,bg)<min;i++)c=mix(c,toward,.12);return c;};
 const VARS=['--paper','--paper-2','--card','--ink','--muted','--faint','--line','--line-soft','--indigo','--indigo-soft','--lv','--lvbg',
  '--n5','--n4','--n3','--n2','--n1','--n5bg','--n4bg','--n3bg','--n2bg','--n1bg','--r-rt','--r-mark','--r-mean','--r-ok','--r-on-level'];
 function originals(doc){
  if(doc.__readerOriginal)return doc.__readerOriginal;
  const style=getComputedStyle(doc.documentElement),found={};
  for(const name of ['--lv','--n5','--n4','--n3','--n2','--n1']){const v=style.getPropertyValue(name).trim();if(valid(v))found[name]=v.toLowerCase();}
  return doc.__readerOriginal=found;
 }
 function colours(doc){
  const p=window.readerTheme?.palette;
  if(!p||!valid(p.card)||!valid(p.ink))return null;
  const dark=p.mode==='dark',page=p.card.toLowerCase(),ink=p.ink.toLowerCase(),white='#ffffff';
  const box=dark?mix(page,white,.06):mix(page,white,.55);
  const link=valid(window.readerTheme.entryColors?.().link)?window.readerTheme.entryColors().link:(p.accentText||ink);
  const levelOn=bg=>dark?legible(mix(bg,white,.3),box,white,4.5):legible(bg,box,ink,3.6);
  const o=originals(doc),out={};
  Object.assign(out,{
   '--paper':page,'--paper-2':mix(page,ink,dark?.1:.06),'--card':box,'--ink':ink,
   '--muted':mix(ink,page,.36),'--faint':mix(ink,page,.55),'--line':mix(ink,page,.78),'--line-soft':mix(ink,page,.86),
   '--indigo':legible(link,box,dark?white:ink,4.6),'--r-mean':mix(ink,page,.18),'--r-on-level':dark?'#1b1916':'#ffffff'
  });
  out['--indigo-soft']=mix(out['--indigo'],box,.85);
  for(const n of ['--n5','--n4','--n3','--n2','--n1'])if(o[n]){out[n]=levelOn(o[n]);out[n+'bg']=mix(o[n],box,dark?.8:.88);}
  const level=o['--lv']||null;
  if(level){out['--lv']=levelOn(level);out['--lvbg']=mix(level,box,dark?.8:.9);}
  const hue=level||(valid(p.accentText)?p.accentText:ink);
  out['--r-rt']=legible(dark?mix(hue,white,.35):mix(hue,page,.12),page,dark?white:ink,3.4);
  out['--r-mark']=mix(level||(valid(p.accent3)?p.accent3:hue),page,dark?.72:.78);
  out['--r-ok']=out['--n5']||legible('#2e7d4f',box,dark?white:ink,4.2);
  return {vars:out,mode:dark?'dark':'light'};
 }
 function prepare(doc){
  const root=doc?.documentElement;if(!root)return;
  root.style.zoom=zoom===100?'':String(zoom/100);
  const theme=follow.checked?colours(doc):null;
  if(!theme){for(const k of VARS)root.style.removeProperty(k);delete root.dataset.readerTheme;root.style.colorScheme='';return;}
  originals(doc);
  for(const [k,v] of Object.entries(theme.vars))root.style.setProperty(k,v);
  root.dataset.readerTheme=theme.mode;root.style.colorScheme=theme.mode;
 }
 window.readerGrammar={prepare};
 let themeSignature='',themeFrame=0;
 new MutationObserver(()=>{if(!themeFrame)themeFrame=requestAnimationFrame(()=>{themeFrame=0;const p=window.readerTheme?.palette;const sig=p?[p.card,p.ink,p.mode,p.accentText,p.accent2].join():'';if(sig===themeSignature)return;themeSignature=sig;const doc=frameDoc();if(doc)prepare(doc);});})
  .observe(document.documentElement,{attributes:true,attributeFilter:['style','data-preset','data-mode']});
 follow.onchange=()=>{store.set('jp-reader-grammar-follow',follow.checked);const doc=frameDoc();if(doc)prepare(doc);};
 function setZoom(value){zoom=Math.max(70,Math.min(220,Math.round(value/5)*5));store.set('jp-reader-grammar-zoom',zoom);$g('grammar-zoom-reset').textContent=zoom+'%';const doc=frameDoc();if(doc)prepare(doc);}
 $g('grammar-zoom-out').onclick=()=>setZoom(zoom-10);$g('grammar-zoom-in').onclick=()=>setZoom(zoom+10);$g('grammar-zoom-reset').onclick=()=>setZoom(100);
 $g('grammar-zoom-reset').textContent=zoom+'%';

 // ------------------------------------------------------------- collections & navigation
 const pathKey=path=>{try{return new URL(path,location.href).pathname.replace(/^\/grammar\/\d+\//,'');}catch{return '';}};
 const relative=url=>{try{const u=new URL(url,location.href),m=u.pathname.match(/^\/grammar\/(\d+)\/(.*)$/);return m?{id:m[1],rest:m[2]+u.search+u.hash}:null;}catch{return null;}};
 const pageKey=url=>{try{const u=new URL(url,location.href);return u.pathname+u.search;}catch{return url;}};
 function frameDoc(){try{const doc=frame.contentDocument;return doc&&frame.contentWindow.location.pathname.startsWith('/grammar/')?doc:null;}catch{return null;}}
 function lastPages(){return store.get('jp-reader-grammar-last',{})||{};}
 function go(url,{remember=true}={}){
  if(!url)return;
  restoreNext=remember;
  frame.hidden=false;
  try{if(frame.contentWindow&&frame.getAttribute('src')){frame.contentWindow.location.replace(url);return;}}catch{}
  frame.src=url;
 }
 function choose(id,{open=true}={}){
  current=collections.find(c=>c.id===id)||collections[0]||null;
  pick.value=current?current.id:'';
  if(current)store.set('jp-reader-grammar-collection',current.path);
  stack=[];at=-1;updateNav();
  if(!open||!current)return;
  const saved=lastPages()[current.path];
  go(saved?current.base+saved:current.home);
 }
 async function load(){
  if(loading)return loading;
  loading=(async()=>{
   try{
    const data=await api('grammar/list');
    collections=(data.collections||[]).map(c=>({...c,base:'/grammar/'+c.id+'/'}));
    $g('grammar-path').placeholder=collections[0]?.path||'C:\\…\\JLPT文法';
    drawFolders(data.root_file);
    pick.replaceChildren(...collections.map(c=>{const o=E('option',c.title);o.value=c.id;return o;}));
    pick.hidden=collections.length<2;
    if(!collections.length){current=null;frame.hidden=true;showSetup(true);title.textContent='尚未設定講義資料夾';return;}
    const wanted=store.get('jp-reader-grammar-collection','');
    const requested=pendingOpen&&relative(pendingOpen);
    choose(requested?.id||collections.find(c=>c.path===wanted)?.id||collections[0].id,{open:!requested});
    if(requested){go(pendingOpen,{remember:false});pendingOpen=null;}
    loaded=true;
   }catch(e){status.textContent='無法讀取講義清單：'+e.message;showSetup(true);}
   finally{loading=null;}
  })();
  return loading;
 }
 function drawFolders(rootFile){
  const list=$g('grammar-folders');list.replaceChildren();
  for(const c of collections){
   const li=E('li'),name=E('b',c.title),path=E('code',c.path),count=E('small',c.pages+' 頁');
   li.append(name,count,path);list.append(li);
  }
  if(rootFile){const li=E('li');li.className='grammar-root-file';li.append(E('small','移除或改順序：編輯 '),E('code',rootFile));list.append(li);}
 }
 function showSetup(show){setup.hidden=!show;foldersToggle.setAttribute('aria-expanded',String(show));window.dispatchEvent(new Event('reader-layout'));}
 foldersToggle.onclick=()=>showSetup(setup.hidden);
 pick.onchange=()=>choose(pick.value);
 $g('grammar-add').onclick=async()=>{
  const value=$g('grammar-path').value.trim();
  if(!value){status.textContent='請先貼上資料夾路徑。';$g('grammar-path').focus();return;}
  $g('grammar-add').disabled=true;status.textContent='正在檢查資料夾…';
  try{
   const result=await api('grammar/root',{path:value});
   $g('grammar-path').value='';
   await load();choose(result.added.id);
   status.textContent='已加入《'+result.added.title+'》 · '+result.added.pages+' 頁。';
   if(collections.length)showSetup(false);
  }catch(e){status.textContent=e.message;}
  finally{$g('grammar-add').disabled=false;}
 };
 $g('grammar-path').addEventListener('keydown',e=>{if(e.key==='Enter')$g('grammar-add').click();});
 $g('grammar-home').onclick=()=>{if(current)go(current.home);else showSetup(true);};
 back.onclick=()=>{if(at>0)go(stack[at-1]);};
 forward.onclick=()=>{if(at<stack.length-1)go(stack[at+1]);};
 function updateNav(){back.disabled=at<=0;forward.disabled=at>=stack.length-1;}
 // Returns true when this load came from moving back or forward.
 function track(url){
  if(stack[at]===url)return true;
  if(at>0&&stack[at-1]===url){at--;updateNav();return true;}
  if(stack[at+1]===url){at++;updateNav();return true;}
  stack=stack.slice(0,at+1);stack.push(url);at=stack.length-1;
  if(stack.length>200){stack.shift();at--;}
  updateNav();return false;
 }

 // ------------------------------------------------------------- remembering where you were
 function snapshot(doc,win){
  const key=pageKey(win.location.href),tab=doc.querySelector('.tab.on')?.dataset?.lv,q=doc.getElementById('q');
  memory.delete(key);memory.set(key,{y:Math.round(win.scrollY),tab:tab||'',q:q&&q.matches('input')?q.value:''});
 }
 function restore(doc,win,state){
  if(!state)return;
  const q=doc.getElementById('q');
  if(q&&q.matches('input[type=search]')&&state.q){q.value=state.q;q.dispatchEvent(new Event('input',{bubbles:true}));}
  else if(state.tab){const tab=doc.querySelector('.tab[data-lv="'+CSS.escape(state.tab)+'"]');if(tab&&!tab.classList.contains('on'))tab.click();}
  const top=state.y||0;
  const apply=()=>win.scrollTo({top,left:0,behavior:'instant'});
  apply();requestAnimationFrame(apply);setTimeout(apply,120);
 }

 // ------------------------------------------------------------- each lesson page
 frame.addEventListener('load',()=>{
  let win,doc;
  try{win=frame.contentWindow;doc=frame.contentDocument;}catch{return;}
  if(!win||!doc||win.location.href==='about:blank')return;
  if(!win.location.pathname.startsWith('/grammar/')){title.textContent='（不是講義頁）';return;}
  prepare(doc);
  window.readerDictionary?.attach(doc);
  if(window.readerShortcutKeydown)doc.addEventListener('keydown',window.readerShortcutKeydown);
  // Links that leave your lesson folder open in a normal browser tab.
  doc.addEventListener('click',event=>{
   const link=event.target.closest?.('a[href]');if(!link||event.defaultPrevented)return;
   let url;try{url=new URL(link.getAttribute('href'),win.location.href);}catch{return;}
   if(url.protocol==='javascript:')return;
   if(url.origin!==location.origin||!url.pathname.startsWith('/grammar/')){event.preventDefault();window.open(url.href,'_blank','noopener');}
  });
  const key=pageKey(win.location.href);
  const moved=track(key);
  const info=relative(win.location.href);
  if(info&&current&&info.id!==current.id){const other=collections.find(c=>c.id===info.id);if(other){current=other;pick.value=other.id;store.set('jp-reader-grammar-collection',other.path);}}
  if(info&&current){const last=lastPages();last[current.path]=info.rest.replace(/#.*$/,'');store.set('jp-reader-grammar-last',last);}
  const full=doc.title||decodeURIComponent(pathKey(win.location.href)).replace(/\.html?$/i,'');
  title.textContent=full.split('｜').slice(0,2).join('｜');title.title=full;
  if(restoreNext||moved)restore(doc,win,memory.get(key));
  restoreNext=false;
  let timer;
  const remember=()=>{clearTimeout(timer);timer=setTimeout(()=>{try{snapshot(doc,win);saveMemory();}catch{}},250);};
  win.addEventListener('scroll',remember,{passive:true});
  doc.addEventListener('click',remember);doc.addEventListener('input',remember);
  win.addEventListener('pagehide',()=>{try{snapshot(doc,win);saveMemory();}catch{}});
  snapshot(doc,win);
 });

 // ------------------------------------------------------------- tab
 views.add('grammar','<span lang="ja">文法</span><small>Grammar</small>',view,{
  onShow(){if(!loaded)load();}
 });
 // A lesson opened in its own browser tab links back here: /#grammar=/grammar/0/lessons/…
 const hash=location.hash.match(/^#grammar=(.+)$/);
 if(hash){
  try{pendingOpen=decodeURIComponent(hash[1]);}catch{}
  history.replaceState(null,'',location.pathname+location.search);
  if(pendingOpen&&!pendingOpen.startsWith('/grammar/'))pendingOpen=null;
  if(pendingOpen){if(loaded){const r=relative(pendingOpen);if(r)choose(r.id,{open:false});go(pendingOpen,{remember:false});pendingOpen=null;}views.set('grammar');}
 }
})();
