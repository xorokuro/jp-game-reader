// Desktop input controls keep the reading block selectable for dictionary shortcuts.
(() => {
  const reading=$('latest'),status=$('paste-status');
  const bar=E('div');bar.className='toolbar reader-inputs';
  const paste=E('button','Paste text'),edit=E('button','Type / edit text'),save=E('button','Save this text');
  const editor=E('details'),summary=E('summary','Paste or edit a passage'),draft=E('textarea'),read=E('button','Read this text');
  editor.id='passage-editor';draft.id='passage-draft';draft.placeholder='Paste Japanese here…';draft.setAttribute('aria-label','Japanese passage');draft.maxLength=12000;
  editor.append(summary,draft,read);reading.before(bar,editor);bar.append(paste,edit,save);
  for(const control of [paste,edit,save,read])control.type='button';
  const saveLabel=E('label'),saveToggle=E('input');saveToggle.type='checkbox';saveToggle.disabled=true;
  saveLabel.append(saveToggle,document.createTextNode(' Automatically save new captured text'));bar.after(saveLabel);
  function openDraft(text){
    if(dirty())throw Error('Save your edited notes first.');
    if(!text.trim())throw Error('Paste Japanese text first.');
    if(text.length>12000)throw Error('Please keep each passage under 12,000 characters.');
    following=false;navSeq=null;
    showCurrent({id:-Date.now(),japanese:text,english:'',traditional_chinese:'',note:'',kind:'manual',temporary:true,localDraft:true});
    rememberPin();editor.open=false;draft.value=text;draft.dataset.changed='false';
    status.textContent='Temporary passage. Select words to look them up; Save this text keeps a copy in your library.';
    reading.focus({preventScroll:true});
  }
  draft.oninput=()=>draft.dataset.changed='true';
  edit.onclick=()=>{if(draft.dataset.changed!=='true')draft.value=currentRecord?.japanese||'';editor.open=true;draft.focus({preventScroll:true});};
  paste.onclick=()=>action(async()=>{
    try{openDraft(await navigator.clipboard.readText());}
    catch(error){editor.open=true;draft.focus({preventScroll:true});status.textContent=error.name==='NotAllowedError'?'Paste into the box, then choose Read this text.':error.message;}
  });
  reading.addEventListener('paste',event=>{event.preventDefault();event.stopPropagation();action(()=>openDraft(event.clipboardData?.getData('text/plain')||''));});
  read.onclick=()=>action(()=>openDraft(draft.value));
  save.onclick=()=>action(async()=>{
    if(!currentRecord?.japanese?.trim())throw Error('Open a passage first.');
    const original=currentRecord;save.disabled=true;
    try{
      const result=await api('add',{japanese:original.japanese,save:true,temporary_id:original.temporary&&!original.localDraft?original.id:undefined});
      if(currentRecord===original){following=false;navSeq=null;showCurrent(result.row);rememberPin();}
      await loadPage();status.textContent='Saved to your library.';
    }finally{save.disabled=false;}
  });
  $('add').onclick=()=>action(async()=>{openDraft($('manual').value);$('manual').value='';});
  saveToggle.onchange=()=>action(async()=>{
    const requested=saveToggle.checked;saveToggle.disabled=true;
    try{const result=await api('save-text',{enabled:requested});saveToggle.checked=result.enabled;}
    catch(error){saveToggle.checked=!requested;throw error;}
    finally{saveToggle.disabled=false;}
  });
  api('state').then(state=>{saveToggle.checked=state.save_text;saveToggle.disabled=false;}).catch(error=>status.textContent=error.message);
  addEventListener('beforeunload',event=>{
    if(draft.dataset.changed==='true'||currentRecord?.localDraft){event.preventDefault();event.returnValue='';}
  });
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
      paused=true;applyMode(result.settings.capture_mode);showSource();
      hint.textContent=activeMode==='paste'?'Ready for pasted text. Capture is paused.':'Source selected. Press Recognize when ready, or enable automatic recognition.';
    }finally{apply.disabled=false;}
  });
  api('state').then(async state=>{mode.value=state.settings.capture_mode||'paste';applyMode(mode.value);showSource();if(mode.value==='window')await listWindows(state.settings.window_handle);}).catch(error=>hint.textContent=error.message);
})();
