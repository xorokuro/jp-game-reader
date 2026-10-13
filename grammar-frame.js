// Added to your lesson pages while the reader serves them (文法 tab). The lesson files are unchanged.
// Inside the reader: let the 文法 tab apply the palette before the page paints.
// Opened on its own: offer to open the page in the reader, where selecting a word looks it up.
(() => {
 let host=null;
 try{if(window.parent!==window&&window.parent.readerGrammar)host=window.parent.readerGrammar;}catch{}
 if(host){try{host.prepare(document);}catch{}return;}
 if(window.parent!==window)return;
 const offer=()=>{
  const link=document.createElement('a');link.className='reader-open-in';
  link.href='/#grammar='+encodeURIComponent(location.pathname+location.search+location.hash);
  link.textContent='在閱讀器中開啟 · 選字查辭典';link.title='Open in the reader (dictionary lookup)';
  document.body.append(link);
 };
 if(document.body)offer();else document.addEventListener('DOMContentLoaded',offer);
})();
