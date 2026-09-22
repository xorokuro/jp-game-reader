(() => {
  const input=document.getElementById('lookup-word');
  const button=document.getElementById('lookup-local');
  const status=document.getElementById('lookup-state');
  const selectionHint=document.createElement('p');selectionHint.className='muted';
  selectionHint.textContent='Auto lookup: select up to 10 characters. Longer text or sentences stay selected for copying. Right-drag to highlight without searching, or hold Shift while selecting.';
  status.after(selectionHint);
  input.addEventListener('click',()=>input.select());
  input.addEventListener('focus',()=>input.select());
  const pasteWord=document.createElement('button');pasteWord.type='button';pasteWord.id='lookup-paste';pasteWord.textContent='Paste and search';
  pasteWord.setAttribute('aria-label','Paste clipboard text and search my dictionaries');input.after(pasteWord);
  pasteWord.onclick=async()=>{
    try{
      const text=await navigator.clipboard.readText();
      if(!text.trim()){status.textContent='Clipboard has no text.';return;}
      input.value=text.trim();input.focus({preventScroll:true});input.select();
      searchDictionaries();
    }catch{
      input.focus({preventScroll:true});input.select();status.textContent='Clipboard access unavailable. Press Ctrl+V to paste, then Enter to search.';
    }
  };
  const onlineButton=document.getElementById('lookup-online');
  const onlineSetting=document.createElement('label');
  const onlineToggle=document.createElement('input');onlineToggle.type='checkbox';
  try{onlineToggle.checked=localStorage.getItem('fortune-show-online-lookup')==='true';}catch{}
  onlineButton.hidden=!onlineToggle.checked;
  onlineToggle.onchange=()=>{onlineButton.hidden=!onlineToggle.checked;try{localStorage.setItem('fortune-show-online-lookup',String(onlineToggle.checked));}catch{}};
  onlineSetting.append(onlineToggle,document.createTextNode(' Show “Look up online” (Jisho)'));
  document.getElementById('theme-settings').append(onlineSetting);
  const panel=document.createElement('div');panel.id='dictionary-panel';panel.hidden=false;
  panel.innerHTML='<div class="dict-toolbar"><strong>Your dictionaries</strong><button type="button" id="dict-read">Read word aloud (synthetic voice)</button><button type="button" id="dict-close">Close dictionary</button></div><p class="muted">Recorded dictionary pronunciations appear as audio players inside entries. Synthetic read-aloud uses an available browser voice.</p><div id="dict-tabs" role="group" aria-label="Installed dictionaries"></div><div class="dict-layout"><div id="dict-entries" aria-label="Matching entries"></div><iframe id="dict-frame" title="Purchased dictionary definition" sandbox="allow-same-origin"></iframe></div>';
  const workspace=document.createElement('div');workspace.id='reader-workspace';
  const current=document.querySelector('section.current');
  current.before(workspace);workspace.append(current,panel);
  const preferences=document.createElement('details');preferences.id='dict-preferences';
  preferences.innerHTML='<summary>Choose dictionaries</summary><p class="muted">Checked dictionaries appear in the results. Drag the ⠿ handle to reorder dictionaries. Choices and order are saved automatically.</p><div id="dict-choices"></div>';
  panel.querySelector('.dict-toolbar').after(preferences);preferences.open=true;
  const preferenceKey='fortune-weave-visible-dictionaries-v1';
  let selectedCodes=null;
  try{const saved=JSON.parse(localStorage.getItem(preferenceKey));if(Array.isArray(saved))selectedCodes=new Set(saved);}catch{}
  if(selectedCodes===null)selectedCodes=new Set(['MDX_ALL','MDX_SHO','MDX_MEI']);
  let dictionaries=[],catalog=[],currentCode='',dictionaryOrder=[];
  try{dictionaryOrder=JSON.parse(localStorage.getItem('fortune-dictionary-order')||'[]');if(!Array.isArray(dictionaryOrder))dictionaryOrder=[];}catch{}
  function ordered(items){return [...items].sort((a,b)=>{const ai=dictionaryOrder.indexOf(a.code),bi=dictionaryOrder.indexOf(b.code);return (ai<0?999:ai)-(bi<0?999:bi);});}
  function saveChoices(){
    try{localStorage.setItem(preferenceKey,JSON.stringify([...selectedCodes]));localStorage.setItem('fortune-dictionary-order',JSON.stringify(dictionaryOrder));}catch{status.textContent='Changes apply now, but could not be saved.';}
  }
  function renderChoices(){
    const all=catalog.length?catalog:dictionaries;
    const enabled=ordered(all.filter(d=>selectedCodes.has(d.code)));
    dictionaryOrder=enabled.map(d=>d.code);
    preferences.querySelector('summary').textContent='Choose dictionaries · '+enabled.length+' selected';
    const choices=document.getElementById('dict-choices');choices.replaceChildren();
    function move(code,number){
      if(!Number.isInteger(number)||number<1||number>enabled.length){status.textContent='Enter a whole number from 1 to '+enabled.length+'.';renderChoices();return;}
      dictionaryOrder=dictionaryOrder.filter(c=>c!==code);dictionaryOrder.splice(number-1,0,code);saveChoices();renderChoices();renderTabs();
    }
    for(const d of [...enabled,...all.filter(d=>!selectedCodes.has(d.code))]){
      const row=document.createElement('div');row.className='dict-choice-row';row.dataset.code=d.code;
      const checked=selectedCodes.has(d.code);
      if(checked){
        const handle=document.createElement('button');handle.type='button';handle.className='dict-drag-handle';handle.textContent='⠿';handle.draggable=true;handle.setAttribute('aria-label','Drag to reorder '+d.name);
        handle.ondragstart=e=>{e.dataTransfer.setData('text/plain',d.code);e.dataTransfer.effectAllowed='move';};
        row.ondragover=e=>{e.preventDefault();e.dataTransfer.dropEffect='move';};
        row.ondrop=e=>{e.preventDefault();const code=e.dataTransfer.getData('text/plain');if(selectedCodes.has(code))move(code,dictionaryOrder.indexOf(d.code)+1);};
        handle.onkeydown=e=>{if(e.altKey&&['ArrowUp','ArrowDown'].includes(e.key)){e.preventDefault();const n=dictionaryOrder.indexOf(d.code)+1+(e.key==='ArrowUp'?-1:1);if(n>=1&&n<=enabled.length)move(d.code,n);}};
        const position=document.createElement('input');position.type='number';position.className='dict-order-number';position.min='1';position.max=String(enabled.length);position.value=dictionaryOrder.indexOf(d.code)+1;position.step='1';position.setAttribute('aria-label','Order for '+d.name);
        position.onchange=()=>move(d.code,Number(position.value));position.onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();position.blur();}else if(e.key==='Escape'){position.value=dictionaryOrder.indexOf(d.code)+1;position.blur();}};
        row.append(handle,position);
      }
      const label=document.createElement('label'),check=document.createElement('input');check.type='checkbox';check.checked=checked;
      check.onchange=()=>{
        dictionaryOrder=dictionaryOrder.filter(c=>c!==d.code);
        if(check.checked){selectedCodes.add(d.code);dictionaryOrder.push(d.code);}else selectedCodes.delete(d.code);
        saveChoices();renderChoices();renderTabs();if(input.value.trim())searchDictionaries(true);
      };
      label.append(check,document.createTextNode(d.name));row.append(label);choices.append(row);
    }
  }
  function renderTabs(){
    previewObserver.disconnect();tabs.replaceChildren();const visible=ordered(dictionaries.filter(d=>selectedCodes.has(d.code)));
    const wordHeading=document.createElement('div');wordHeading.className='dict-preview-heading';
    const title=document.createElement('strong');title.textContent=spokenWord?'Dictionary: '+spokenWord:'Highlight a word to preview your dictionaries';wordHeading.append(title);
    for(const kanji of [...new Set((spokenWord||'').match(/[\u3400-\u9fff]/gu)||[])]){
      const k=document.createElement('button');k.type='button';k.textContent=kanji;k.title='Look up this kanji in your selected dictionaries';k.onclick=()=>{input.value=kanji;searchDictionaries();};wordHeading.append(k);
    }
    tabs.append(wordHeading);
    visible.forEach(d=>{
      const group=document.createElement('section');group.className='dict-result-group';
      const heading=document.createElement('h3');heading.textContent=d.name+' · '+(d.error?'error':d.count);group.append(heading);
      for(const row of d.entries||[]){
        const result=document.createElement('button');result.type='button';result.className='dict-result-row';result.dataset.code=d.code;result.dataset.entry=String(row.id);result.textContent=row.previewLabel||row.title;
        result.onclick=()=>{currentCode=d.code;openEntry(d,row);};group.append(result);
        result._preview={dictionary:d,row};previewObserver.observe(result);
      }
      if(!d.entries?.length){const empty=document.createElement('p');empty.textContent=d.error||'No matches';group.append(empty);}
      tabs.append(group);
    });
    if(!visible.length){const empty=document.createElement('p');empty.textContent='Choose a dictionary above, then highlight a word.';tabs.append(empty);}
    tabs.hidden=false;entries.hidden=true;frame.hidden=true;frame.removeAttribute('src');
  }
  const previewQueue=[];let previewJobs=0;
  const previewObserver=new IntersectionObserver(items=>{for(const item of items){if(item.isIntersecting){previewObserver.unobserve(item.target);previewQueue.push(item.target);}}fillReadings();});
  async function fillReadings(){
    while(previewJobs<4&&previewQueue.length){
      const target=previewQueue.shift();if(!target.isConnected)continue;
      const {dictionary,row}=target._preview;if(row.previewLabel){target.textContent=row.previewLabel;continue;}
      previewJobs++;
      (async()=>{try{
        const response=await fetch('/api/dictionary/entry?'+new URLSearchParams({code:dictionary.code,id:row.id}));if(!response.ok)return;
        const doc=new DOMParser().parseFromString(await response.text(),'text/html');
        const reading=doc.querySelector('h3 .pinyin_h');
        const head=doc.querySelector('.HeadG,.head .word,.headword,.entry-headword,h3,h1');
        let label=reading?reading.textContent.trim()+'【'+row.title+'】':head?.textContent.trim().replace(/\s+/g,' ');
        if(label&&label.length<=140){row.previewLabel=label;if(target.isConnected)target.textContent=label;}
      }catch{}finally{previewJobs--;fillReadings();}})();
    }
  }
  const tabs=document.getElementById('dict-tabs'),entries=document.getElementById('dict-entries'),frame=document.getElementById('dict-frame');
  let dictionaryZoom=100;
  try{const saved=Number(localStorage.getItem('fortune-dictionary-zoom'));if(saved>=70&&saved<=200)dictionaryZoom=saved;}catch{}
  const zoomControls=document.createElement('span');zoomControls.className='dict-zoom-controls';
  const zoomOut=document.createElement('button'),zoomReset=document.createElement('button'),zoomIn=document.createElement('button');
  for(const control of [zoomOut,zoomReset,zoomIn])control.type='button';
  zoomOut.textContent='A−';zoomOut.setAttribute('aria-label','Shrink dictionary text');
  zoomIn.textContent='A+';zoomIn.setAttribute('aria-label','Enlarge dictionary text');
  zoomReset.title='Reset dictionary zoom to 100%';
  function applyDictionaryZoom(){
    zoomReset.textContent=dictionaryZoom+'%';zoomOut.disabled=dictionaryZoom<=70;zoomIn.disabled=dictionaryZoom>=200;
    try{if(frame.contentDocument?.body)frame.contentDocument.body.style.setProperty('zoom',dictionaryZoom/100,'important');}catch{}
  }
  function changeDictionaryZoom(value){dictionaryZoom=Math.max(70,Math.min(200,value));try{localStorage.setItem('fortune-dictionary-zoom',String(dictionaryZoom));}catch{}applyDictionaryZoom();}
  zoomOut.onclick=()=>changeDictionaryZoom(dictionaryZoom-10);zoomIn.onclick=()=>changeDictionaryZoom(dictionaryZoom+10);zoomReset.onclick=()=>changeDictionaryZoom(100);
  zoomControls.append(zoomOut,zoomReset,zoomIn);panel.querySelector('.dict-toolbar strong').after(zoomControls);applyDictionaryZoom();
  function navigateDictionaryWithUndo(event){
    if(event.defaultPrevented||event.isComposing||event.altKey||!event.ctrlKey||event.metaKey||event.key.toLowerCase()!=='z')return;
    const target=event.target;
    if(target?.isContentEditable||target?.closest?.('input,textarea,select,[contenteditable],[role="textbox"],[role="combobox"]'))return;
    event.preventDefault();
    const control=event.shiftKey?next:back;
    if(!event.repeat&&!control.disabled)control.click();
  }
  function navigateDictionaryWithArrows(event){
    if(event.defaultPrevented||event.isComposing||event.altKey||event.ctrlKey||event.metaKey||event.shiftKey)return;
    if(event.key!=='ArrowLeft'&&event.key!=='ArrowRight')return;
    const target=event.target;
    if(target?.isContentEditable||target?.closest?.('input,textarea,select,audio,video,[contenteditable],[role="textbox"],[role="slider"],[role="combobox"],[role="listbox"],[role="tablist"]'))return;
    const control=event.key==='ArrowLeft'?back:next;
    if(control.disabled)return;
    event.preventDefault();
    if(!event.repeat)control.click();
  }
  function pasteAndSearch(event){
    if(event.defaultPrevented)return;
    const target=event.target;
    if(target?.isContentEditable||target?.closest?.('input,textarea,select,[contenteditable],[role="textbox"],[role="combobox"]'))return;
    const text=event.clipboardData?.getData('text/plain')?.trim();
    if(!text)return;
    event.preventDefault();
    input.value=text;
    searchDictionaries();
  }
  function enableSelectionSearch(doc,insideEntry=false){
    let selecting=false,skipLookup=false,pendingLookup;
    const cancelLookup=()=>{clearTimeout(pendingLookup);};
    // Right-drag selects text without scheduling dictionary lookup.
    let rightDrag=null,suppressMenu=false;
    function caretAt(x,y){
      if(doc.caretPositionFromPoint){const p=doc.caretPositionFromPoint(x,y);return p&&{node:p.offsetNode,offset:p.offset};}
      const r=doc.caretRangeFromPoint?.(x,y);return r&&{node:r.startContainer,offset:r.startOffset};
    }
    doc.addEventListener('pointerdown',event=>{
      suppressMenu=false;
      if(event.button!==2)return;
      cancelLookup();selecting=false;skipLookup=true;
      const target=event.target;
      if(target.closest('button,input,textarea,select,audio,video,summary,[contenteditable]'))return;
      const host=insideEntry?doc.body:target.closest('#latest,#latestenglish,#latestchinese');
      if(!host)return;
      const anchor=caretAt(event.clientX,event.clientY);
      if(!anchor||!host.contains(anchor.node))return;
      rightDrag={anchor,host,x:event.clientX,y:event.clientY,moved:false};
      event.preventDefault();
    });
    doc.addEventListener('pointermove',event=>{
      if(!rightDrag)return;
      if(!(event.buttons&2)){rightDrag=null;return;}
      if(Math.hypot(event.clientX-rightDrag.x,event.clientY-rightDrag.y)<4&&!rightDrag.moved)return;
      const end=caretAt(event.clientX,event.clientY);
      if(!end||!rightDrag.host.contains(end.node))return;
      rightDrag.moved=true;suppressMenu=true;cancelLookup();
      doc.getSelection()?.setBaseAndExtent(rightDrag.anchor.node,rightDrag.anchor.offset,end.node,end.offset);
      event.preventDefault();
    });
    doc.addEventListener('pointerup',event=>{
      if(event.button!==2)return;
      if(rightDrag?.moved){event.preventDefault();suppressMenu=true;}
      rightDrag=null;selecting=false;cancelLookup();
    });
    doc.addEventListener('pointercancel',()=>{rightDrag=null;});
    doc.addEventListener('contextmenu',event=>{
      if(suppressMenu||rightDrag?.moved){event.preventDefault();suppressMenu=false;}
    });
    doc.addEventListener('copy',cancelLookup);
    doc.addEventListener('paste',event=>{cancelLookup();pasteAndSearch(event);});
    doc.addEventListener('keydown',navigateDictionaryWithArrows);
    doc.addEventListener('keydown',navigateDictionaryWithUndo);
    doc.addEventListener('keydown',event=>{
      if(event.key==='Shift'){skipLookup=true;cancelLookup();}
      if((event.ctrlKey||event.metaKey)&&event.key.toLowerCase()==='c')cancelLookup();
    });
    doc.addEventListener('pointerdown',event=>{
      cancelLookup();skipLookup=event.shiftKey;
      const target=event.target;
      selecting=event.button===0&&(!target.closest('button,input,textarea,select,a,audio,summary,[contenteditable]')||!!target.closest('#latest'))&&
        (insideEntry||!!target.closest('#latest,#latestenglish,#latestchinese'));
    });
    doc.addEventListener('pointercancel',()=>{selecting=false;cancelLookup();});
    doc.addEventListener('pointerup',event=>{
      if(!selecting)return;selecting=false;
      if(skipLookup||event.shiftKey)return;
      const selectedText=doc.getSelection()?.toString().trim();
      pendingLookup=setTimeout(()=>{
        const selection=doc.getSelection();
        if(!selection||selection.isCollapsed)return;
        const word=selection.toString().trim();
        // Leave sentence selections intact so copying never replaces the entry.
        if(!word||word!==selectedText||Array.from(word).length>10||/[\r\n。！？.!?]/u.test(word))return;
        input.value=word;searchDictionaries(true);
      },300);
    });
  }
  enableSelectionSearch(document);
  // Entries are a separate document, so the reader's light/dark choice is copied in.
  function matchEntryTheme(){
    try{
      const entryDocument=frame.contentDocument;
      if(entryDocument?.documentElement)entryDocument.documentElement.dataset.mode=document.documentElement.dataset.mode||'dark';
    }catch{}
  }
  document.addEventListener('readerthemechange',matchEntryTheme);
  frame.addEventListener('load',()=>{
    // Entries stay sandboxed; the parent can read selections in local documents.
    let entryDocument;try{entryDocument=frame.contentDocument;}catch{return;}
    if(!entryDocument)return;
    matchEntryTheme();
    applyDictionaryZoom();
    // Scroll only the embedded document. URL fragments can also scroll its
    // containing page when the browser brings the target into view.
    const anchor=new URL(frame.src,location.href).searchParams.get('anchor');
    const target=anchor&&(entryDocument.getElementById(anchor)||entryDocument.getElementsByName(anchor)[0]);
    const innerWindow=frame.contentWindow;
    if(innerWindow)innerWindow.scrollTo({top:target?target.getBoundingClientRect().top+innerWindow.scrollY:0,left:0,behavior:'instant'});
    enableSelectionSearch(entryDocument,true);
    const useSelection=()=>{
      if(document.activeElement===input)return;
      const active=entryDocument.activeElement;
      if(active&&(active.matches('input,textarea')||active.isContentEditable))return;
      const selection=entryDocument.getSelection();
      if(!selection||selection.isCollapsed)return;
      const word=selection.toString().trim();
      if(word&&word.length<120)input.value=word;
    };
    entryDocument.addEventListener('selectionchange',useSelection);
    entryDocument.addEventListener('pointerup',useSelection);
    entryDocument.addEventListener('keyup',useSelection);
  });
  let requestVersion=0,spokenWord='';
  const searchHistory=[],forwardHistory=[];
  let searchPending=false,currentEntry=null;
  const back=document.createElement('button');back.type='button';back.id='dict-back';back.textContent='← Previous search';back.title='Previous search (Ctrl+Z)';back.disabled=true;
  panel.querySelector('.dict-toolbar strong').after(back);
  const next=document.createElement('button');next.type='button';next.id='dict-next';next.textContent='Next search →';next.title='Next search (Ctrl+Shift+Z)';back.after(next);
  const leftBack=back.cloneNode(true),leftNext=next.cloneNode(true);leftBack.id='lookup-back';leftNext.id='lookup-next';button.after(leftBack,leftNext);
  function updateBack(){
    for(const control of [back,leftBack]){control.disabled=!searchHistory.length&&!(searchPending&&spokenWord);control.title=searchHistory.length?'Previous: '+searchHistory.at(-1).word:'No earlier search';}
    for(const control of [next,leftNext]){control.disabled=!forwardHistory.length;control.title=forwardHistory.length?'Next: '+forwardHistory.at(-1).word:'No later search';}
  }
  function rememberSearch(stack,saved){if(saved){stack.push(saved);if(stack.length>100)stack.shift();}}
  function snapshotSearch(){
    if(!spokenWord)return null;
    return {word:spokenWord,dictionaries,code:currentCode,entry:currentEntry,codes:[...selectedCodes].sort().join('|')};
  }
  function restoreSearch(saved){
    spokenWord=saved.word;input.value=saved.word;dictionaries=saved.dictionaries;currentCode=saved.code;panel.hidden=false;
    if(saved.codes!==[...selectedCodes].sort().join('|')){searchDictionaries(true);return;}
    renderChoices();renderTabs();
    const dictionary=dictionaries.find(d=>d.code===saved.code&&selectedCodes.has(d.code));
    if(dictionary&&saved.entry)openEntry(dictionary,saved.entry);
    status.textContent='“'+saved.word+'” · Search restored.';
  }
  back.onclick=()=>{
    const current=snapshotSearch();
    const saved=searchPending?snapshotSearch():searchHistory.pop();
    if(!saved)return;
    if(!searchPending)rememberSearch(forwardHistory,current);
    ++requestVersion;searchPending=false;button.disabled=false;
    restoreSearch(saved);updateBack();
  };
  next.onclick=()=>{
    const saved=forwardHistory.pop();if(!saved)return;
    rememberSearch(searchHistory,snapshotSearch());
    ++requestVersion;searchPending=false;button.disabled=false;
    restoreSearch(saved);updateBack();
  };
  leftBack.onclick=back.onclick;leftNext.onclick=next.onclick;updateBack();
  for(const control of [back,leftBack])control.setAttribute('aria-keyshortcuts','Control+z ArrowLeft');
  for(const control of [next,leftNext])control.setAttribute('aria-keyshortcuts','Control+Shift+z ArrowRight');
  selectionHint.textContent+=' Use Ctrl+Z / Ctrl+Shift+Z (or ← / →) for previous / next search outside text fields.';
  function openEntry(dictionary,row){
    currentEntry=row;currentCode=dictionary.code;tabs.hidden=true;entries.hidden=false;entries.replaceChildren();frame.hidden=false;
    const backToResults=document.createElement('button');backToResults.type='button';backToResults.textContent='← All dictionary results';backToResults.onclick=()=>{tabs.hidden=false;entries.hidden=true;frame.hidden=true;};entries.append(backToResults);
    const entryTitle=document.createElement('strong');entryTitle.textContent=dictionary.name+' · '+(row.previewLabel||row.title);entries.append(entryTitle);
    const params=new URLSearchParams({code:dictionary.code,id:row.id,anchor:row.anchor||''});
    frame.src='/api/dictionary/entry?'+params;
    [...entries.children].forEach(b=>b.classList.toggle('active',b.dataset.entry===String(row.id)+'#'+row.anchor));
  }
  function choose(dictionary){
    currentEntry=null;
    currentCode=dictionary.code;
    tabs.querySelectorAll('button[data-code]').forEach(b=>{const selected=b.dataset.code===dictionary.code;b.classList.toggle('active',selected);b.setAttribute('aria-pressed',String(selected));});
    entries.replaceChildren();frame.removeAttribute('src');
    if(dictionary.error){entries.textContent='Dictionary error: '+dictionary.error;return;}
    if(!dictionary.entries.length){entries.textContent='No matches in this dictionary.';return;}
    dictionary.entries.forEach(row=>{
      const b=document.createElement('button');b.type='button';b.textContent=row.title;b.dataset.entry=String(row.id)+'#'+row.anchor;
      b.onclick=()=>openEntry(dictionary,row);entries.append(b);
    });
    openEntry(dictionary,dictionary.entries[0]);
  }
  button.textContent='Look up in my dictionaries';
  const kenkyushaEntryKinds=new Map();
  async function mainKenkyushaFirst(results){
    const dictionary=results.find(d=>d.code==='MDX_KEN');
    if(!dictionary?.entries?.length)return;
    await Promise.all(dictionary.entries.map(async row=>{
      const key=String(row.id);
      if(!kenkyushaEntryKinds.has(key)){
        try{
          const response=await fetch('/api/dictionary/entry?'+new URLSearchParams({code:'MDX_KEN',id:row.id}));
          if(!response.ok)return;
          const doc=new DOMParser().parseFromString(await response.text(),'text/html');
          kenkyushaEntryKinds.set(key,doc.querySelector('.Header.Main')?'main':doc.querySelector('.Header.Sup')?'supplement':'other');
        }catch{return;}
      }
      row.kenkyushaKind=kenkyushaEntryKinds.get(key);
      if(row.kenkyushaKind==='main')row.title+=' · 本文';
      else if(row.kenkyushaKind==='supplement')row.title+=' · 追加語彙';
    }));
    const rank={main:0,other:1,supplement:2};
    dictionary.entries.sort((a,b)=>(rank[a.kenkyushaKind]??1)-(rank[b.kenkyushaKind]??1));
  }
  async function searchDictionaries(automatic=false){
    const word=input.value.trim();if(!word){status.textContent='Select or type a word first.';input.focus();return;}
    const previous=snapshotSearch();
    const version=++requestVersion;searchPending=true;updateBack();button.disabled=true;status.textContent='Searching your local dictionaries…';
    try{
      const response=await fetch('/api/dictionary/search',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({word,codes:[...selectedCodes]})});
      const result=await response.json();if(!response.ok)throw Error(result.error||'Dictionary search failed.');
      await mainKenkyushaFirst(result.dictionaries);
      if(version!==requestVersion)return;
      if(previous&&previous.word!==word){rememberSearch(searchHistory,previous);forwardHistory.length=0;}
      spokenWord=word;panel.hidden=false;dictionaries=result.dictionaries;currentCode='';renderChoices();renderTabs();
      status.textContent='“'+word+'” · Showing your chosen dictionaries. Change them under “Choose dictionaries”.';
    }catch(e){if(version===requestVersion)status.textContent=e.message;}finally{if(version===requestVersion){button.disabled=false;searchPending=false;updateBack();}}
  }
  button.onclick=()=>searchDictionaries();
  input.addEventListener('keydown',e=>{if(e.key==='Enter'){e.preventDefault();button.click();}});
  document.getElementById('dict-close').onclick=()=>{panel.hidden=true;frame.removeAttribute('src');if(window.speechSynthesis)speechSynthesis.cancel();};
  document.getElementById('dict-read').onclick=()=>{
    if(!window.speechSynthesis){status.textContent='Synthetic voice is unavailable in this browser. Use the recorded pronunciation players.';return;}
    const language=/[\u3040-\u30ff\u3400-\u9fff]/.test(spokenWord)?'ja':'en';
    const voices=speechSynthesis.getVoices();const voice=voices.find(v=>v.lang.toLowerCase().startsWith(language));
    if(!voice){status.textContent='No '+(language==='ja'?'Japanese':'English')+' browser voice is available. Recorded dictionary audio still works.';return;}
    speechSynthesis.cancel();const utterance=new SpeechSynthesisUtterance(spokenWord);utterance.lang=voice.lang;utterance.voice=voice;
    utterance.onerror=e=>{status.textContent='Synthetic speech could not play: '+e.error;};speechSynthesis.speak(utterance);
    status.textContent='Synthetic read-aloud: '+voice.name;
  };
  if(window.speechSynthesis)speechSynthesis.getVoices();
  preferences.querySelector('p').textContent='Only checked dictionaries are numbered. Newly checked dictionaries go last. Enter a number to reorder your selected dictionaries; choices and order are saved automatically.';
  const choiceActions=document.createElement('div');choiceActions.className='toolbar';
  for(const [title,codes] of [['Select all',null],['Clear selection',[]],['Use 3 main dictionaries',['MDX_ALL','MDX_SHO','MDX_MEI']]]){
    const action=document.createElement('button');action.type='button';action.textContent=title;
    action.onclick=()=>{const wanted=codes===null?[...dictionaryOrder,...catalog.map(d=>d.code)]:codes;selectedCodes=new Set(wanted);dictionaryOrder=[...selectedCodes];saveChoices();renderChoices();renderTabs();if(input.value.trim())searchDictionaries(true);};
    choiceActions.append(action);
  }
  preferences.querySelector('p').after(choiceActions);
  fetch('/api/dictionary/catalog').then(r=>{if(!r.ok)throw Error('catalog');return r.json();}).then(data=>{catalog=data.dictionaries;renderChoices();renderTabs();}).catch(()=>{preferences.querySelector('p').textContent='Could not load dictionary choices. Restart the reader and refresh.';});
})();
