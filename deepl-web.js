(() => {
 const status=document.getElementById('translation-state');
 const manual=document.createElement('button');manual.id='translate-current';manual.type='button';manual.textContent='Translate this text';
 const hint=document.createElement('p');hint.className='muted';
 const feedback=document.createElement('p');feedback.id='engine-feedback';feedback.setAttribute('role','status');
 const controls=document.createElement('div');controls.className='toolbar';
 const engineLabel=document.createElement('label');engineLabel.textContent='Translation engine ';
 const engine=document.createElement('select');engine.id='translation-engine';engineLabel.append(engine);
 const label=document.createElement('label');label.textContent='Model / language package ';
 const select=document.createElement('select');select.id='translation-model';label.append(select);
 const refresh=document.createElement('button');refresh.textContent='Refresh options';refresh.type='button';
 const load=document.createElement('button');load.id='use-translation-engine';load.textContent='Use selection';load.type='button';
 controls.append(engineLabel,label,refresh,load);status.after(controls,hint,manual,feedback);
 let catalog=null,busy=false;
 function renderModels(){
  const info=catalog.engines.find(item=>item.id===engine.value);
  select.replaceChildren();
  for(const model of info.models){const option=document.createElement('option');option.value=model.id;option.textContent=model.label;select.append(option);}
  select.value=info.selected;
  if(!select.value&&info.models.length)select.value=info.models[0].id;
  hint.textContent=info.message;
  update();
 }
 function update(){
  const info=catalog?.engines.find(item=>item.id===engine.value);
  const active=info&&engine.value===catalog.selected_engine&&select.value===info.selected;
  const ready=active&&info.available&&info.models.some(m=>m.id===select.value&&['ready','loaded'].includes(m.state));
  engine.disabled=busy;select.disabled=busy||!info?.available;refresh.disabled=busy;
  load.disabled=busy||!info?.available||!select.value;
  manual.disabled=busy||!ready;
 }
 async function listModels(){
  const response=await fetch('/api/translation-options');const data=await response.json();
  if(!response.ok)throw Error(data.error||'Could not read translation options.');
  catalog=data;engine.replaceChildren();
  for(const item of data.engines){const option=document.createElement('option');option.value=item.id;option.textContent=item.label+(item.available?'':' · unavailable');engine.append(option);}
  engine.value=data.selected_engine;renderModels();
  const active=data.engines.find(item=>item.id===data.selected_engine);
  feedback.textContent=active.available?'Active: '+active.label:active.message;
 }
 refresh.onclick=()=>listModels().catch(error=>feedback.textContent=error.message);
 engine.onchange=()=>{renderModels();feedback.textContent='Click Use selection to activate this engine and model.';};
 select.onchange=()=>{update();feedback.textContent='Click Use selection to activate this engine and model.';};
 load.onclick=async()=>{
  busy=true;update();feedback.textContent='Preparing your selection…';
  try{
   const response=await fetch('/api/translation-engine',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({engine:engine.value,model:select.value})});
   const data=await response.json();if(!response.ok)throw Error(data.error||'Could not select this engine.');
   await listModels();
  }catch(error){feedback.textContent=error.message;}
  finally{busy=false;update();}
 };
 manual.onclick=async()=>{
  const id=Number(document.getElementById('latestmeta').textContent.match(/Journal #([0-9]+)/)?.[1]);
  if(!id){feedback.textContent='Open saved text before translating.';return;}
  busy=true;update();
  try{
   const response=await fetch('/api/local-translate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id})});
   const data=await response.json();if(!response.ok)throw Error(data.error||'Translation unavailable');
   feedback.textContent='Text #'+id+' queued. Translation progress appears above.';
  }catch(error){feedback.textContent=error.message;}
  finally{busy=false;update();}
 };
 manual.disabled=true;
 listModels().catch(error=>feedback.textContent=error.message);
})();
