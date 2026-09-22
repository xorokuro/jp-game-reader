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
