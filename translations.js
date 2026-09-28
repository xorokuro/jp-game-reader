(function(root){
function parseTranslations(raw){
 const blocks=[...raw.matchAll(/```(?:json)?\s*([\s\S]*?)```/gi)].map(m=>m[1]);
 const candidate=blocks.length?blocks[blocks.length-1]:raw.trim();
 const value=JSON.parse(candidate),items=Array.isArray(value)?value:[value],seen=new Set();
 for(const r of items){
  if(!r||!Number.isSafeInteger(r.id)||r.id<1)throw Error('Each translation needs a numeric journal id.');
  if(seen.has(r.id))throw Error('Duplicate journal id: '+r.id);seen.add(r.id);
  for(const field of ['english','traditional_chinese'])if(typeof r[field]!=='string'||!r[field].trim())throw Error('Both English and Traditional Chinese translations are required for #'+r.id);
 }
 if(!items.length)throw Error('No translations found.');return items;
}
if(typeof module!=='undefined')module.exports={parseTranslations};else root.parseTranslations=parseTranslations;
})(typeof window!=='undefined'?window:globalThis);
