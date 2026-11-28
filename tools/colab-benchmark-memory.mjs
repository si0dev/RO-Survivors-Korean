import {createHash} from 'node:crypto';
import {readFile,writeFile} from 'node:fs/promises';
import {resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
const hash=s=>createHash('sha256').update(s,'utf8').digest('hex');
const escape=s=>s.replace(/[.*+?^$\x7b\x7d()|[\]\\]/g,'\\$&');
// Candidate vocabulary only. Korean values always come from matching approved hashes.
// Longest match wins (e.g. Ore Discovery is not the stat Discovery).
export const candidates=[
 'Ore Discovery','Hindsight','Affixes','Haste','Flee','Discovery','Sword Dance','Sand Attack','Spear Quicken','Peco Peco','Peco','Unhealed Wound','Caltrops','Caltrop','Mage','Wizard','Deity','Talent','Talents','Epic','Legendary','Crit','Critical','Critical Hit','Area','Pierce','Shadow','Undead','Freeze','Frozen','Sleep','Stun','Damage','Healing','Cast Speed','Cast Time','Cooldown','Zeny','EXP','Armor','Gear','Card','Boss','Job','Skill','Skills','ATK','MATK','HP','SP','STR','AGI','VIT','INT','DEX','LUK'
];
export function buildMemory(entries,decisions={}){
 const exact=new Map(),labels=new Map();
 for(const [id,r] of Object.entries(entries)){
  if(!r||typeof r.ko!=='string'||!r.ko||!r.sourceHash)continue;
  const set=exact.get(r.sourceHash)??new Set();set.add(r.ko);exact.set(r.sourceHash,set);
  // Only short approved labels, never descriptions or placeholder templates.
  if((decisions[id]?.type==='fixed'||r.ko.length<=24)&&!r.placeholders?.length&&!/[\r\n]/.test(r.ko)&&r.ko.length<=24){
   const l=labels.get(r.sourceHash)??new Set();l.add(r.ko);labels.set(r.sourceHash,l);
  }
 }
 const unique=(m,k)=>m.get(k)?.size===1?[...m.get(k)][0]:null;
 function lookup(source){return unique(exact,hash(source));}
 function terms(source){
  const result={},ranges=[];
  for(const term of [...candidates].sort((a,b)=>b.length-a.length)){
   const pattern=new RegExp('(?<![A-Za-z0-9_])'+escape(term)+'(?![A-Za-z0-9_])','gi');
   for(const match of source.matchAll(pattern)){
    const start=match.index,end=start+match[0].length;
    if(ranges.some(([a,b])=>start<b&&end>a))continue;
    // Reserve longer recognized phrases even if no unique approved translation exists.
    ranges.push([start,end]);
    const values=new Set([term,match[0],term.toLowerCase(),term.toUpperCase()].flatMap(form=>{
     const h=hash(form),label=unique(labels,h);
     return label&&unique(exact,h)===label?[label]:[];
    }));
    if(values.size===1)result[match[0]]=[...values][0];
   }
  }
  return result;
 }
 return {lookup,terms};
}
async function main(){
 const [root,snapshotPath,outPath]=process.argv.slice(2);
 const {loadCatalog,mergeRecords}=await import(pathToFileURL(resolve(root,'tools/records.mjs')));
 const catalog=await loadCatalog(resolve(root,'translations'));
 const memory=buildMemory(mergeRecords(catalog.base,catalog.extra).entries,catalog.decisions);
 const snapshot=JSON.parse(await readFile(snapshotPath,'utf8'));
 const failed=snapshot.rows.filter(r=>!r.excluded&&(r.verdict!=='ACCEPT'||!Object.values(r.final_checks).every(Boolean)));
 if(failed.length!==28)throw Error('MEMORY_RETRY_COUNT');
 const rows=failed.map(r=>({id:r.id,source:r.source,terms:memory.terms(r.source),exact:memory.lookup(r.source)}));
 await writeFile(outPath,JSON.stringify(rows),{mode:0o600});
 console.log('CHAIN_MEMORY_EXACT_HITS='+rows.filter(r=>r.exact!==null).length+'/28');
 console.log('CHAIN_MEMORY_TERM_ROWS='+rows.filter(r=>Object.keys(r.terms).length).length+'/28');
}
if(process.argv[1]&&import.meta.url===pathToFileURL(resolve(process.argv[1])).href)await main();
