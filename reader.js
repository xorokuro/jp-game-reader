// A single editable Japanese block for pasted and recognized text.
(() => {
 const reading=$('latest'),status=$('paste-status');
 reading.contentEditable='false';reading.tabIndex=0;reading.setAttribute('aria-readonly','true');reading.setAttribute('role','textbox');reading.setAttribute('aria-multiline','true');reading.spellcheck=false;
 reading.setAttribute('aria-label','Japanese text — select words to look them up');
 const bar=E('div');bar.className='toolbar reader-inputs';
 const paste=E('button'),save=E('button');paste.innerHTML=(window.readerIcon?readerIcon('paste'):'')+'<span>貼上文字 · Paste</span>';save.innerHTML=(window.readerIcon?readerIcon('save'):'')+'<span>儲存 · Save</span>';save.title='Save text / corrections';
 const editLabel=E('label'),editToggle=E('input');editToggle.type='checkbox';editToggle.id='edit-reading-text';
 editLabel.append(editToggle,document.createTextNode(' 編輯 · Edit text'));
 editToggle.onchange=()=>{
  reading.contentEditable=editToggle.checked?'plaintext-only':'false';
  reading.setAttribute('aria-readonly',String(!editToggle.checked));
  status.textContent=editToggle.checked?'Editing enabled. Save to keep your changes.':'Select a word to search. Check Edit text to type or correct this passage.';
  if(editToggle.checked)reading.focus({preventScroll:true});
 };
 bar.append(paste,save,editLabel);reading.before(bar);
 const restore=E('button','Restore previous draft');restore.type='button';restore.hidden=true;bar.append(restore);
 let previousDraft=null;
 window.addEventListener('reader-resume-capture',()=>{
  if(reading.dataset.dirty==='true'&&currentRecord){previousDraft={...currentRecord,japanese:reading.innerText};restore.hidden=false;}
  editToggle.checked=false;reading.contentEditable='false';reading.setAttribute('aria-readonly','true');
  status.textContent='Returning to captured text. Your previous draft can be restored.';
 });
 restore.onclick=()=>action(()=>{
  if(dirty())throw Error('Save your current edits before restoring the previous draft.');
  if(!previousDraft)return;
  following=false;navSeq=null;showCurrent(previousDraft);changed();
  previousDraft=null;restore.hidden=true;
 });
 for(const button of [paste,save])button.type='button';
 const saveLabel=E('label'),saveToggle=E('input');saveToggle.type='checkbox';saveToggle.id='capture-auto-save';saveToggle.disabled=true;
 saveLabel.append(saveToggle,document.createTextNode(' Automatically save new captured text'));
 document.querySelector('.panel-status').append(saveLabel);
 function changed(){
  const text=reading.innerText;
  following=false;navSeq=null;startupBlank=false;
  currentRecord={...(currentRecord||{id:-Date.now(),kind:'manual',temporary:true,note:''}),japanese:text,english:'',traditional_chinese:'',localDraft:true};currentId=currentRecord.id;
  reading.dataset.dirty='true';rememberPin();updateNavigation();
  $('latestenglish').textContent='Text changed — save before translating again.';$('latestchinese').textContent='原文已修改，儲存後可重新翻譯。';
  $('currentimport').replaceChildren();currentImportId=null;
  $('latestmeta').textContent='Unsaved edits · save to keep your corrections';
  status.textContent='Editing this text. New capture will not overwrite your changes.';
 }
 reading.addEventListener('input',changed);
 reading.addEventListener('beforeinput',event=>{
  if(!editToggle.checked){event.preventDefault();return;}
  if(event.isComposing||!event.data)return;
  if(reading.innerText.length+event.data.length-(window.getSelection()?.toString().length||0)>12000){event.preventDefault();status.textContent='Keep each passage under 12,000 characters.';}
 });
 reading.addEventListener('paste',event=>{
  if(!editToggle.checked)return; // Let the dictionary handle paste in read-only mode.
  event.preventDefault();event.stopPropagation();
  const text=event.clipboardData?.getData('text/plain')||'';
  if(reading.innerText.length+text.length-(window.getSelection()?.toString().length||0)>12000){status.textContent='Keep each passage under 12,000 characters.';return;}
  document.execCommand('insertText',false,text);
 });
 paste.onclick=()=>action(async()=>{
  if(dirty())throw Error('Save your edits before opening a new passage.');
  let text;
  try{text=await navigator.clipboard.readText();}catch{status.textContent='Check Edit text, then paste into the Japanese block with Ctrl+V.';return;}
  if(!text.trim()||text.length>12000)throw Error('Paste between 1 and 12,000 characters.');
  following=false;navSeq=null;
  showCurrent({id:-Date.now(),kind:'manual',temporary:true,japanese:text,note:'',english:'',traditional_chinese:''});
  changed();reading.focus({preventScroll:true});
 });
 save.onclick=()=>action(async()=>{
  const original=currentRecord;
  if(!original?.japanese?.trim())throw Error('Enter Japanese text first.');
  if(original.japanese.length>12000)throw Error('Keep each passage under 12,000 characters.');
  save.disabled=true;
  try{
   let row;
   const translations=original.english||original.traditional_chinese?{english:original.english||'',traditional_chinese:original.traditional_chinese||''}:null;
   if(original.id>0){
    await api('edit',{id:original.id,japanese:original.japanese,...(original.localDraft?{english:'',traditional_chinese:''}:{})});
    row=await api('sentence?id='+original.id);
   }else{
    row=(await api('add',{japanese:original.japanese,save:true,temporary_id:!original.localDraft?original.id:undefined})).row;
    if(translations&&!row.english&&original.kind==='script'){await api('edit',{id:row.id,...translations});row=await api('sentence?id='+row.id);}
   }
   if(currentRecord===original){reading.dataset.dirty='false';following=false;navSeq=null;showCurrent(row);rememberPin();status.textContent='Saved. Select words to look them up. Check Edit text to make corrections.';}
   await loadPage();
  }finally{save.disabled=false;}
 });
 saveToggle.onchange=()=>action(async()=>{
  const requested=saveToggle.checked;saveToggle.disabled=true;
  try{saveToggle.checked=(await api('save-text',{enabled:requested})).enabled;}catch(error){saveToggle.checked=!requested;throw error;}finally{saveToggle.disabled=false;}
 });
 api('state').then(async state=>{saveToggle.checked=state.capture_enabled&&!state.save_text?(await api('save-text',{enabled:true})).enabled:state.save_text;saveToggle.disabled=false;}).catch(error=>status.textContent=error.message);
 status.textContent='Select a word to search. Use Paste text, or check Edit text to type or correct this passage.';
 // Retire the duplicate manual-entry block; keep its IDs for older app bindings.
 $('manual').closest('details').hidden=true;
})();

// Input source selection is independent of the current passage and dictionary state.
(() => {
  const bar=E('div');bar.className='toolbar input-source';
  const label=E('label','Read from '),mode=E('select');mode.id='input-source';mode.setAttribute('aria-label','Reading input');
  for(const [value,text] of [['paste','Pasted text'],['obs','OBS projector'],['window','Game window']]){const option=E('option',text);option.value=value;mode.append(option);}
  label.append(mode);
  const windows=E('select');windows.id='capture-window';windows.setAttribute('aria-label','Game window');
  const refresh=E('button','Refresh windows'),apply=E('button','Use this source'),hint=E('p');hint.className='muted';hint.setAttribute('role','status');
  for(const b of [refresh,apply])b.type='button';
  bar.append(label,windows,refresh,apply);document.querySelector('.panel-status').prepend(bar,hint);
  let targets=[],activeMode='paste';
  function showSource(){
    windows.hidden=refresh.hidden=mode.value!=='window';
    hint.textContent=mode.value==='paste'?'Paste, read and look up words without OBS or a running game.':mode.value==='obs'?'Keep the OBS projector visible. Capture uses OCR; it does not read game memory.':'Choose a visible game window. Keep its dialogue uncovered. Use OBS if the game cannot be captured directly.';
  }
  function applyMode(value){
    activeMode=value;document.body.dataset.inputMode=value;
    for(const id of ['pause','retry-ocr','retry-full-ocr','obs-settings','obs-batch'])if($(id))$(id).hidden=value==='paste';
  }
  async function listWindows(selected){
    const result=await api('capture-sources');targets=result.windows;windows.replaceChildren();
    for(const row of targets){const option=E('option',row.process+' · '+row.title);option.value=String(row.handle);windows.append(option);}
    if(selected&&targets.some(row=>row.handle===selected))windows.value=String(selected);
    if(!targets.length){const option=E('option','No visible windows — open the game and refresh');option.value='';windows.append(option);}
  }
  refresh.onclick=()=>action(()=>listWindows(Number(windows.value)));
  mode.onchange=()=>{showSource();if(mode.value==='window')action(()=>listWindows());};
  apply.onclick=()=>action(async()=>{
    apply.disabled=true;
    try{
      const target=targets.find(row=>String(row.handle)===windows.value);
      const result=await api('capture-source',{mode:mode.value,handle:target?.handle,pid:target?.pid});
      const saving=await api('save-text',{enabled:result.settings.capture_mode!=='paste'});
      $('capture-auto-save').checked=saving.enabled;
      paused=true;applyMode(result.settings.capture_mode);showSource();
      hint.textContent=activeMode==='paste'?'Ready for pasted text. Capture is paused.':'Source selected. Press Recognize when ready, or enable automatic recognition.';
    }finally{apply.disabled=false;}
  });
  api('state').then(async state=>{mode.value=state.settings.capture_mode||'paste';applyMode(mode.value);showSource();if(mode.value==='window')await listWindows(state.settings.window_handle);}).catch(error=>hint.textContent=error.message);
})();

// Reading first: reader and dictionary side by side, setup tiles below.
(() => {
 const icon=name=>window.readerIcon?readerIcon(name):'';
 const shell=document.querySelector('main.shell'),workspace=$('reader-workspace'),dictionary=$('dictionary-panel');
 const quick=document.querySelector('[aria-label="Quick dictionary search"]');
 quick.querySelector('h2')?.remove();
 quick.className='dictionary-quick-search';dictionary.querySelector('.dict-head').after(quick);
 $('paste-status').after($('message'),$('retry-message'));
 // Recognition controls and status live in the sticky top bar.
 $('capture-actions').prepend($('retry-ocr'),$('retry-full-ocr'));
 $('topbar-status').append($('status'));
 const source=document.querySelector('.panel-status');
 const tiles=new Map([
  [source,['gamepad','來源與擷取','Source & capture']],
  [document.querySelector('[aria-label="Translation and dictionary"]'),['globe','翻譯引擎','Translation']],
  [document.querySelector('[aria-label="Journal actions"]'),['save','儲存與匯出','Journal & export']],
  [$('ocr-review'),['spark','待確認台詞','OCR to review']]
 ]);
 function summaryContent(summary,[name,zh,en]){summary.innerHTML='<span class="tile-icon">'+icon(name)+'</span><span class="tile-title"><b></b><small></small></span>';summary.querySelector('b').textContent=zh;summary.querySelector('small').textContent=en;}
 function disclosure(host,info,open=false){
  const box=E('details'),summary=E('summary');box.className='settings-disclosure';box.open=open;summaryContent(summary,info);
  const children=[...host.childNodes];box.append(summary,...children);host.append(box);return box;
 }
 for(const host of [...shell.children]){
  if(host.tagName!=='SECTION'||host===workspace||host.classList.contains('current'))continue;
  const heading=host.querySelector(':scope > h2');
  const info=tiles.get(host)||['note',heading?.textContent||host.getAttribute('aria-label')||'Settings',''];
  if(heading)heading.remove();disclosure(host,info,host.id==='ocr-review');
 }
 for(const [id,info] of [['history',['book','收藏與歷史','Your collection']],['obs-settings',['crop','擷取範圍','Capture area']],['promptbox',['note','準備好的 prompt','Prepared prompt']],['obs-batch',['basket','整段收集','Collect a scene']]]){
  const summary=$(id)?.querySelector(':scope > summary');if(summary)summaryContent(summary,info);
 }
 // Reading card header.
 const readingPanel=workspace.querySelector('section.current');
 const heading=readingPanel.querySelector(':scope > h2');
 const head=E('div');head.className='card-head';
 const title=E('h2');title.className='hand-title';title.innerHTML='<span lang="ja">読む</span><small>Reading · 日文 / English / 繁體中文</small>';
 head.append(title,$('reader-mode'));heading.replaceWith(head);
 const nav=readingPanel.querySelector('.reading-nav');
 $('sentence-prev').innerHTML=icon('left')+'<span>上一句</span>';$('sentence-next').innerHTML='<span>下一句</span>'+icon('right');
 head.append(nav);
 dictionary.hidden=false;
 if(!$('dict-tabs').querySelector('.dict-tab'))$('dict-entries').textContent='';
 for(const [id,label] of [['latestenglish','English'],['latestchinese','繁體中文']]){
  const text=$(id),h=text.previousElementSibling;
  if(h?.tagName==='H2'){const group=E('details'),summary=E('summary',label);group.className='translation-disclosure';group.dataset.lang=id==='latestenglish'?'en':'zh';group.open=true;h.before(group);group.append(summary,text);h.remove();}
 }
 const chatToggle=[...readingPanel.querySelectorAll('label')].find(label=>label.textContent.includes('Temporary Chat'));
 if(chatToggle){const options=E('details'),summary=E('summary','Chat options');options.className='chat-options';options.append(summary,chatToggle);currentSend.after(options);}
 currentSend.classList.add('send-row');
 $('copy-current-japanese').innerHTML=icon('paste')+'<span>複製日文</span>';
 // Setup tiles sit in a tidy grid beneath the workspace; opened ones span the full width.
 const grid=E('div');grid.className='settings-grid';
 const footer=shell.querySelector(':scope > footer');
 grid.append(...[...shell.children].filter(node=>node!==workspace&&node!==footer));
 const review=grid.querySelector('#ocr-review');if(review)grid.prepend(review);
 const gridTitle=E('h2');gridTitle.className='hand-title section-title';gridTitle.innerHTML='<span lang="ja">道具箱</span><small>Tools &amp; settings</small>';
 workspace.after(gridTitle,grid);
 shell.prepend(workspace);

 // Keep the dictionary's definition area level with the reading text, and let it fill the window.
 const latest=$('latest'),body=dictionary.querySelector('.dict-body');
 const leftPad=E('div'),rightPad=E('div');leftPad.className=rightPad.className='align-spacer';leftPad.setAttribute('aria-hidden','true');rightPad.setAttribute('aria-hidden','true');
 latest.before(leftPad);body.before(rightPad);
 const topbar=$('topbar');
 let frame=0;
 function align(){
  frame=0;
  document.documentElement.style.setProperty('--topbar-h',Math.round(topbar.getBoundingClientRect().height)+'px');
  const sideBySide=!dictionary.hidden&&getComputedStyle(workspace).gridTemplateColumns.trim().split(/\s+/).length>1;
  if(!sideBySide||readingPanel.dataset.view==='script'){leftPad.style.height=rightPad.style.height='0px';return;}
  // While the search row is tucked away, keep the reading text where it is.
  if(dictionary.classList.contains('search-tucked'))return;
  const leftHead=latest.getBoundingClientRect().top-readingPanel.getBoundingClientRect().top-leftPad.offsetHeight;
  const rightHead=body.getBoundingClientRect().top-dictionary.getBoundingClientRect().top-rightPad.offsetHeight;
  const delta=Math.round(leftHead-rightHead);
  const l=Math.max(0,-delta)+'px',r=Math.max(0,delta)+'px';
  if(leftPad.style.height!==l)leftPad.style.height=l;
  if(rightPad.style.height!==r)rightPad.style.height=r;
 }
 const schedule=()=>{if(!frame)frame=requestAnimationFrame(align);};
 const observer=new ResizeObserver(schedule);
 for(const node of [topbar,workspace,head,quick,dictionary.querySelector('.dict-head'),readingPanel.querySelector('.reader-inputs')])if(node)observer.observe(node);
 new MutationObserver(schedule).observe(dictionary,{attributes:true,attributeFilter:['hidden']});
 addEventListener('resize',schedule);addEventListener('reader-layout',schedule);
 document.fonts?.ready.then(schedule);schedule();
})();

// Auto-hide the dictionary search row (search box, status, recent words) while scrolling
// down a definition or the headword list; scrolling up brings it back. On by default.
(() => {
 const dictionary=$('dictionary-panel'),quick=dictionary?.querySelector('.dictionary-quick-search');
 const frame=$('dict-frame'),tabs=$('dict-tabs');
 if(!dictionary||!quick||!frame||!tabs)return;
 const KEY='jp-reader-autohide-search';
 let enabled=true;
 try{enabled=localStorage.getItem(KEY)!=='false';}catch{}
 let naturalHeight=0,quietUntil=0;
 const positions=new WeakMap();
 const quiet=ms=>{quietUntil=performance.now()+ms;};
 const tucked=()=>dictionary.classList.contains('search-tucked');
 function tuck(){
  if(tucked()||!enabled)return;
  if(quick.contains(document.activeElement))document.activeElement.blur();
  naturalHeight=quick.scrollHeight||naturalHeight;
  quick.style.maxHeight=naturalHeight+'px';void quick.offsetHeight;
  dictionary.classList.add('search-tucked');quick.setAttribute('aria-hidden','true');quiet(320);
 }
 function reveal(){
  if(!tucked())return;
  quick.style.maxHeight=(naturalHeight||400)+'px';
  dictionary.classList.remove('search-tucked');quick.removeAttribute('aria-hidden');quiet(320);
  dispatchEvent(new Event('reader-layout'));
 }
 quick.addEventListener('transitionend',event=>{if(event.target===quick&&event.propertyName==='max-height'&&!tucked())quick.style.maxHeight='';});
 // Scroll direction with a little accumulation so touchpad jitter does not flicker.
 function watch(key,y){
  const state=positions.get(key)||{y,acc:0};positions.set(key,state);
  const delta=y-state.y;state.y=y;
  if(!enabled||performance.now()<quietUntil){state.acc=0;return;}
  state.acc=(Math.sign(delta)===Math.sign(state.acc)?state.acc:0)+delta;
  if(state.acc>28&&y>40){state.acc=0;tuck();}
  else if(state.acc<-28||y<=2){state.acc=0;reveal();}
 }
 const wheelUp=event=>{if(enabled&&event.deltaY<-4&&performance.now()>=quietUntil)reveal();};
 tabs.addEventListener('scroll',()=>watch(tabs,tabs.scrollTop),{passive:true});
 tabs.addEventListener('wheel',wheelUp,{passive:true});
 frame.addEventListener('load',()=>{
  let win,doc;try{win=frame.contentWindow;doc=frame.contentDocument;}catch{return;}
  if(!win||!doc)return;
  quiet(300);positions.set(win,{y:win.scrollY,acc:0});
  win.addEventListener('scroll',()=>watch(win,win.scrollY),{passive:true});
  doc.addEventListener('wheel',wheelUp,{passive:true});
 });
 quick.addEventListener('focusin',reveal);
 addEventListener('reader-lookup',reveal);
 // Setting: one checkbox in the dictionary help popover, one in Theme › More; kept in sync.
 const boxes=[];
 function makeSetting(host){
  if(!host)return;
  const label=document.createElement('label'),box=document.createElement('input');
  label.className='dict-autohide-setting';box.type='checkbox';box.checked=enabled;
  box.onchange=()=>{
   enabled=box.checked;for(const other of boxes)other.checked=enabled;
   try{localStorage.setItem(KEY,String(enabled));}catch{}
   if(!enabled)reveal();
  };
  label.append(box,document.createTextNode(' 往下捲動時隱藏搜尋列 · Hide search bar while scrolling down'));
  host.append(label);boxes.push(box);
 }
 makeSetting(dictionary.querySelector('#dict-help .dict-pop-body'));
 makeSetting($('theme-settings'));
})();

// Workspace size: drag the bottom grip to make both panels longer, and the middle grip
// to give the dictionary more width. Double-click either grip to reset. Saved per reader.
(() => {
 const workspace=document.getElementById('reader-workspace'),dictionary=document.getElementById('dictionary-panel');
 const reading=workspace?.querySelector('section.current');
 if(!workspace||!dictionary||!reading)return;
 const KEY='jp-reader-workspace-v1',MIN_H=420,MAX_H=6000;
 let size={h:null,left:null};
 try{const saved=JSON.parse(localStorage.getItem(KEY)||'null');if(saved&&typeof saved==='object'){if(Number.isFinite(saved.h))size.h=saved.h;if(Number.isFinite(saved.left))size.left=saved.left;}}catch{}
 const save=()=>{try{localStorage.setItem(KEY,JSON.stringify(size));}catch{}};
 const tip=document.createElement('div');tip.className='ws-size-tip';tip.hidden=true;
 function apply(){
  if(size.h)workspace.style.setProperty('--ws-custom-h',Math.round(Math.max(MIN_H,Math.min(MAX_H,size.h)))+'px');else workspace.style.removeProperty('--ws-custom-h');
  if(size.left){const f=Math.max(.28,Math.min(.72,size.left));workspace.style.setProperty('--ws-left',f.toFixed(4)+'fr');workspace.style.setProperty('--ws-right',(1-f).toFixed(4)+'fr');}
  else{workspace.style.removeProperty('--ws-left');workspace.style.removeProperty('--ws-right');}
  place();dispatchEvent(new Event('reader-layout'));
 }
 const grip=(cls,label,title)=>{const b=document.createElement('button');b.type='button';b.className='ws-grip '+cls;b.setAttribute('aria-label',label);b.title=title;return b;};
 const hGrip=grip('ws-grip-h','Resize panel height','拖曳調整兩側面板高度 · 雙擊恢復填滿視窗 (↑/↓)');
 const vGrip=grip('ws-grip-v','Resize panel widths','拖曳調整左右寬度 · 雙擊恢復預設 (←/→)');
 workspace.append(hGrip,vGrip,tip);
 function place(){
  const a=reading.getBoundingClientRect(),b=dictionary.getBoundingClientRect(),w=workspace.getBoundingClientRect();
  vGrip.style.left=Math.round(a.right-w.left+(b.left-a.right)/2-13)+'px';
 }
 function showTip(text){tip.textContent=text;tip.hidden=false;clearTimeout(showTip.t);showTip.t=setTimeout(()=>tip.hidden=true,1200);}
 function drag(el,down,onMove){
  el.addEventListener('pointerdown',event=>{
   if(event.button!==0)return;event.preventDefault();el.setPointerCapture(event.pointerId);
   el.classList.add('dragging');document.body.classList.add('ws-resizing');
   const start=down(event);
   const move=e=>onMove(e,start);
   const up=()=>{el.releasePointerCapture?.(event.pointerId);el.classList.remove('dragging');document.body.classList.remove('ws-resizing');el.removeEventListener('pointermove',move);el.removeEventListener('pointerup',up);el.removeEventListener('pointercancel',up);save();};
   el.addEventListener('pointermove',move);el.addEventListener('pointerup',up);el.addEventListener('pointercancel',up);
  });
 }
 const panelHeight=()=>dictionary.getBoundingClientRect().height;
 drag(hGrip,e=>({y:e.clientY+scrollY,h:panelHeight()}),(e,s)=>{
  size.h=Math.max(MIN_H,Math.min(MAX_H,s.h+(e.clientY+scrollY-s.y)));apply();
  if(e.clientY>innerHeight-40)scrollBy(0,18);
  showTip('高度 '+Math.round(size.h)+' px · 雙擊恢復');
 });
 drag(vGrip,()=>({}),e=>{
  const w=workspace.getBoundingClientRect();size.left=Math.max(.28,Math.min(.72,(e.clientX-w.left)/w.width));apply();
  showTip('左 '+Math.round(size.left*100)+'% · 右 '+Math.round((1-size.left)*100)+'%');
 });
 hGrip.addEventListener('dblclick',()=>{size.h=null;save();apply();showTip('已恢復：填滿視窗');});
 vGrip.addEventListener('dblclick',()=>{size.left=null;save();apply();showTip('已恢復預設寬度');});
 hGrip.addEventListener('keydown',e=>{if(!['ArrowUp','ArrowDown'].includes(e.key))return;e.preventDefault();e.stopPropagation();size.h=Math.max(MIN_H,Math.min(MAX_H,(size.h||panelHeight())+(e.key==='ArrowDown'?60:-60)));save();apply();showTip('高度 '+Math.round(size.h)+' px');});
 vGrip.addEventListener('keydown',e=>{if(!['ArrowLeft','ArrowRight'].includes(e.key))return;e.preventDefault();e.stopPropagation();const w=workspace.getBoundingClientRect(),cur=size.left||reading.getBoundingClientRect().width/w.width;size.left=Math.max(.28,Math.min(.72,cur+(e.key==='ArrowRight'?.02:-.02)));save();apply();});
 new ResizeObserver(place).observe(workspace);
 new MutationObserver(place).observe(dictionary,{attributes:true,attributeFilter:['hidden']});
 addEventListener('resize',place);
 apply();
})();
