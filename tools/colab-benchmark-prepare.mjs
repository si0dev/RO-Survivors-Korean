import {readFile,writeFile} from 'node:fs/promises';
import {resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
const root=resolve(process.argv[2]),temp=resolve(process.argv[3]);
const {identify,sha256}=await import(pathToFileURL(root+'/src/core.mjs'));
const {findPageBundle,sourceSnapshot}=await import(pathToFileURL(root+'/src/browser.mjs'));
const pack=JSON.parse(await readFile(root+'/dist/ko.json','utf8'));
const wiki=JSON.parse(await readFile(temp+'/wiki.json','utf8'));
const origin='https://ro-survivors.com/';
async function get(url){
 const r=await fetch(url,{cache:'no-store',signal:AbortSignal.timeout(30000)});
 if(!r.ok||new URL(r.url).origin!==new URL(origin).origin)throw Error('HTTP '+r.status);
 return r.text();
}
const snapshots=[];
for(const [kind,page] of [['main',origin],['talents',origin+'talents.html']]){
 const html=await get(page),urls=[...html.matchAll(/(?:src|href)\s*=\s*["']([^"']+)["']/gi)].map(m=>m[1]);
 const url=findPageBundle(urls,page);if(!url)throw Error('Bundle missing: '+kind);
 const content=await get(url),build=content.match(/RO Survivors[^*\n]*?Build\s+([0-9a-f]{7,64})\b/i)?.[1];
 if(!build||build!==wiki.build)throw Error('Game build changed during extraction');
 const snap=await sourceSnapshot({kind,url,content,build},get);
 if(kind==='main'&&snap.newsScanFailed)throw Error('News extraction failed');
 snapshots.push(snap);
}
const groups=Object.fromEntries(['ui','skill','gear','job','wiki','news'].map(k=>[k,new Map()]));
const eligible=(en,ko)=>typeof en==='string'&&/[A-Za-z]/.test(en)&&typeof ko==='string'&&/[가-힣]/.test(ko)&&en.trim().length>=2&&en.length<=1200;
function add(group,id,en,ko,context){
 if(!eligible(en,ko))return;
 const old=groups[group].get(en);
 if(old&&old.reference!==ko){groups[group].set(en,null);return;}
 if(groups[group].has(en)&&!old)return;
 groups[group].set(en,{id,source:en,reference:ko,group,context});
}
for(const [view,texts] of wiki.views){
 const [category]=JSON.parse(view);
 const group=['skills','deity'].includes(category)?'skill':['gear','equip','cards'].includes(category)?'gear':['jobs','progress'].includes(category)?'job':'wiki';
 for(const [position,en] of Object.entries(texts)){
  if(!position.startsWith('wk-detail/'))continue;
  const row=await identify({kind:'wiki',key:en,en});
  const r=pack.entries[row.id];
  if(r?.scope==='wiki'&&r.sourceHash===row.sourceHash)add(group,row.id,en,r.ko,'wiki:'+category);
 }
}
const [game,talents]=snapshots;
const manifest=JSON.parse(await get(origin+'assets/manifest.json?v='+wiki.build));
const gearNames=new Set(Object.values(manifest.items??{}).concat(Object.values(manifest.cards??{})).map(x=>x?.name).filter(Boolean));
for(const row of [...game.rows,...game.newsHistory,...talents.rows]){
 if(row.en===null)continue;
 const identified=await identify(row),r=pack.entries[identified.id];
 if(!r||r.sourceHash!==identified.sourceHash||r.scope==='wiki')continue;
 if(row.kind==='news')add('news',identified.id,row.en,r.ko,'news');
 else if(row.kind==='name'&&gearNames.has(row.en))add('gear',identified.id,row.en,r.ko,'item/card name');
 else if(row.kind==='ui'&&row.en.length<=120)add('ui',identified.id,row.en,r.ko,'game/talent language table');
}
// Reproducible stratified sample: no source appears twice, prefer varying lengths.
const quotas={ui:30,skill:40,gear:40,job:30,wiki:40,news:20};
const used=new Set(),selected=[];
const excluded=new Set(['It can be sorted by score, quality, tier or arrival, and the «Only new» box leaves only what just came in.','Signature: {skill} (on the 1st level-up)','Discovery increases by {value}% for 10 seconds.','Legendary: {item}','Deals 150% ATK damage to nearby enemies and heals {hp} HP.','Gain +5% Discovery for each Legendary item.','Deals 80% MATK damage to nearby enemies every 2 seconds.','Choose a skill on your next level-up.','Increases Discovery by 8%.','Your next level-up grants 2 points.','Deals 120% ATK damage.','Sort by arrival.']);
for(const group of ['skill','gear','job','wiki','news','ui']){
 const rows=[...groups[group].values()].filter(r=>r&&!used.has(r.source)&&!excluded.has(r.source));
 for(const r of rows)r.rank=await sha256('ro-benchmark-v1\0'+r.source);
 rows.sort((a,b)=>a.rank.localeCompare(b.rank));
 const buckets=[rows.filter(r=>r.source.length<=25),rows.filter(r=>r.source.length>25&&r.source.length<=100),rows.filter(r=>r.source.length>100)];
 let n=0;
 while(n<quotas[group]){
  let progress=false;
  for(const bucket of buckets){
   if(n>=quotas[group])break;
   const r=bucket.shift();if(!r)continue;
   if(used.has(r.source))continue;
   used.add(r.source);const {rank,...record}=r;selected.push(record);n++;progress=true;
  }
  if(!progress)throw Error('Insufficient approved '+group+' samples: '+n);
 }
 console.log('BENCHMARK_SAMPLE '+JSON.stringify({group,available:rows.length,selected:n}));
}
if(selected.length!==200||used.size!==200)throw Error('Invalid sample count');
const references=selected.map((r,i)=>({...r,id:String(i+1).padStart(3,'0'),recordId:r.id}));
const baseline=JSON.parse(await readFile(new URL('./colab-benchmark-baseline.json',import.meta.url),'utf8'));
if(wiki.build!==baseline.build||JSON.stringify(references.map(({id,recordId})=>({id,recordId})))!==JSON.stringify(baseline.rows))throw Error('Comparison sample differs from Qwen baseline; refusing to compare');
console.log('BASELINE_MATCH 200/200');
await writeFile(temp+'/references.json',JSON.stringify(references));
await writeFile(temp+'/inputs.json',JSON.stringify(references.map(({id,source,group,context})=>({id,source,group,context}))));
console.log('BENCHMARK_BUILD '+wiki.build);
