// A single editable Japanese block for pasted and recognized text.
(() => {
 const reading=$('latest'),status=$('paste-status');
 reading.contentEditable='false';reading.tabIndex=0;reading.setAttribute('aria-readonly','true');reading.setAttribute('role','textbox');reading.setAttribute('aria-multiline','true');reading.spellcheck=false;
 reading.setAttribute('aria-label','Japanese text — select words to look them up');
 const bar=E('div');bar.className='toolbar reader-inputs';
 const paste=E('button','Paste text'),save=E('button','Save text / corrections');
 const editLabel=E('label'),editToggle=E('input');editToggle.type='checkbox';editToggle.id='edit-reading-text';
 editLabel.append(editToggle,document.createTextNode(' Edit text'));
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
   if(original.id>0){
    await api('edit',{id:original.id,japanese:original.japanese,...(original.localDraft?{english:'',traditional_chinese:''}:{})});
    row=await api('sentence?id='+original.id);
   }else{
    row=(await api('add',{japanese:original.japanese,save:true,temporary_id:!original.localDraft?original.id:undefined})).row;
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

// Reading first; setup stays available below in closed disclosures.
(() => {
 const shell=document.querySelector('main.shell'),workspace=$('reader-workspace'),dictionary=$('dictionary-panel');
 const quick=document.querySelector('[aria-label="Quick dictionary search"]');
 const dictionaryToolbar=dictionary.querySelector('.dict-toolbar');
 const quickHeading=quick.querySelector('h2');if(quickHeading)quickHeading.remove();
 quick.className='dictionary-quick-search';dictionaryToolbar.after(quick);
 const hints=quick.querySelector('.muted');
 if(hints){const help=E('details'),summary=E('summary','Selection and keyboard shortcuts');help.append(summary,hints);quick.append(help);}
 $('paste-status').after($('message'));
 const source=document.querySelector('.panel-status');source.append($('pause'));
 const brand=document.querySelector('.app-header');
 function disclosure(host,title,open=false,className=''){
  const box=E('details'),summary=E('summary',title);box.className=className;box.open=open;
  const children=[...host.childNodes];box.append(summary,...children);host.append(box);return box;
 }
 for(const host of [...shell.children]){
  if(host.tagName!=='SECTION'||host===workspace||host.classList.contains('current'))continue;
  const heading=host.querySelector(':scope > h2');
  const title=host===source?'Source & capture settings':heading?.textContent||host.getAttribute('aria-label')||'Settings';
  if(heading)heading.remove();disclosure(host,title,false,'settings-disclosure');
 }
 const readingPanel=workspace.querySelector('section.current');
 const heading=readingPanel.querySelector(':scope > h2');const title=heading.textContent;heading.remove();disclosure(readingPanel,title,true,'reading-disclosure');
 dictionary.querySelector('.dict-toolbar strong')?.remove();
 disclosure(dictionary,'Your dictionaries',true,'dictionary-disclosure');dictionary.hidden=false;
 if(!$('dict-tabs').children.length)$('dict-entries').textContent='Select a word, or paste a search above.';
 for(const id of ['latestenglish','latestchinese']){
  const text=$(id),heading=text.previousElementSibling;
  if(heading?.tagName==='H2'){const group=E('details'),summary=E('summary',heading.textContent);group.className='translation-disclosure';group.open=true;heading.before(group);group.append(summary,text);heading.remove();}
 }
 const chatToggle=[...readingPanel.querySelectorAll('label')].find(label=>label.textContent.includes('Temporary Chat'));
 if(chatToggle){const options=E('details'),summary=E('summary','Chat options');options.append(summary,chatToggle);currentSend.after(options);}
 const about=E('details');about.className='panel';about.append(E('summary','About Japanese Reader'),brand);shell.append(about);
 shell.prepend(workspace);
})();

// Keep the two content borders aligned as controls and dictionary tabs wrap.
// Offsets are removed from measurements so resizing never accumulates spacing.
(() => {
 const workspace=$('reader-workspace'),reading=$('latest'),frame=$('dict-frame');
 const dictionary=$('dictionary-panel');
 const desktop=matchMedia('(min-width:1100px)');
 let readingOffset=0,dictionaryOffset=0,pending=false;
 function align(){
  pending=false;
  let nextReading=0,nextDictionary=0;
  const readingOpen=workspace.querySelector('.reading-disclosure').open;
  const companionSpace=document.getElementById('reader-companion-art')?340:0;
  if(desktop.matches&&readingOpen)nextReading=companionSpace;
  if(desktop.matches&&!dictionary.hidden&&readingOpen&&dictionary.querySelector('.dictionary-disclosure').open){
   const readingTop=reading.getBoundingClientRect().top-readingOffset;
   const dictionaryTop=frame.getBoundingClientRect().top-dictionaryOffset;
   nextReading=Math.max(companionSpace,dictionaryTop-readingTop);
   nextDictionary=Math.max(0,readingTop+nextReading-dictionaryTop);
  }
  if(Math.abs(nextReading-readingOffset)>.5||Math.abs(nextDictionary-dictionaryOffset)>.5){
   readingOffset=nextReading;dictionaryOffset=nextDictionary;
   workspace.style.setProperty('--reading-top-offset',readingOffset+'px');
   workspace.style.setProperty('--dictionary-top-offset',dictionaryOffset+'px');
   workspace.dispatchEvent(new Event('reader-layout-aligned'));
  }
 }
 function schedule(){if(!pending){pending=true;requestAnimationFrame(align);}}
 const resize=new ResizeObserver(schedule);
 resize.observe(workspace);
 for(const element of workspace.querySelectorAll('.reading-disclosure > *, .dictionary-disclosure > *, #dict-entries'))resize.observe(element);
 new MutationObserver(schedule).observe(workspace,{subtree:true,childList:true,characterData:true,attributes:true,attributeFilter:['open','hidden','class']});
 window.addEventListener('resize',schedule);
 desktop.addEventListener('change',()=>{
  readingOffset=dictionaryOffset=0;
  workspace.style.removeProperty('--reading-top-offset');
  workspace.style.removeProperty('--dictionary-top-offset');
  schedule();
 });
 document.fonts.ready.then(schedule);
 schedule();
})();

// Decorative companions occupy only the existing desktop alignment gap.
(() => {
 const data=document.getElementById('reader-companion-art');
 if(!data)return;
 const assets=JSON.parse(data.textContent),workspace=$('reader-workspace');
 const reading=$('latest'),host=reading.closest('.reading-disclosure');
 const key='reader-companions-v1',reduce=matchMedia('(prefers-reduced-motion: reduce)');
 let saved={};try{saved=JSON.parse(localStorage.getItem(key)||'{}')||{};}catch{}
 const prefs={hidden:!!saved.hidden,paused:typeof saved.paused==='boolean'?saved.paused:reduce.matches,
  size:Math.min(140,Math.max(60,Number(saved.size)||100)),selected:Array.isArray(saved.selected)?saved.selected:assets.map(a=>a.id),positions:saved.positions||{}};
 function save(){try{localStorage.setItem(key,JSON.stringify(prefs));}catch{}}
 const stage=E('section');stage.id='reader-companions';stage.setAttribute('aria-label','Character companions');stage.hidden=true;
 const controls=E('div');controls.className='companion-controls';
 const title=E('span','Reading companions');title.className='companion-title';
 const pause=E('button'),hide=E('button'),choose=E('button','Artwork credits'),reset=E('button','Reset positions');
 for(const b of [pause,hide,choose,reset])b.type='button';
 const size=E('input');size.type='range';size.min=60;size.max=140;size.value=prefs.size;size.setAttribute('aria-label','Character size');
 const options=E('div');options.className='companion-options';options.id='companion-options';options.hidden=true;
 choose.setAttribute('aria-controls',options.id);choose.setAttribute('aria-expanded','false');
 const cast=E('div');cast.className='companion-cast';
 const hint=E('span','Drag to arrange · arrow keys to move');hint.className='companion-hint';
 controls.append(title,pause,hide,choose,size,reset);stage.append(controls,options,cast,hint);reading.before(stage);
 const choices=E('div');choices.className='companion-choices';choices.setAttribute('role','group');choices.setAttribute('aria-label','Show or hide individual characters');
 choices.append(E('span','Show:'));controls.append(choices);
 const people=[];
 for(const [i,a] of assets.entries()){
  const label=E('label'),check=E('input');check.type='checkbox';check.checked=prefs.selected.includes(a.id);
  label.append(check,document.createTextNode(a.name));choices.append(label);
  check.onchange=()=>{prefs.selected=assets.filter(item=>item.id===a.id?check.checked:prefs.selected.includes(item.id)).map(item=>item.id);prefs.positions={};if(check.checked)prefs.hidden=false;save();layout();};
  const person=E('button');person.type='button';person.className='companion-person';person.dataset.character=a.id;
  person.setAttribute('aria-label',a.name+' — drag or use arrow keys to move');person.title=a.name;
  const art=E('span');art.className='companion-art';art.style.animationDelay=(-i*1.3)+'s';
  art.style.animationDuration=(5.2+i*.45)+'s';
  // SVG viewBox clips the source page's transparent margins without modifying artwork.
  const ns='http://www.w3.org/2000/svg',svg=document.createElementNS(ns,'svg');
  svg.setAttribute('viewBox',a.box.join(' '));svg.setAttribute('aria-hidden','true');
  const img=document.createElementNS(ns,'image');img.setAttribute('href',a.image);img.setAttribute('width',a.width);img.setAttribute('height',a.height);
  if(a.clip){const defs=document.createElementNS(ns,'defs'),clip=document.createElementNS(ns,'clipPath'),poly=document.createElementNS(ns,'polygon');clip.id='companion-clip-'+a.id;poly.setAttribute('points',a.clip);clip.append(poly);defs.append(clip);svg.append(defs);img.setAttribute('clip-path','url(#'+clip.id+')');}
  svg.append(img);art.append(svg);const caption=E('span',a.name);caption.className='companion-caption';person.append(art,caption);cast.append(person);
  const state={a,person,art,index:i};people.push(state);
  let drag=null;
  person.onpointerdown=e=>{
   if(e.button!==0)return;
   person.focus({preventScroll:true});person.setPointerCapture(e.pointerId);
   drag={x:e.clientX,y:e.clientY,left:person.offsetLeft,top:person.offsetTop};person.dataset.dragging='true';
  };
  function move(left,top){
   const mx=Math.max(0,cast.clientWidth-person.offsetWidth),my=Math.max(0,cast.clientHeight-person.offsetHeight);
   left=Math.max(0,Math.min(mx,left));top=Math.max(0,Math.min(my,top));
   person.style.left=left+'px';person.style.top=top+'px';prefs.positions[a.id]={x:mx?left/mx:0,y:my?top/my:0};
  }
  person.onpointermove=e=>{if(drag)move(drag.left+e.clientX-drag.x,drag.top+e.clientY-drag.y);};
  function finish(){if(!drag)return;drag=null;delete person.dataset.dragging;save();}
  person.onpointerup=finish;person.onpointercancel=finish;person.onlostpointercapture=finish;
  person.onkeydown=e=>{
   if(!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(e.key))return;
   e.preventDefault();const step=e.shiftKey?20:5;
   move(person.offsetLeft+(e.key==='ArrowLeft'?-step:e.key==='ArrowRight'?step:0),person.offsetTop+(e.key==='ArrowUp'?-step:e.key==='ArrowDown'?step:0));save();
  };
 }
 const credits=E('p');credits.className='companion-credits';credits.append(document.createTextNode('Artwork: '));
 for(const [text,url] of [['STEINS;GATE ELITE','https://steinsgate.jp/elite/'],['Cosmic Princess Kaguya!','https://www.cho-kaguyahime.com/']]){const a=E('a',text);a.href=url;a.target='_blank';a.rel='noopener noreferrer';credits.append(a,document.createTextNode(' · '));}
 credits.append(document.createTextNode('Portraits with gentle motion.'));options.append(credits);
 pause.onclick=()=>{prefs.paused=!prefs.paused;save();layout();};
 hide.onclick=()=>{prefs.hidden=!prefs.hidden;save();layout();};
 choose.onclick=()=>{options.hidden=!options.hidden;choose.setAttribute('aria-expanded',String(!options.hidden));layout();};
 reset.onclick=()=>{prefs.positions={};save();layout();};size.oninput=()=>{prefs.size=Number(size.value);save();layout();};
 function layout(){
  const offset=parseFloat(workspace.style.getPropertyValue('--reading-top-offset'))||0;
  const desktop=matchMedia('(min-width:1100px)').matches;
  stage.hidden=!host.open;
  if(stage.hidden)return;
  stage.style.top=desktop?(reading.getBoundingClientRect().top-host.getBoundingClientRect().top-offset+6)+'px':'auto';
  stage.style.height=(desktop?Math.max(328,offset-12):340)+'px';
  stage.dataset.paused=String(prefs.paused);pause.textContent=prefs.paused?'Resume':'Pause';pause.setAttribute('aria-pressed',String(prefs.paused));
  hide.textContent=prefs.hidden?'Show characters':'Hide';hide.setAttribute('aria-pressed',String(prefs.hidden));
  cast.hidden=hint.hidden=prefs.hidden;
  const top=controls.offsetHeight+(options.hidden?0:options.offsetHeight)+12;
  cast.style.top=top+'px';
  const chosen=people.filter(p=>prefs.selected.includes(p.a.id));
  // Equal-width slots keep character centres evenly spaced despite differing
  // artwork widths. A shared height also keeps their feet on one baseline.
  const slotWidth=cast.clientWidth/Math.max(1,chosen.length);
  const widest=Math.max(1e-3,...chosen.map(p=>p.a.box[2]/p.a.box[3]));
  const height=Math.max(0,Math.min(420*prefs.size/100,cast.clientHeight-30,slotWidth*.94/widest,slotWidth*.94/widest*prefs.size/100));
  for(const p of people){
   p.person.hidden=!chosen.includes(p);if(p.person.hidden)continue;
   const ratio=p.a.box[2]/p.a.box[3];
   const width=height*ratio,fullHeight=height+22;
   p.person.style.width=width+'px';p.person.style.height=fullHeight+'px';p.art.style.height=height+'px';
   const mx=Math.max(0,cast.clientWidth-width),my=Math.max(0,cast.clientHeight-fullHeight);
   const pos=prefs.positions[p.a.id];
   const x=pos&&Number.isFinite(pos.x)?Math.max(0,Math.min(1,pos.x))*mx:(chosen.indexOf(p)+.5)*slotWidth-width/2;
   const y=pos&&Number.isFinite(pos.y)?Math.max(0,Math.min(1,pos.y))*my:my;
   p.person.style.left=Math.max(0,Math.min(mx,x))+'px';p.person.style.top=y+'px';
  }
 }
 let pending=false;function schedule(){if(!pending){pending=true;requestAnimationFrame(()=>{pending=false;layout();});}}
 workspace.addEventListener('reader-layout-aligned',schedule);
 const observer=new ResizeObserver(schedule);observer.observe(host);observer.observe(controls);observer.observe(options);
 host.addEventListener('toggle',schedule);window.addEventListener('resize',schedule);
 document.addEventListener('visibilitychange',()=>{stage.dataset.sleeping=String(document.hidden);});
 schedule();
})();
