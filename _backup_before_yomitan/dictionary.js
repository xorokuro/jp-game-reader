(() => {
  const input=document.getElementById('lookup-word');
  const button=document.getElementById('lookup-local');
  const status=document.getElementById('lookup-state');
  const selectionHint=document.createElement('p');selectionHint.className='muted';
  selectionHint.textContent='Auto lookup: select up to 10 characters. Longer text or sentences stay selected for copying. Right-drag to highlight without searching, or hold Shift while selecting.';
  input.addEventListener('click',()=>input.select());
  input.addEventListener('focus',()=>input.select());
  const pasteWord=document.createElement('button');pasteWord.type='button';pasteWord.id='lookup-paste';pasteWord.innerHTML=(window.readerIcon?readerIcon('paste'):'')+'<span>貼上查詢</span>';pasteWord.title='貼上剪貼簿文字並查詢 · Paste and search';
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
  onlineSetting.append(onlineToggle,document.createTextNode(' 顯示 Jisho 線上查詢按鈕 · Show “Look up online”'));
  document.getElementById('theme-settings').append(onlineSetting);
  const panel=document.createElement('div');panel.id='dictionary-panel';panel.hidden=true;
  panel.innerHTML='<div class="dict-head"><div class="dict-title"><span class="dict-seal" aria-hidden="true">辞</span><div><strong>辞書 · Dictionary</strong><span id="dict-word" class="dict-word" lang="ja"></span></div></div><div class="dict-toolbar"><button type="button" id="dict-read" class="icon-button" title="朗讀（合成語音）· Read aloud" aria-label="Read word aloud (synthetic voice)"></button><details class="dict-pop" id="dict-help"><summary class="icon-button" title="說明與快捷鍵 · Help" aria-label="Help and shortcuts"></summary><div class="dict-pop-body"><b>選取即查詢 · How lookup works</b></div></details><button type="button" id="dict-close" class="icon-button" title="關閉辭典 · Close" aria-label="Close dictionary"></button></div></div><div class="dict-body"><nav id="dict-tabs" role="group" aria-label="Installed dictionaries"><div id="dict-entries" aria-label="Matching entries"></div></nav><div class="dict-main"><div class="dict-frame-wrap"><iframe id="dict-frame" title="Purchased dictionary definition" sandbox="allow-same-origin"></iframe><div id="dict-empty" class="dict-empty"><svg viewBox="0 0 120 90" aria-hidden="true"><path d="M60 22c-12-8-28-10-44-7-1 20-1 40 1 60 16-2 30 0 43 8 13-8 27-10 43-8 2-20 2-40 1-60-16-3-32-1-44 7Zm0 1c-1 20-1 40 0 60"/><path d="M26 34c7-1 14 0 21 3M26 45c7-1 14 0 21 3M73 37c7-3 14-4 21-3M73 48c7-3 14-4 21-3" opacity=".6"/><path d="M98 10c1 4 3 6 7 7-4 1-6 3-7 7-1-4-3-6-7-7 4-1 6-3 7-7Z" class="twinkle"/></svg><b>選一個單字吧</b><span>在左邊反白日文，或在上方輸入 · Select a word on the left, or type above.</span></div></div></div></div>';
  panel.querySelector('#dict-read').innerHTML=(window.readerIcon?readerIcon('speaker'):'');
  panel.querySelector('#dict-close').innerHTML=(window.readerIcon?readerIcon('x'):'');
  panel.querySelector('#dict-help>summary').innerHTML=(window.readerIcon?readerIcon('help'):'');
  const helpBody=panel.querySelector('#dict-help .dict-pop-body');helpBody.append(selectionHint);
  const audioNote=document.createElement('p');audioNote.className='muted';audioNote.textContent='辭典內建的真人發音會以播放器顯示在詞條中；「朗讀」使用瀏覽器的合成語音。Recorded pronunciations appear inside entries; Read aloud uses a browser voice.';helpBody.append(audioNote);
  const emptyNote=panel.querySelector('#dict-empty');
  function setEmpty(title,text){emptyNote.querySelector('b').textContent=title;emptyNote.querySelector('span').textContent=text;}
  for(const pop of panel.querySelectorAll('.dict-pop'))pop.addEventListener('toggle',()=>{if(pop.open)for(const other of panel.querySelectorAll('.dict-pop'))if(other!==pop)other.open=false;});
  document.addEventListener('pointerdown',event=>{for(const pop of panel.querySelectorAll('.dict-pop[open]'))if(!pop.contains(event.target))pop.open=false;});
  const workspace=document.createElement('div');workspace.id='reader-workspace';
  const current=document.querySelector('section.current');
  current.before(workspace);workspace.append(current,panel);
  const preferences=document.createElement('details');preferences.id='dict-preferences';
  preferences.className='dict-pop';
  preferences.innerHTML='<summary class="icon-button" title="選擇辭典與順序 · Choose dictionaries" aria-label="Choose dictionaries"></summary><div class="dict-pop-body"><b>選擇辭典 · Choose dictionaries</b><p class="muted">Checked dictionaries appear in the results. Drag the ⠿ handle to reorder dictionaries. Choices and order are saved automatically.</p><div id="dict-choices"></div></div>';
  preferences.querySelector('summary').innerHTML=(window.readerIcon?readerIcon('list'):'');
  panel.querySelector('#dict-help').before(preferences);
  preferences.addEventListener('toggle',()=>{if(preferences.open)for(const other of panel.querySelectorAll('.dict-pop'))if(other!==preferences)other.open=false;});
  const preferenceKey='fortune-weave-visible-dictionaries-v1';
  let selectedCodes=null;
  try{const saved=JSON.parse(localStorage.getItem(preferenceKey));if(Array.isArray(saved))selectedCodes=new Set(saved);}catch{}
  if(selectedCodes===null)selectedCodes=new Set(['MDX_ALL','MDX_SHO','MDX_MEI']);
  let dictionaries=[],catalog=[],currentCode='',dictionaryOrder=[];
  try{if(!localStorage.getItem('fortune-nhk-added')){selectedCodes.add('MDX_NHK');localStorage.setItem(preferenceKey,JSON.stringify([...selectedCodes]));localStorage.setItem('fortune-nhk-added','1');}}catch{}
  try{if(!localStorage.getItem('fortune-sho-jcd3-added')){selectedCodes.add('MDX_SHO_JCD3');localStorage.setItem(preferenceKey,JSON.stringify([...selectedCodes]));localStorage.setItem('fortune-sho-jcd3-added','1');}}catch{}
  try{if(!localStorage.getItem('fortune-crown-added')){selectedCodes.add('MDX_CROWN');localStorage.setItem(preferenceKey,JSON.stringify([...selectedCodes]));localStorage.setItem('fortune-crown-added','1');}}catch{}
  try{dictionaryOrder=JSON.parse(localStorage.getItem('fortune-dictionary-order')||'[]');if(!Array.isArray(dictionaryOrder))dictionaryOrder=[];}catch{}
  try{if(!localStorage.getItem('fortune-kenkyusha-added')){selectedCodes.add('MDX_KEN');localStorage.setItem(preferenceKey,JSON.stringify([...selectedCodes]));localStorage.setItem('fortune-kenkyusha-added','1');}}catch{}
  try{if(!localStorage.getItem('fortune-new-folder-dicts-v1')){["MDX_NEW_91FD134B", "MDX_NEW_B40701CF", "MDX_NEW_9E8F73AE", "MDX_NEW_D6719330", "MDX_NEW_DCCF31BC", "MDX_NEW_6420A558", "MDX_NEW_894F618D", "MDX_NEW_12ACC0F4", "MDX_NEW_5A4D159D", "MDX_NEW_FA6F3D98"].forEach(code=>selectedCodes.add(code));localStorage.setItem(preferenceKey,JSON.stringify([...selectedCodes]));localStorage.setItem('fortune-new-folder-dicts-v1','1');}}catch{}
  try{if(!localStorage.getItem('fortune-direct-dictionaries-v1')){
    const replacements={SANWIZJ3:'MDX_NEW_D6719330',GENIUSJ3:'MDX_NEW_DCCF31BC',OLEXJE2:'MDX_NEW_6420A558'};
    selectedCodes=new Set([...selectedCodes].map(code=>replacements[code]||code).filter(code=>code.startsWith('MDX_')));
    dictionaryOrder=[...new Set(dictionaryOrder.map(code=>replacements[code]||code).filter(code=>code.startsWith('MDX_')))];
    try{localStorage.setItem(preferenceKey,JSON.stringify([...selectedCodes]));localStorage.setItem('fortune-dictionary-order',JSON.stringify(dictionaryOrder));localStorage.setItem('fortune-direct-dictionaries-v1','1');}catch{}
  }}catch{}
  function ordered(items){return [...items].sort((a,b)=>{const ai=dictionaryOrder.indexOf(a.code),bi=dictionaryOrder.indexOf(b.code);return (ai<0?999:ai)-(bi<0?999:bi);});}
  try{if(!localStorage.getItem('fortune-mdict-added-v1')){['MDX_ALL','MDX_SHO','MDX_MEI'].forEach(c=>selectedCodes.add(c));localStorage.setItem(preferenceKey,JSON.stringify([...selectedCodes]));localStorage.setItem('fortune-mdict-added-v1','1');}}catch{}
  function renderChoices(){
    const choices=document.getElementById('dict-choices');choices.replaceChildren();
    const available=ordered(catalog.length?catalog:dictionaries);
    available.forEach((d,index)=>{
      const label=document.createElement('label'),check=document.createElement('input');
      check.type='checkbox';check.checked=selectedCodes.has(d.code);
      check.onchange=()=>{if(check.checked)selectedCodes.add(d.code);else selectedCodes.delete(d.code);
        try{localStorage.setItem(preferenceKey,JSON.stringify([...selectedCodes]));}catch{status.textContent='Choices apply now, but this browser could not save them.';}
        renderTabs();if(input.value.trim())searchDictionaries(true);
      };
      label.append(check,document.createTextNode(d.name));
      const row=document.createElement('div');row.className='dict-choice-row';row.append(label);
      row.dataset.code=d.code;
      const handle=document.createElement('button');handle.type='button';handle.className='dict-drag-handle';handle.textContent='⠿';handle.setAttribute('aria-label','Drag to reorder '+d.name);handle.title='Drag to reorder; keyboard: Alt + Up / Down';row.prepend(handle);
      function saveOrder(){dictionaryOrder=[...choices.children].map(item=>item.dataset.code);try{localStorage.setItem('fortune-dictionary-order',JSON.stringify(dictionaryOrder));}catch{status.textContent='Order changed, but could not save it.';}renderTabs();}
      handle.draggable=true;
      handle.ondragstart=event=>{event.dataTransfer.setData('text/plain',d.code);event.dataTransfer.effectAllowed='move';row.classList.add('dict-dragging');};
      handle.ondragend=()=>row.classList.remove('dict-dragging');
      row.ondragover=event=>{event.preventDefault();event.dataTransfer.dropEffect='move';};
      row.ondrop=event=>{event.preventDefault();const source=[...choices.children].find(item=>item.dataset.code===event.dataTransfer.getData('text/plain'));if(source&&source!==row){choices.insertBefore(source,event.clientY<row.getBoundingClientRect().top+row.offsetHeight/2?row:row.nextSibling);saveOrder();}};
      handle.onpointerdown=event=>{
        if(event.button!==0||event.pointerType==='mouse')return;
        event.preventDefault();handle.setPointerCapture(event.pointerId);row.classList.add('dict-dragging');
        const original=[...choices.children];
        handle.onpointermove=move=>{
          const target=[...choices.children].find(item=>{const r=item.getBoundingClientRect();return move.clientY>=r.top&&move.clientY<=r.bottom;});
          if(target&&target!==row&&target.parentElement===choices){const rect=target.getBoundingClientRect();choices.insertBefore(row,move.clientY<rect.top+rect.height/2?target:target.nextSibling);}
          if(move.clientY<60)window.scrollBy(0,-25);else if(move.clientY>window.innerHeight-60)window.scrollBy(0,25);
        };
        const finish=cancel=>{handle.onpointermove=null;handle.onpointerup=null;handle.onpointercancel=null;row.classList.remove('dict-dragging');if(handle.hasPointerCapture(event.pointerId))handle.releasePointerCapture(event.pointerId);if(cancel)original.forEach(item=>choices.append(item));else saveOrder();};
        handle.onpointerup=()=>finish(false);handle.onpointercancel=()=>finish(true);
      };
      handle.onkeydown=event=>{if(!event.altKey||!['ArrowUp','ArrowDown'].includes(event.key))return;event.preventDefault();const sibling=event.key==='ArrowUp'?row.previousElementSibling:row.nextElementSibling;if(sibling){choices.insertBefore(row,event.key==='ArrowUp'?sibling:sibling.nextSibling);saveOrder();handle.focus();}};
      choices.append(row);
    });
  }
  // Tabs show a compact name; the full title stays in the tooltip and the entry page.
  function shortDictionaryName(full){
    const base=String(full||'').replace(/\s*[（(]?第\s*\d+\s*版[）)]?/g,'').trim();
    const short=base.replace(/^[（(][^）)]*[）)]\s*/,'').replace(/^(大修館|旺文社|小学館|三省堂|研究社|講談社|朝日出版社|くろしお出版|岩波書店)\s*/,'').replace(/(新|大)?(辞典|辞書)(?=\s|·|［|$)/g,'').replace(/\s+·\s+/,' · ').trim();
    return short.length>=2?short:base;
  }
  function renderTabs(){
    tabs.replaceChildren();const visible=ordered(dictionaries.filter(d=>selectedCodes.has(d.code)));
    visible.forEach(d=>{const b=document.createElement('button');b.type='button';b.dataset.code=d.code;b.className='dict-tab';
      const name=document.createElement('span');name.className='dict-tab-name';name.textContent=shortDictionaryName(d.name);
      const count=document.createElement('span');count.className='dict-tab-count';count.textContent=d.error?'!':String(d.count);
      b.append(name,count);b.title=d.name+' ('+(d.error?'error':d.count)+')';
      b.classList.toggle('empty',!!d.error||!d.entries.length);b.classList.toggle('error',!!d.error);
      b.onclick=()=>{
        // Clicking the open dictionary again folds or unfolds its headword list.
        if(d.code===currentCode&&b.classList.contains('active')&&entries.isConnected){const folded=entries.classList.toggle('collapsed');b.setAttribute('aria-expanded',String(!folded));return;}
        choose(d);
      };
      tabs.append(b);
    });
    const first=visible.find(d=>d.code===currentCode)||visible.find(d=>d.entries.length)||visible[0];
    if(first)choose(first);else{currentCode='';tabs.append(entries);entries.textContent='No dictionaries selected. Open “Choose dictionaries” to enable one.';frame.removeAttribute('src');setEmpty('還沒有選擇辭典','按上方的清單圖示選擇要查的辭典 · Open the list icon to choose dictionaries.');}
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
  // Dictionary typeface: book-style serif (default) or gothic.
  let dictionaryFont='serif';
  try{if(localStorage.getItem('jp-reader-dict-font')==='sans')dictionaryFont='sans';}catch{}
  const fontToggle=document.createElement('button');fontToggle.type='button';fontToggle.className='dict-font-toggle';
  function applyDictionaryFont(){
    fontToggle.textContent=dictionaryFont==='sans'?'ゴ':'明';
    fontToggle.title=dictionaryFont==='sans'?'辭典字體：黑體（按一下改為明朝）· Gothic':'辭典字體：明朝（按一下改為黑體）· Serif';
    fontToggle.setAttribute('aria-label','Dictionary typeface: '+(dictionaryFont==='sans'?'gothic':'serif'));
    try{const root=frame.contentDocument?.documentElement;if(root)root.dataset.font=dictionaryFont;}catch{}
  }
  fontToggle.onclick=()=>{dictionaryFont=dictionaryFont==='sans'?'serif':'sans';try{localStorage.setItem('jp-reader-dict-font',dictionaryFont);}catch{}applyDictionaryFont();};
  zoomControls.append(zoomOut,zoomReset,zoomIn,fontToggle);applyDictionaryFont();panel.querySelector('.dict-toolbar').prepend(zoomControls);applyDictionaryZoom();
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
  function navigateDictionaryWithLetters(event){
    if(event.defaultPrevented||event.isComposing||event.altKey||event.ctrlKey||event.metaKey||event.shiftKey||panel.hidden||searchPending)return;
    const key=event.key.toLowerCase();
    if(key!=='a'&&key!=='d')return;
    const target=event.target;
    if(target?.isContentEditable||target?.closest?.('input,textarea,select,audio,video,[contenteditable],[role="textbox"],[role="slider"],[role="combobox"],[role="listbox"],[role="tablist"]'))return;
    const visible=ordered(dictionaries.filter(d=>selectedCodes.has(d.code)));
    const current=visible.findIndex(d=>d.code===currentCode);
    const direction=key==='d'?1:-1;
    for(let step=1;step<=visible.length;step++){
      const index=(current+direction*step+visible.length)%visible.length;
      const dictionary=visible[index];
      if(dictionary.error||!dictionary.entries.length||dictionary.code===currentCode)continue;
      event.preventDefault();
      if(!event.repeat)choose(dictionary);
      return;
    }
  }
  function pasteAndSearch(event){
    if(event.defaultPrevented)return;
    const target=event.target;
    const readOnlyPassage=target?.closest?.('#latest')?.getAttribute('contenteditable')==='false';
    if(!readOnlyPassage&&(target?.isContentEditable||target?.closest?.('input,textarea,select,[contenteditable],[role="textbox"],[role="combobox"]')))return;
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
      if(target.closest('button,input,textarea,select,audio,video,summary')||(target.closest('[contenteditable]')&&!target.closest('#latest')))return;
      const host=insideEntry?doc.body:target.closest('#latest,#latestenglish,#latestchinese,[data-lookup]');
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
    doc.addEventListener('keydown',navigateDictionaryWithLetters);
    doc.addEventListener('keydown',navigateDictionaryWithUndo);
    doc.addEventListener('keydown',event=>{
      if(event.key==='Shift'){skipLookup=true;cancelLookup();}
      if((event.ctrlKey||event.metaKey)&&event.key.toLowerCase()==='c')cancelLookup();
    });
    doc.addEventListener('pointerdown',event=>{
      cancelLookup();skipLookup=event.shiftKey;
      const target=event.target;
      selecting=event.button===0&&!target.closest('button,input,textarea,select,a,audio,summary')&&(!target.closest('[contenteditable]')||!!target.closest('#latest'))&&
        (insideEntry||!!target.closest('#latest,#latestenglish,#latestchinese,[data-lookup]'));
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
  frame.addEventListener('load',()=>{
    // Entries stay sandboxed; the parent can read selections in local documents.
    let entryDocument;try{entryDocument=frame.contentDocument;}catch{return;}
    if(!entryDocument)return;
    try{const code=new URL(frame.src,location.href).searchParams.get('code');if(code&&entryDocument.body)entryDocument.body.dataset.dict=code;}catch{}
    applyDictionaryFont();
    applyDictionaryZoom();
    window.readerTheme?.themeFrame(frame);
    if(window.readerShortcutKeydown)entryDocument.addEventListener('keydown',window.readerShortcutKeydown);
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
  const back=document.createElement('button');back.type='button';back.id='dict-back';back.innerHTML=(window.readerIcon?readerIcon('left'):'');back.setAttribute('aria-label','Previous search');back.title='Previous search (Ctrl+Z)';back.disabled=true;
  back.hidden=true;panel.append(back);
  const next=document.createElement('button');next.type='button';next.id='dict-next';next.innerHTML=(window.readerIcon?readerIcon('right'):'');next.setAttribute('aria-label','Next search');next.title='Next search (Ctrl+Shift+Z)';next.hidden=true;back.after(next);
  const leftBack=back.cloneNode(true),leftNext=next.cloneNode(true);leftBack.hidden=leftNext.hidden=false;leftBack.id='lookup-back';leftNext.id='lookup-next';input.before(leftBack,leftNext);
  function updateBack(){
    for(const control of [back,leftBack]){control.disabled=!searchHistory.length&&!(searchPending&&spokenWord);control.title=searchHistory.length?'Previous: '+searchHistory.at(-1).word:'No earlier search';}
    for(const control of [next,leftNext]){control.disabled=!forwardHistory.length;control.title=forwardHistory.length?'Next: '+forwardHistory.at(-1).word:'No later search';}
  }
  function rememberSearch(stack,saved){if(saved){stack.push(saved);if(stack.length>5)stack.shift();}}
  function snapshotSearch(){
    if(!spokenWord)return null;
    return {word:spokenWord,dictionaries,code:currentCode,entry:currentEntry};
  }
  function restoreSearch(saved){
    spokenWord=saved.word;input.value=saved.word;dictionaries=saved.dictionaries;currentCode=saved.code;panel.hidden=false;if(panel.querySelector('.dictionary-disclosure'))panel.querySelector('.dictionary-disclosure').open=true;
    renderChoices();renderTabs();
    const dictionary=dictionaries.find(d=>d.code===saved.code&&selectedCodes.has(d.code));
    if(dictionary&&saved.entry)openEntry(dictionary,saved.entry);
    status.textContent='“'+saved.word+'” · Search restored.';wordLabel.textContent=saved.word;
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
  for(const control of [back,leftBack])control.setAttribute('aria-keyshortcuts','ArrowLeft');
  for(const control of [next,leftNext])control.setAttribute('aria-keyshortcuts','ArrowRight');
  selectionHint.textContent+=' Use ← / → for previous / next dictionary search (outside text fields).';
  const dictionaryShortcutHint=document.createElement('p');dictionaryShortcutHint.className='muted';
  dictionaryShortcutHint.textContent='A / D: previous / next dictionary with matches for this word. Skips empty dictionaries and wraps around (outside text fields).';
  helpBody.append(dictionaryShortcutHint);
  function openEntry(dictionary,row){
    currentEntry=row;
    const params=new URLSearchParams({code:dictionary.code,id:row.id,anchor:row.anchor||''});
    frame.src='/api/dictionary/entry?'+params;
    [...entries.children].forEach(b=>b.classList.toggle('active',b.dataset.entry===String(row.id)+'#'+row.anchor));
  }
  function choose(dictionary){
    currentEntry=null;
    currentCode=dictionary.code;
    [...tabs.children].forEach(b=>{const selected=b.dataset.code===dictionary.code;b.classList.toggle('active',selected);b.setAttribute('aria-pressed',String(selected));});
    entries.replaceChildren();frame.removeAttribute('src');
    const activeTab=[...tabs.children].find(b=>b.dataset?.code===dictionary.code);if(activeTab)activeTab.after(entries);else tabs.append(entries);
    entries.classList.toggle('single',dictionary.entries.length===1);entries.classList.remove('collapsed');if(activeTab){activeTab.setAttribute('aria-expanded','true');activeTab.title=activeTab.title.replace(/ · 再按一次收合.*$/,'')+' · 再按一次收合／展開';}
    if(dictionary.error){entries.textContent='Dictionary error: '+dictionary.error;setEmpty('這本辭典出錯了',dictionary.error);return;}
    if(!dictionary.entries.length){entries.textContent='No matches in this dictionary.';setEmpty('這本辭典查不到「'+spokenWord+'」','按 A / D 換一本有結果的辭典 · Press A / D for the next dictionary with results.');return;}
    dictionary.entries.forEach(row=>{
      const b=document.createElement('button');b.type='button';b.dataset.entry=String(row.id)+'#'+row.anchor;b.dataset.id=String(row.id);
      drawEntryLabel(b,row,entryLabels.get(dictionary.code+':'+row.id));
      b.onclick=()=>openEntry(dictionary,row);entries.append(b);
    });
    openEntry(dictionary,dictionary.entries[0]);
    loadEntryLabels(dictionary);
  }
  // Headword list: add the written (kanji) form, e.g. 高騰 above こうとう.
  const entryLabels=new Map();
  function drawEntryLabel(b,row,label){
    b.replaceChildren();b.classList.toggle('has-kanji',!!label);
    if(!label){b.textContent=row.title;b.title=row.title;return;}
    const kanji=document.createElement('span');kanji.className='entry-kanji';kanji.lang='ja';kanji.textContent=label;
    const kana=document.createElement('span');kana.className='entry-kana';kana.lang='ja';kana.textContent=row.title;
    b.append(kanji,kana);b.title=row.title.replace(/ · .*$/,'')+'【'+label+'】';
  }
  async function loadEntryLabels(dictionary){
    if(dictionary.entries.length<2)return;
    const missing=dictionary.entries.filter(row=>!entryLabels.has(dictionary.code+':'+row.id)).map(row=>row.id);
    if(missing.length){
      try{
        const response=await fetch('/api/dictionary/labels?'+new URLSearchParams({code:dictionary.code,ids:missing.join(',')}));
        if(!response.ok)return;
        const data=await response.json();
        for(const id of missing)entryLabels.set(dictionary.code+':'+id,data.labels?.[String(id)]||'');
      }catch{return;}
    }
    if(currentCode!==dictionary.code)return;
    for(const b of entries.querySelectorAll('button[data-id]')){
      const row=dictionary.entries.find(r=>String(r.id)===b.dataset.id);
      if(row)drawEntryLabel(b,row,entryLabels.get(dictionary.code+':'+row.id));
    }
  }
  button.innerHTML=(window.readerIcon?readerIcon('search'):'')+'<span>查詢</span>';button.title='在我的辭典中查詢 · Look up in my dictionaries (Enter)';
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
      spokenWord=word;panel.hidden=false;if(panel.querySelector('.dictionary-disclosure'))panel.querySelector('.dictionary-disclosure').open=true;dictionaries=result.dictionaries;currentCode='';renderChoices();renderTabs();
      status.textContent='“'+word+'” · '+dictionaries.filter(d=>d.entries?.length).length+' 本辭典有結果 · A / D 切換';
      wordLabel.textContent=word;rememberWord(word);window.dispatchEvent(new CustomEvent('reader-lookup',{detail:{word}}));
    }catch(e){if(version===requestVersion)status.textContent=e.message;}finally{if(version===requestVersion){button.disabled=false;searchPending=false;updateBack();}}
  }
  button.onclick=()=>searchDictionaries();
  const wordLabel=document.getElementById('dict-word');
  // Recently searched words, one click to look them up again.
  const recentKey='jp-reader-recent-words';
  const recentBox=document.createElement('div');recentBox.id='recent-words';recentBox.className='recent-words';recentBox.setAttribute('aria-label','Recent searches');
  document.querySelector('[aria-label="Quick dictionary search"]').append(recentBox);
  function recentWords(){try{const v=JSON.parse(localStorage.getItem(recentKey)||'[]');return Array.isArray(v)?v.filter(w=>typeof w==='string').slice(0,14):[];}catch{return [];}}
  function drawRecent(){
    const words=recentWords();recentBox.replaceChildren();recentBox.hidden=!words.length;
    if(!words.length)return;
    const label=document.createElement('span');label.className='recent-label';label.textContent='最近 ·';recentBox.append(label);
    for(const w of words){const chip=document.createElement('button');chip.type='button';chip.className='word-chip';chip.textContent=w;chip.lang='ja';chip.title='再查一次「'+w+'」';chip.onclick=()=>{input.value=w;searchDictionaries();};recentBox.append(chip);}
  }
  function rememberWord(word){if(Array.from(word).length>20)return;const words=[word,...recentWords().filter(w=>w!==word)].slice(0,14);try{localStorage.setItem(recentKey,JSON.stringify(words));}catch{}drawRecent();}
  drawRecent();
  input.addEventListener('keydown',e=>{if(e.key==='Enter'){e.preventDefault();button.click();}});
  document.getElementById('dict-close').onclick=()=>{panel.hidden=true;if(window.speechSynthesis)speechSynthesis.cancel();window.dispatchEvent(new Event('reader-layout'));};
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
  preferences.querySelector('p').textContent='只搜尋勾選的辭典；拖曳 ⠿ 調整順序（或 Alt + ↑ / ↓）。設定會自動儲存。';
  fetch('/api/dictionary/catalog').then(r=>{if(!r.ok)throw Error('catalog');return r.json();}).then(data=>{catalog=data.dictionaries;renderChoices();}).catch(()=>{});
})();
