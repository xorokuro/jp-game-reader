// Appearance engine: palette presets, hand-drawn doodle background, reading typography.
// Browser-local only (mirrored to data/reading/preferences.json); never touches journal entries.
(() => {
 'use strict';
 const KEY='jp-reader-theme-v2',OLD_KEY='dimension-journal-theme-v1',ENTRY_KEY='jp-reader-entry-theme';

 // ---------------------------------------------------------------- presets
 const PRESETS={
  washi:{zh:'和紙',en:'Washi paper',mode:'light',paper:'#f3eadb',card:'#fffaf1',ink:'#3b2f28',accent:'#c9573a',accent2:'#6e9a5b',accent3:'#d6a03e',
   doodles:['#c9573a','#6e9a5b','#d6a03e','#7f9fc4'],motifs:['sakura','cloud','wave','kana','onigiri','star','cat','petal'],fall:'petal'},
  sakura:{zh:'桜',en:'Sakura',mode:'light',paper:'#f8e8ec',card:'#fffafb',ink:'#4a2f3a',accent:'#d2557a',accent2:'#6f9dc9',accent3:'#e39b45',
   doodles:['#e07a98','#d2557a','#6f9dc9','#e3b04f'],motifs:['sakura','petal','heart','kana','sparkle','cloud','cat','sakura'],fall:'petal'},
  umi:{zh:'海辺',en:'Seaside',mode:'light',paper:'#e4eef1',card:'#fbfdfd',ink:'#203b48',accent:'#237ea1',accent2:'#e0704f',accent3:'#d9a93d',
   doodles:['#237ea1','#5fb0c9','#e0704f','#d9a93d'],motifs:['wave','fish','bubble','sparkle','kana','cloud','wave','shell'],fall:'bubble'},
  sumi:{zh:'墨',en:'Sumi ink',mode:'light',paper:'#efece5',card:'#fcfbf7',ink:'#262422',accent:'#b0392e',accent2:'#4f5b57',accent3:'#9a8b73',
   doodles:['#262422','#262422','#b0392e','#6d6a64'],motifs:['enso','wave','kana','cloud','kana','dots'],fall:''},
  matcha:{zh:'抹茶',en:'Matcha night',mode:'dark',paper:'#1b2520',card:'#243029',ink:'#edf2e4',accent:'#a6d08a',accent2:'#f0cd8a',accent3:'#e89d8a',
   doodles:['#a6d08a','#f0cd8a','#e89d8a','#8cc3b4'],motifs:['leaf','teacup','sparkle','kana','cloud','cat','dots','onigiri'],fall:'leaf'},
  engawa:{zh:'夜の縁側',en:'Lantern night',mode:'dark',paper:'#211c29',card:'#2c2535',ink:'#f4e9dc',accent:'#f1b15a',accent2:'#e98aa6',accent3:'#9cc6e6',
   doodles:['#f1b15a','#e98aa6','#9cc6e6','#c9b3f0'],motifs:['lantern','moon','star','cat','sparkle','kana','cloud','sparkle'],fall:'sparkle'},
  momiji:{zh:'紅葉',en:'Autumn leaves',mode:'dark',paper:'#29201b',card:'#352822',ink:'#f7e9d8',accent:'#f08b4c',accent2:'#e9c46a',accent3:'#b7d07b',
   doodles:['#f08b4c','#e9c46a','#d8654a','#b7d07b'],motifs:['maple','leaf','kana','teacup','sparkle','cloud','maple','dots'],fall:'maple'},
  hoshi:{zh:'星空',en:'Starry sky',mode:'dark',paper:'#141a2d',card:'#1d253f',ink:'#e9edff',accent:'#ffd27a',accent2:'#9fd0ff',accent3:'#f5a0c2',
   doodles:['#ffd27a','#9fd0ff','#f5a0c2','#c4b5ff'],motifs:['star','sparkle','moon','planet','kana','cat','dots','star'],fall:'sparkle'}
 };
 const ORDER=['washi','sakura','umi','sumi','matcha','engawa','momiji','hoshi'];
 const FONTS={
  kyokasho:{zh:'教科書體',en:'Textbook',css:'"UD Digi Kyokasho N-R","UD デジタル 教科書体 N-R","UD Digi Kyokasho NK-R","Klee One","Yu Mincho",serif'},
  gothic:{zh:'黑體',en:'Gothic',css:'"Yu Gothic UI","Yu Gothic","Noto Sans JP","Hiragino Kaku Gothic ProN","Meiryo",sans-serif'},
  mincho:{zh:'明朝',en:'Mincho',css:'"Yu Mincho","YuMincho","Noto Serif JP","Hiragino Mincho ProN","MS PMincho",serif'}
 };
 const DENSITY={none:0,calm:10,normal:18,lively:30};
 const LIMITS={jp:[18,48],translation:[14,36],spacing:[1.3,2.6],width:[900,2200],radius:[4,30]};
 const DEFAULTS={preset:'washi',custom:{},density:'normal',grain:true,falling:true,font:'kyokasho',jp:30,translation:20,spacing:1.9,width:1640,radius:20};

 let theme={...DEFAULTS,custom:{}};
 function clamp(k,v){const [a,b]=LIMITS[k];return Math.max(a,Math.min(b,v));}
 function load(){
  let saved=null;try{saved=JSON.parse(localStorage.getItem(KEY)||'null');}catch{}
  if(saved&&typeof saved==='object'){
   if(PRESETS[saved.preset])theme.preset=saved.preset;
   if(saved.custom&&typeof saved.custom==='object')for(const k of ['paper','card','accent'])if(/^#[0-9a-f]{6}$/i.test(saved.custom[k]||''))theme.custom[k]=saved.custom[k].toLowerCase();
   if(DENSITY[saved.density]!==undefined)theme.density=saved.density;
   for(const k of ['grain','falling'])if(typeof saved[k]==='boolean')theme[k]=saved[k];
   if(FONTS[saved.font])theme.font=saved.font;
   for(const k of Object.keys(LIMITS))if(Number.isFinite(saved[k]))theme[k]=clamp(k,saved[k]);
   return;
  }
  // First run after the redesign: carry reading sizes over, pick a preset near the old palette.
  try{const old=JSON.parse(localStorage.getItem(OLD_KEY)||'null');
   if(old){
    for(const [k,o] of [['jp','jp'],['translation','translation'],['spacing','spacing'],['radius','radius']])if(Number.isFinite(old[o]))theme[k]=clamp(k,old[o]);
    if(/^#[0-9a-f]{6}$/i.test(old.card||''))theme.preset=luminance(old.card)<.2?'matcha':'washi';
   }}catch{}
 }

 // ---------------------------------------------------------------- colour maths
 const rgb=hex=>hex.slice(1).match(/../g).map(x=>parseInt(x,16)/255);
 function luminance(hex){return rgb(hex).map(v=>v<=.04045?v/12.92:((v+.055)/1.055)**2.4).reduce((a,v,i)=>a+v*[.2126,.7152,.0722][i],0);}
 function contrast(a,b){const x=luminance(a),y=luminance(b);return (Math.max(x,y)+.05)/(Math.min(x,y)+.05);}
 function mix(a,b,t){const x=rgb(a),y=rgb(b);return '#'+x.map((v,i)=>Math.round((v*(1-t)+y[i]*t)*255).toString(16).padStart(2,'0')).join('');}
 function readable(bg,preferred,light='#fffaf3',dark='#2a211c'){if(contrast(bg,preferred)>=6)return preferred;return contrast(bg,light)>=contrast(bg,dark)?light:dark;}
 function palette(){
  const p={...PRESETS[theme.preset]};
  for(const k of ['paper','card','accent'])if(theme.custom[k])p[k]=theme.custom[k];
  p.mode=luminance(p.paper)<.2?'dark':'light';
  p.ink=readable(p.card,p.ink);
  p.paperInk=readable(p.paper,p.ink);
  // Keep the accent legible as text on cards; nudge toward ink until it reaches 3:1.
  let accentText=p.accent;for(let i=0;i<12&&contrast(p.card,accentText)<3.2;i++)accentText=mix(accentText,p.ink,.12);
  p.accentText=accentText;
  p.onAccent=contrast(p.accent,'#ffffff')>=contrast(p.accent,'#1d1712')?'#ffffff':'#1d1712';
  return p;
 }

 // ---------------------------------------------------------------- apply
 const root=document.documentElement;
 let current=null;
 function apply(save=true){
  const p=palette();current=p;
  const vars={paper:p.paper,'paper-ink':p.paperInk,card:p.card,ink:p.ink,accent:p.accent,'accent-text':p.accentText,'accent-2':p.accent2,'accent-3':p.accent3,'on-accent':p.onAccent,
   'jp-font':FONTS[theme.font].css,'jp-size':theme.jp+'px','translation-size':theme.translation+'px','line-space':theme.spacing,'reader-width':theme.width+'px',rounding:theme.radius+'px'};
  for(const [k,v] of Object.entries(vars))root.style.setProperty('--'+k,v);
  root.dataset.mode=p.mode;root.dataset.preset=theme.preset;
  root.style.colorScheme=p.mode;
  root.classList.toggle('no-grain',!theme.grain);
  root.classList.toggle('no-falling',!theme.falling);
  const meta=document.querySelector('meta[name="theme-color"]');if(meta)meta.content=p.paper;
  drawDoodles(p);drawFalling(p);themeFrame();
  if(save){
   try{localStorage.setItem(KEY,JSON.stringify(theme));localStorage.setItem(ENTRY_KEY,JSON.stringify(entryColors()));say('✓ 已自動儲存');}
   catch{say('可以預覽，但瀏覽器無法保存設定。');}
  }
  syncControls();
 }
 // Colours handed to purchased-dictionary entries (sandboxed iframe, no scripts).
 function entryColors(){
  const p=current||palette();
  const bg=p.card;
  // Example phrases use a book-like ink blue, tinted slightly toward the palette.
  let ex=p.mode==='dark'?mix('#a9c8f5',p.accent2,.18):mix('#1f3f8f',p.accent2,.12);
  for(let i=0;i<10&&contrast(bg,ex)<4.8;i++)ex=mix(ex,p.mode==='dark'?'#ffffff':'#000000',.12);
  return {bg,fg:p.ink,muted:mix(p.ink,bg,.38),link:p.mode==='dark'?mix(p.accent2,'#ffffff',.15):mix(p.accent2,p.ink,.35),strong:p.accentText,border:mix(p.ink,bg,.82),sel:mix(p.accent,bg,.6),ex,scheme:p.mode};
 }
 function themeFrame(frame=document.getElementById('dict-frame')){
  if(!frame)return;
  let doc;try{doc=frame.contentDocument;}catch{return;}
  if(!doc?.documentElement)return;
  const c=entryColors(),s=doc.documentElement.style;
  for(const k of ['bg','fg','muted','link','strong','border','sel','ex'])s.setProperty('--e-'+k,c[k]);
  s.colorScheme=c.scheme;doc.documentElement.dataset.scheme=c.scheme;
 }
 window.readerTheme={themeFrame,entryColors,get palette(){return current||palette();}};

 // ---------------------------------------------------------------- hand-drawn doodles
 function rng(seed){return()=>{seed|=0;seed=seed+0x6D2B79F5|0;let t=Math.imul(seed^seed>>>15,1|seed);t=t+Math.imul(t^t>>>7,61|t)^t;return((t^t>>>14)>>>0)/4294967296;};}
 const f=n=>n.toFixed(1);
 function smooth(pts,closed){
  const n=pts.length,get=i=>closed?pts[(i+n)%n]:pts[Math.max(0,Math.min(n-1,i))];
  let d='M'+f(pts[0][0])+' '+f(pts[0][1]);
  for(let i=0;i<(closed?n:n-1);i++){
   const p0=get(i-1),p1=get(i),p2=get(i+1),p3=get(i+2);
   d+='C'+f(p1[0]+(p2[0]-p0[0])/6)+' '+f(p1[1]+(p2[1]-p0[1])/6)+' '+f(p2[0]-(p3[0]-p1[0])/6)+' '+f(p2[1]-(p3[1]-p1[1])/6)+' '+f(p2[0])+' '+f(p2[1]);
  }
  return closed?d+'Z':d;
 }
 const ring=(r,n=14,a0=0,a1=Math.PI*2)=>Array.from({length:n+1},(_,i)=>{const a=a0+(a1-a0)*i/n;return [Math.cos(a)*r,Math.sin(a)*r];});
 const poly=(pts,s=1)=>pts.map(([x,y])=>[x*s,y*s]);
 const rot=(pts,a)=>pts.map(([x,y])=>[x*Math.cos(a)-y*Math.sin(a),x*Math.sin(a)+y*Math.cos(a)]);
 const move=(pts,dx,dy)=>pts.map(([x,y])=>[x+dx,y+dy]);
 const PETAL=[[0,-.72],[.2,-1],[.46,-.8],[.6,-.3],[.46,.3],[.16,.8],[0,.95],[-.16,.8],[-.46,.3],[-.6,-.3],[-.46,-.8],[-.2,-1]];
 // Each motif returns strokes [{pts,closed,fill?}] in a unit box (≈ -1…1), or text.
 const MOTIFS={
  star:()=>[{pts:Array.from({length:10},(_,i)=>{const a=-Math.PI/2+i*Math.PI/5,r=i%2?.44:1;return [Math.cos(a)*r,Math.sin(a)*r];}),closed:true,fill:.18}],
  sparkle:()=>[{pts:Array.from({length:8},(_,i)=>{const a=-Math.PI/2+i*Math.PI/4,r=i%2?.2:1;return [Math.cos(a)*r,Math.sin(a)*r];}),closed:true,fill:.25},{pts:ring(.12,6),closed:true,fill:.6,at:[.9,-.8]}],
  petal:()=>[{pts:poly(PETAL,.8),closed:true,fill:.22}],
  sakura:()=>[...Array.from({length:5},(_,k)=>({pts:rot(move(poly(PETAL,.5),0,-.52),k*Math.PI*2/5),closed:true,fill:.16})),{pts:ring(.13,6),closed:true,fill:.5}],
  heart:()=>[{pts:[[0,-.45],[.35,-.9],[.85,-.65],[.8,-.05],[0,.8],[-.8,-.05],[-.85,-.65],[-.35,-.9]],closed:true,fill:.2}],
  cloud:()=>{const pts=[[-1,.35]];for(const [cx,r,a,b] of [[-.58,.38,Math.PI,Math.PI*1.9],[.02,.55,Math.PI*1.1,Math.PI*1.95],[.62,.36,Math.PI*1.15,Math.PI*2]])for(let i=0;i<=5;i++){const t=a+(b-a)*i/5;pts.push([cx+Math.cos(t)*r,.35+Math.sin(t)*r]);}pts.push([1,.35]);
   const swirl=Array.from({length:9},(_,i)=>{const t=i*.75,r=.05+i*.035;return [.02+Math.cos(t)*r,.05+Math.sin(t)*r];});
   return [{pts,closed:true,fill:.12},{pts:swirl}];},
  wave:()=>[1,.68,.36].map(r=>({pts:ring(r,10,Math.PI,Math.PI*2).map(([x,y])=>[x,y+.45])})),
  enso:()=>[{pts:ring(.9,16,-.4,Math.PI*1.82),width:2.6}],
  dots:()=>[[-.5,.2,.14],[.1,-.3,.1],[.5,.35,.17]].map(([x,y,r])=>({pts:move(ring(r,6),x,y),closed:true,fill:.55})),
  cat:()=>[{pts:[[-.8,.12],[-.86,-.48],[-.72,-1],[-.36,-.62],[0,-.68],[.36,-.62],[.72,-1],[.86,-.48],[.8,.12],[.6,.55],[0,.74],[-.6,.55]],closed:true,fill:.1},
   {pts:[[-.44,-.06],[-.31,-.19],[-.18,-.06]]},{pts:[[.18,-.06],[.31,-.19],[.44,-.06]]},{pts:[[-.13,.2],[-.06,.3],[0,.2],[.06,.3],[.13,.2]]},
   {pts:[[.4,.12],[1.08,.02]]},{pts:[[.4,.24],[1.06,.32]]},{pts:[[-.4,.12],[-1.08,.02]]},{pts:[[-.4,.24],[-1.06,.32]]}],
  onigiri:()=>[{pts:[[0,-.95],[.36,-.5],[.82,.36],[.7,.72],[0,.8],[-.7,.72],[-.82,.36],[-.36,-.5]],closed:true,fill:.08},{pts:[[-.32,.28],[.32,.28],[.32,.8],[-.32,.8]],closed:true,fill:.55}],
  teacup:()=>[{pts:[[-.62,-.2],[-.57,.46],[-.36,.76],[.36,.76],[.57,.46],[.62,-.2]]},{pts:[[-.62,-.2],[0,-.1],[.62,-.2],[0,-.3]],closed:true,fill:.2},
   {pts:[[-.2,-.42],[-.32,-.62],[-.14,-.82],[-.26,-1.02]]},{pts:[[.16,-.4],[.04,-.6],[.22,-.8],[.1,-1]]}],
  leaf:()=>[{pts:[[0,-1],[.46,-.55],[.5,0],[.26,.55],[0,.8],[-.26,.55],[-.5,0],[-.46,-.55]],closed:true,fill:.16},{pts:[[0,-.8],[0,1.02]]},{pts:[[0,-.2],[.28,-.45]]},{pts:[[0,.15],[-.28,-.08]]}],
  maple:()=>{const pts=[];for(let k=0;k<5;k++){const a=-Math.PI/2+k*Math.PI*2/5;for(const [da,r] of [[-.62,.4],[-.3,.66],[0,1],[.3,.66]])pts.push([Math.cos(a+da*.55)*r,Math.sin(a+da*.55)*r]);}
   return [{pts,closed:true,fill:.2},{pts:[[0,.3],[.08,1.1]]}];},
  moon:()=>{const outer=ring(.95,12,Math.PI*.35,Math.PI*1.65),inner=ring(.72,10,Math.PI*1.55,Math.PI*.45).map(([x,y])=>[x-.38,y]);return [{pts:[...outer,...inner],closed:true,fill:.22}];},
  lantern:()=>[{pts:ring(.62,14).map(([x,y])=>[x*.9,y*1.25]),closed:true,fill:.2},{pts:[[-.52,-.4],[0,-.36],[.52,-.4]]},{pts:[[-.56,0],[0,.05],[.56,0]]},{pts:[[-.52,.4],[0,.44],[.52,.4]]},
   {pts:[[-.3,-.86],[.3,-.86]]},{pts:[[-.3,.86],[.3,.86]]},{pts:[[0,-.86],[0,-1.2]]}],
  fish:()=>[{pts:[[-.9,0],[-.4,-.42],[.3,-.36],[.72,0],[.3,.36],[-.4,.42]],closed:true,fill:.14},{pts:[[.68,0],[1.05,-.38],[.98,0],[1.05,.38]],closed:true,fill:.3},{pts:move(ring(.07,6),-.5,-.08),closed:true,fill:.8}],
  bubble:()=>[{pts:ring(.8,14),closed:true,fill:.06},{pts:ring(.45,6,Math.PI*1.1,Math.PI*1.45)}],
  shell:()=>{const fan=[];for(let i=0;i<=6;i++){const a=Math.PI*(1.1+.8*i/6);fan.push({pts:[[0,.7],[Math.cos(a)*.95,Math.sin(a)*.95+.2]]});}return [{pts:ring(.95,10,Math.PI*1.08,Math.PI*1.92).map(([x,y])=>[x,y+.2]).concat([[.35,.7],[0,.8],[-.35,.7]]),closed:true,fill:.14},...fan];},
  planet:()=>[{pts:ring(.55,12),closed:true,fill:.18},{pts:rot(ring(1,16).map(([x,y])=>[x,y*.28]),-.35)}],
  kana:null
 };
 const KANA='あいうえおかきくけこさしすせそたちつてとなにぬねのはひふへほまみむめもやゆよらりるれろわをんアイウエオカキクケコサシスセソ';
 let lastDoodle='';
 function drawDoodles(p){
  const host=document.getElementById('doodles');if(!host)return;
  const count=DENSITY[theme.density];
  const signature=[theme.preset,count,p.paper,p.doodles?.join()].join('|');
  if(signature===lastDoodle)return;lastDoodle=signature;
  if(!count){host.replaceChildren();return;}
  const W=1180,H=860,r=rng([...theme.preset].reduce((a,c)=>a*31+c.charCodeAt(0),7)),placed=[];
  const colors=p.doodles||[p.accent,p.accent2,p.accent3];
  let body='';
  for(let tries=0;placed.length<count&&tries<count*40;tries++){
   const x=40+r()*(W-80),y=40+r()*(H-80),size=16+r()*22;
   if(placed.some(q=>Math.hypot(q[0]-x,q[1]-y)<(q[2]+size)*1.9))continue;
   placed.push([x,y,size]);
   const name=p.motifs[Math.floor(r()*p.motifs.length)],color=colors[Math.floor(r()*colors.length)],angle=(r()-.5)*50;
   if(name==='kana'){
    const ch=KANA[Math.floor(r()*KANA.length)];
    body+=`<text x="${f(x)}" y="${f(y)}" transform="rotate(${f(angle*.6)} ${f(x)} ${f(y)})" font-size="${f(size*1.5)}" fill="${color}" fill-opacity=".55" font-family='"UD Digi Kyokasho N-R","Yu Mincho","Klee One",serif' text-anchor="middle" dominant-baseline="central">${ch}</text>`;
    continue;
   }
   const strokes=MOTIFS[name]?.()||MOTIFS.star();
   let g='';
   for(const s of strokes){
    let pts=s.at?move(s.pts,s.at[0],s.at[1]):s.pts;
    // Two slightly different passes give the wobbly, pencil-drawn line.
    for(let pass=0;pass<2;pass++){
     const jitter=pass?.07:.035;
     const wobbled=pts.map(([px,py])=>[(px+(r()-.5)*jitter)*size,(py+(r()-.5)*jitter)*size]);
     const fill=!pass&&s.fill?` fill="${color}" fill-opacity="${s.fill}"`:' fill="none"';
     g+=`<path d="${smooth(wobbled,!!s.closed)}"${fill} stroke-width="${pass?1:(s.width||1.7)}" stroke-opacity="${pass?.45:.9}"/>`;
    }
   }
   body+=`<g transform="translate(${f(x)} ${f(y)}) rotate(${f(angle)})" stroke="${color}" stroke-linecap="round" stroke-linejoin="round">${g}</g>`;
  }
  host.innerHTML=`<svg xmlns="http://www.w3.org/2000/svg" width="100%" height="100%"><defs><pattern id="doodle-tile" patternUnits="userSpaceOnUse" width="${W}" height="${H}">${body}</pattern></defs><rect width="100%" height="100%" fill="url(#doodle-tile)"/></svg>`;
 }
 let lastFall='';
 function drawFalling(p){
  const host=document.getElementById('falling');if(!host)return;
  const kind=p.fall||'',signature=theme.preset+kind+(p.doodles||[]).join();
  if(signature===lastFall)return;lastFall=signature;host.replaceChildren();
  if(!kind||!MOTIFS[kind])return;
  const r=rng(99),colors=p.doodles||[p.accent];
  for(let i=0;i<9;i++){
   const size=10+r()*10,color=colors[i%colors.length];
   const strokes=MOTIFS[kind]();
   const paths=strokes.map(s=>`<path d="${smooth(poly(s.at?move(s.pts,...s.at):s.pts,size),!!s.closed)}" fill="${s.fill?color:'none'}" fill-opacity="${s.fill?Math.min(.7,s.fill*2.2):0}" stroke="${color}" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/>`).join('');
   const el=document.createElement('span');
   el.innerHTML=`<svg viewBox="${-size*1.3} ${-size*1.3} ${size*2.6} ${size*2.6}" width="${size*2.6}" height="${size*2.6}">${paths}</svg>`;
   el.style.setProperty('--x',(r()*100).toFixed(1)+'vw');
   el.style.setProperty('--drift',((r()-.5)*24).toFixed(1)+'vw');
   el.style.setProperty('--dur',(16+r()*16).toFixed(1)+'s');
   el.style.setProperty('--delay',(-r()*30).toFixed(1)+'s');
   el.style.setProperty('--spin',((r()>.5?1:-1)*(180+r()*360)).toFixed(0)+'deg');
   el.className=kind==='bubble'?'rise':'fall';
   host.append(el);
  }
 }

 // ---------------------------------------------------------------- drawer UI
 const $=id=>document.getElementById(id);
 const make=(tag,cls,text)=>{const e=document.createElement(tag);if(cls)e.className=cls;if(text!==undefined)e.textContent=text;return e;};
 function say(text){const s=$('theme-save');if(s){s.textContent=text;clearTimeout(say.t);say.t=setTimeout(()=>{s.textContent='';},2200);}}
 function segmented(host,options,get,set){
  host.replaceChildren();
  for(const [value,label] of options){
   const b=make('button','seg',label);b.type='button';b.dataset.value=value;
   b.onclick=()=>{set(value);apply();};host.append(b);
  }
  host.sync=()=>{for(const b of host.children)b.setAttribute('aria-pressed',String(b.dataset.value===String(get())));};
 }
 const sliders=[];
 function slider(host,key,label,step,unit=''){
  const wrap=make('label','slider'),top=make('span','slider-top'),name=make('span','',label),value=make('output'),input=make('input');
  input.type='range';[input.min,input.max]=LIMITS[key];input.step=step;input.setAttribute('aria-label',label);
  input.oninput=()=>{theme[key]=clamp(key,Number(input.value));value.textContent=theme[key]+unit;apply();};
  top.append(name,value);wrap.append(top,input);host.append(wrap);
  sliders.push(()=>{input.value=theme[key];value.textContent=theme[key]+unit;});
 }
 function preview(key){
  const p=PRESETS[key],b=make('button','preset-card');b.type='button';b.dataset.preset=key;
  b.style.setProperty('--pv-paper',p.paper);b.style.setProperty('--pv-card',p.card);b.style.setProperty('--pv-ink',p.ink);b.style.setProperty('--pv-accent',p.accent);b.style.setProperty('--pv-accent2',p.accent2);
  const art=make('span','preset-art');
  const strokes=(MOTIFS[p.motifs[0]]||MOTIFS.star)();
  art.innerHTML=`<svg viewBox="-30 -30 60 60" aria-hidden="true"><g stroke="${p.doodles[0]}" stroke-linecap="round" stroke-linejoin="round">${strokes.map(s=>`<path d="${smooth(poly(s.at?move(s.pts,...s.at):s.pts,22),!!s.closed)}" fill="${s.fill?p.doodles[0]:'none'}" fill-opacity="${s.fill||0}" stroke-width="1.8"/>`).join('')}</g></svg><i></i><i></i>`;
  const names=make('span','preset-name');names.append(make('b','',p.zh),make('small','',p.en));
  b.append(art,names);
  b.onclick=()=>{theme.preset=key;theme.custom={};apply();};
  return b;
 }
 let pickers={};
 function build(){
  const presets=$('theme-presets');if(!presets)return;
  presets.replaceChildren(...ORDER.map(preview));
  segmented($('theme-density'),[['none','無'],['calm','少少'],['normal','適中'],['lively','熱鬧']],()=>theme.density,v=>theme.density=v);
  segmented($('theme-font'),Object.entries(FONTS).map(([k,v])=>[k,v.zh]),()=>theme.font,v=>theme.font=v);
  for(const [id,key] of [['theme-grain','grain'],['theme-falling','falling']]){const box=$(id);box.onchange=()=>{theme[key]=box.checked;apply();};}
  const sizes=$('theme-sizes');sizes.replaceChildren();sliders.length=0;
  slider(sizes,'jp','日文字級 · Japanese size',1,'px');slider(sizes,'translation','翻譯字級 · Translation size',1,'px');
  slider(sizes,'spacing','行距 · Line spacing',.05);slider(sizes,'width','版面寬度 · Page width',10,'px');slider(sizes,'radius','圓角 · Roundness',1,'px');
  const colors=$('theme-colors');colors.replaceChildren();pickers={};
  for(const [key,label] of [['paper','背景紙 · Paper'],['card','卡片 · Cards'],['accent','重點色 · Accent']]){
   const wrap=make('label','color-chip'),input=make('input'),text=make('span','',label);input.type='color';
   input.oninput=()=>{theme.custom[key]=input.value.toLowerCase();apply();};
   wrap.append(input,text);colors.append(wrap);pickers[key]=input;
  }
  $('theme-reset').onclick=()=>{theme={...DEFAULTS,custom:{}};apply();say('已恢復預設外觀');};
  $('theme-custom-reset').onclick=()=>{theme.custom={};apply();};
 }
 function syncControls(){
  if(!$('theme-presets'))return;
  for(const b of $('theme-presets').children)b.setAttribute('aria-pressed',String(b.dataset.preset===theme.preset));
  $('theme-density').sync?.();$('theme-font').sync?.();
  $('theme-grain').checked=theme.grain;$('theme-falling').checked=theme.falling;
  for(const s of sliders)s();
  const p=current||palette();for(const [k,input] of Object.entries(pickers))input.value=p[k];
  $('theme-custom-reset').hidden=!Object.keys(theme.custom).length;
  const chip=$('theme-open');if(chip)chip.title='主題：'+PRESETS[theme.preset].zh+' · '+PRESETS[theme.preset].en;
 }
 function drawer(){
  const panel=$('theme-drawer'),open=$('theme-open'),close=$('theme-close'),scrim=$('theme-scrim');
  if(!panel)return;
  const set=show=>{panel.classList.toggle('open',show);scrim.hidden=!show;panel.setAttribute('aria-hidden',String(!show));open?.setAttribute('aria-expanded',String(show));if(show)panel.querySelector('button')?.focus({preventScroll:true});};
  open?.addEventListener('click',()=>set(!panel.classList.contains('open')));
  close?.addEventListener('click',()=>set(false));scrim?.addEventListener('click',()=>set(false));
  document.addEventListener('keydown',e=>{if(e.key==='Escape'&&panel.classList.contains('open'))set(false);});
  window.readerTheme.openDrawer=()=>set(true);
 }

 load();
 // Paint colours immediately (before layout scripts) to avoid a flash of the wrong palette.
 apply(false);
 const ready=()=>{build();drawer();apply(false);};
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',ready);else ready();
})();

// Small hand-drawn icon set shared by the page scripts (stroke = currentColor).
(() => {
 const P={
  refresh:'M19.5 8.2c-1.3-2.9-4.2-4.7-7.4-4.6C7.6 3.8 4.2 7.4 4.3 11.9c.1 4.4 3.7 7.9 8 7.8 3-.1 5.6-1.9 6.8-4.5M19.8 3.6l-.2 4.8-4.7-.4',
  screen:'M3.8 5.2c5.4-.4 10.9-.3 16.4.1.3 3.9.3 7.8-.1 11.7-5.4.3-10.9.3-16.3-.1-.3-3.9-.3-7.8 0-11.7ZM8.5 20.3c2.4-.2 4.7-.2 7.1 0M7 9.2V7.8h1.6M17 9.2V7.8h-1.6M7 13.4v1.4h1.6M17 13.4v1.4h-1.6',
  stop:'M6.2 5.8c3.9-.3 7.8-.2 11.7.1.3 4 .2 8-.1 12-3.9.3-7.8.3-11.7-.1-.2-4-.2-8 .1-12Z',
  play:'M7.6 4.9c3.9 2.1 7.6 4.5 11 7.2-3.5 2.6-7.2 4.9-11.1 7-.3-4.7-.3-9.5.1-14.2Z',
  x:'M6.3 6.1c3.9 3.8 7.7 7.9 11.4 12M17.8 6.3c-3.9 3.7-7.7 7.6-11.5 11.6',
  speaker:'M4.3 9.3c1.3-.1 2.6-.1 3.9 0l4.6-3.7c.3 4.3.3 8.6 0 12.9L8.2 14.8c-1.3.1-2.6.1-3.9 0-.2-1.8-.2-3.7 0-5.5ZM15.8 9.1c1.2 1.8 1.2 4 0 5.8M18.4 6.6c2.4 3.4 2.4 7.4 0 10.8',
  help:'M12 20.3c4.7.1 8.4-3.6 8.3-8.4-.1-4.6-3.9-8.3-8.5-8.2-4.5.2-8.1 4-8 8.5.1 4.5 3.7 8.1 8.2 8.1ZM9.6 9.6c.3-1.5 1.5-2.4 2.9-2.3 1.5.1 2.5 1.2 2.4 2.5-.1 1.6-2.7 2-2.8 3.9M12.1 16.6v.2',
  list:'M8.8 6.7c3.8-.2 7.6-.2 11.4.1M8.9 12.1c3.7-.1 7.4-.1 11.2.1M8.8 17.5c3.8-.2 7.5-.1 11.3.1M4.4 6.6h.9M4.4 12h.9M4.4 17.4h.9',
  search:'M10.6 17.3c3.7.1 6.6-2.8 6.6-6.5 0-3.6-2.9-6.5-6.5-6.5C7 4.4 4.1 7.3 4.2 11c.1 3.5 2.9 6.3 6.4 6.3ZM15.6 15.8c1.5 1.4 2.9 2.9 4.3 4.5',
  paste:'M8.4 5.2c-1.5 0-3 0-4.4.1-.2 5-.2 10 .1 15 4.4.2 8.9.2 13.3 0 .2-5 .2-10 0-15-1.4-.1-2.9-.1-4.3-.1M8.6 3.8c2.2-.1 4.5-.1 6.7 0 .1.9.1 1.9 0 2.8-2.2.1-4.5.1-6.7 0-.1-.9-.1-1.9 0-2.8ZM8 11.4c2.8-.1 5.6-.1 8.4.1M8 15.3c2-.1 4-.1 6 0',
  left:'M19.4 12.2c-4.8-.2-9.6-.1-14.4.1M10.3 6.4c-1.9 1.9-3.7 3.8-5.4 5.8 1.7 2 3.5 3.9 5.4 5.7',
  right:'M4.6 12.2c4.8-.2 9.6-.1 14.4.1M13.7 6.4c1.9 1.9 3.7 3.8 5.4 5.8-1.7 2-3.5 3.9-5.4 5.7',
  palette:'M12.2 3.9c-4.8-.2-8.7 3.5-8.6 8.2.1 4.4 3.6 8 8 8 1.6 0 2.1-1.2 1.3-2.4-.9-1.3 0-2.8 1.6-2.8h2.2c2.3 0 3.6-1.5 3.5-3.6-.3-4-3.7-7.2-8-7.4ZM7.8 11.6h.2M10.4 7.8h.2M14.6 8h.2',
  keyboard:'M3.6 7.1c5.6-.3 11.2-.3 16.8 0 .3 3.3.3 6.6-.1 9.9-5.5.3-11.1.3-16.6 0-.3-3.3-.3-6.6-.1-9.9ZM7 10.4h.3M10.3 10.4h.3M13.6 10.4h.3M16.9 10.4h.3M7.8 13.8c2.8-.1 5.6-.1 8.4 0',
  gamepad:'M7.4 7.6c3.1-.4 6.1-.4 9.2 0 2.6.3 4 4.7 3.9 7.8-.1 2.4-2.2 2.9-3.6 1.4-1.1-1.2-2-1.9-4.9-1.9s-3.8.7-4.9 1.9c-1.4 1.5-3.5 1-3.6-1.4-.1-3.1 1.3-7.5 3.9-7.8ZM7.5 10.2v3.2M5.9 11.8h3.2M15.9 10.6h.2M17.5 12.4h.2',
  globe:'M12 20.3c4.6.1 8.3-3.6 8.3-8.3 0-4.6-3.7-8.3-8.3-8.3S3.7 7.5 3.7 12.1c0 4.5 3.7 8.2 8.3 8.2ZM3.9 11.8c5.4.3 10.8.3 16.3 0M12 3.8c-2.6 2.5-3.7 5.4-3.6 8.4.1 3 1.3 5.8 3.6 8.1 2.3-2.3 3.5-5.2 3.6-8.2 0-3-1.1-5.8-3.6-8.3',
  book:'M12 6.3c-2.4-1.5-5.2-2-8.2-1.7-.2 4.5-.1 9 .1 13.4 3-.3 5.7.2 8.1 1.8 2.4-1.6 5.1-2.1 8.1-1.8.2-4.4.3-8.9.1-13.4-3-.3-5.8.2-8.2 1.7ZM12 6.4c-.2 4.4-.2 8.9 0 13.3',
  save:'M4.4 4.6c4.2-.2 8.4-.2 12.6 0l2.7 2.7c.2 4.2.2 8.4 0 12.5-5.1.2-10.2.2-15.3 0-.2-5.1-.2-10.2 0-15.2ZM8 4.8c-.1 1.4-.1 2.8 0 4.2 2.4.1 4.8.1 7.2 0 .1-1.4.1-2.8 0-4.2M7.4 19.6c-.1-2.2-.1-4.3 0-6.5 3-.1 6.1-.1 9.2 0 .1 2.2.1 4.3 0 6.5',
  crop:'M6.6 3.4c-.2 5.7-.2 11.4.1 17M3.4 7.2c5.8-.2 11.6-.2 13.5.1.2 5.6.2 11.3 0 13.4M17.2 16.9c1.2 0 2.3 0 3.4.1',
  basket:'M3.8 9.8c5.5-.3 11-.3 16.4 0-.6 3.5-1.3 6.9-2.3 10.3-3.9.2-7.9.2-11.8 0-1-3.4-1.7-6.8-2.3-10.3ZM7.6 9.7c.9-2.3 2-4.2 3.1-5.8M16.4 9.7c-.9-2.3-2-4.2-3.1-5.8M9.2 13.2c.2 1.9.4 3.6.7 5M14.8 13.2c-.2 1.9-.4 3.6-.7 5',
  note:'M5.2 3.9c4.6-.2 9.1-.2 13.6 0 .2 4.4.2 8.8 0 13.2l-3.6 3.3c-3.3.1-6.7.1-10 0-.2-5.5-.2-11 0-16.5ZM15 20.2c-.1-1.2-.1-2.4 0-3.6 1.3-.1 2.5-.1 3.8 0M8.4 8.6c2.4-.1 4.8-.1 7.2 0M8.4 12.1c2.4-.1 4.8-.1 7.2 0',
  spark:'M12 3.4c.8 3.8 2.6 6.4 6.8 8.4-4.2 1.9-6 4.6-6.8 8.6-.9-4-2.6-6.7-6.8-8.6 4.2-2 6-4.6 6.8-8.4Z',
  check:'M4.8 12.6c1.8 1.6 3.4 3.3 4.9 5.2 3-4.6 6.3-8.8 9.8-12.6',
  pencil:'M4.5 19.6c.3-1.7.7-3.3 1.2-4.9L15.9 4.5c1.2-.1 2.4 1 3.5 2.3.1.7-.2 1.2-.6 1.6L8.8 18.5c-1.5.5-2.9.8-4.3 1.1ZM14.2 6.3c1.3.9 2.4 2.1 3.4 3.4'
 };
 window.readerIcons=P;
 window.readerIcon=(name,cls='ico')=>`<svg class="${cls}" viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="${P[name]||P.spark}"/></svg>`;
})();
