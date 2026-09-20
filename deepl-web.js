(() => {
 const status=document.getElementById('translation-state');
 const manual=document.createElement('button');manual.id='translate-current';manual.type='button';manual.textContent='Translate this text · Local model';
 const hint=document.createElement('p');hint.className='muted';hint.textContent='Local translation: keep LM Studio open with your selected model loaded and its server on. Auto fills missing English + 繁體中文; turn Auto off for manual mode. Text stays on this computer.';
 const feedback=document.createElement('p');feedback.setAttribute('role','status');status.after(hint,manual,feedback);
 const controls=document.createElement('div');controls.className='toolbar';
 const label=document.createElement('label');label.textContent='Translation model ';const select=document.createElement('select');select.id='translation-model';label.append(select);
 const refresh=document.createElement('button');refresh.textContent='Refresh models';refresh.type='button';
 const load=document.createElement('button');load.textContent='Load selected model';load.type='button';controls.append(label,refresh,load);hint.after(controls);
 async function listModels(){
  try{const r=await fetch('/api/local-models');const data=await r.json();if(!r.ok)throw Error(data.error||'Start the LM Studio server first.');
   select.replaceChildren();for(const m of data.models){const option=document.createElement('option');option.value=m.id;option.textContent=m.id+' · '+m.quantization+(m.state==='loaded'?' · loaded':'');select.append(option);}select.value=data.selected;
   if(!select.value&&data.models.length)select.value=data.models[0].id;
   manual.disabled=!data.available;load.disabled=!data.available||!data.models.length;select.disabled=!data.available;
   document.getElementById('paste-translate').disabled=!data.available;
   if(!data.available)document.getElementById('paste-status').textContent='Reading and dictionaries are ready. No local AI is connected; use Copy learning prompt.';
   feedback.textContent=data.available?'Local AI server connected. Choose a model, then load it.':data.message;
  }catch(e){feedback.textContent=e.message;}
 }
 refresh.onclick=listModels;
 load.onclick=async()=>{load.disabled=true;refresh.disabled=true;select.disabled=true;feedback.textContent='Loading model… The previous reader model will be unloaded to free VRAM.';
  try{const r=await fetch('/api/local-model',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({model:select.value})});const data=await r.json();if(!r.ok)throw Error(data.error||'Model could not load');feedback.textContent='Ready: '+data.selected;await listModels();}catch(e){feedback.textContent=e.message;}finally{load.disabled=false;refresh.disabled=false;select.disabled=false;}
 };
 listModels();
 manual.onclick=async()=>{const id=Number(document.getElementById('latestmeta').textContent.match(/Journal #([0-9]+)/)?.[1]);if(!id){feedback.textContent='No saved sentence is displayed.';return;}
 manual.disabled=true;try{const r=await fetch('/api/local-translate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id})});const result=await r.json();if(!r.ok)throw Error(result.error||'Local translation unavailable');feedback.textContent='Sentence #'+id+' queued for local translation.';}catch(e){feedback.textContent=e.message;}finally{manual.disabled=false;}};
})();
