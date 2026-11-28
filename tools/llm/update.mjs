import {readFile,writeFile,mkdir} from 'node:fs/promises';
import {join,resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
import {identify,samePlaceholders,placeholders} from '../../src/core.mjs';
import {loadCatalog,mergeRecords,saveParts} from '../records.mjs';
import {buildMemory} from './memory.mjs';
const read=async p=>JSON.parse(await readFile(p,'utf8'));
const write=async(p,v)=>writeFile(p,JSON.stringify(v,null,2)+'\n',{mode:0o600});
export async function plan(game,wiki,entries,decisions={}){
 if(!game.build||game.build!==wiki.build)throw Error('SOURCE_BUILD_MISMATCH');
 const memory=buildMemory(entries,decisions),seen=new Map(),rows=[],pending=[],reused=[],deferred=[];
 for(const row of [...game.rows,...wiki.rows]){
  const r=await identify(row);
  if(row.id!==r.id||row.sourceHash!==r.sourceHash)throw Error('SOURCE_ID_MISMATCH');
  if(seen.has(r.id)){
   if(seen.get(r.id)!==r.sourceHash)throw Error('SOURCE_CONFLICT');
   continue;
  }
  seen.set(r.id,r.sourceHash);
  if(entries[r.id]?.sourceHash===r.sourceHash)continue;
  const source=r.en??r.key;
  if(typeof source!=='string'||!source.trim())throw Error('EMPTY_SOURCE');
  const id=String(rows.length+1);
  rows.push({id,record:{kind:r.kind,key:r.key,en:r.en,sourceHash:r.sourceHash,id:r.id}});
  const exact=memory.lookup(source);
  if(exact!==null&&samePlaceholders(source,exact)){
   reused.push({id,ko:exact,status:'APPROVED_MEMORY'});
  }else if(source==='1M'){
   deferred.push({id,status:'NUMERIC_SHORTHAND'});
  }else if(source.length>1200||/[\r\n]/.test(source)||pending.length>=200){
   deferred.push({id,status:'REVIEW_REQUIRED'});
  }else{
   const context=r.kind==='wiki'?'wiki visible text':r.kind==='news'?'game patch notes':r.kind==='name'?'game item, monster or skill name':'game/talent language table';
   pending.push({id,source,context,terms:memory.terms(source)});
  }
 }
 return {build:game.build,rows,pending,reused,deferred};
}
export async function assemble(plan,verified){
 const expected=new Set(plan.pending.map(r=>r.id));
 if(verified.length!==expected.size||new Set(verified.map(r=>r.id)).size!==verified.length||verified.some(r=>!expected.has(r.id)||!['MODEL_VERIFIED','REVIEW_REQUIRED'].includes(r.status)))throw Error('INCOMPLETE_MODEL_RESULTS');
 const all=[...plan.reused,...verified,...plan.deferred];
 if(all.length!==plan.rows.length||new Set(all.map(r=>r.id)).size!==all.length)throw Error('ROUTING_INCOMPLETE');
 const byId=new Map(plan.rows.map(r=>[r.id,r.record])),approved=[],unresolved=[];
 for(const result of all){
  const r=byId.get(result.id);
  if(!r)throw Error('UNKNOWN_RESULT');
  if(['APPROVED_MEMORY','MODEL_VERIFIED'].includes(result.status)){
   if(typeof result.ko!=='string'||!result.ko.trim()||!samePlaceholders(r.en??r.key,result.ko))throw Error('INVALID_CANDIDATE');
   approved.push({...r,ko:result.ko,approved:true,origin:result.status});
  }else unresolved.push({id:r.id,sourceHash:r.sourceHash,reason:result.status});
 }
 return {build:plan.build,rows:approved,unresolved};
}
async function apply(work){
 const catalog=await loadCatalog(),{base,extra}=catalog;
 const prev=await read('translations/catalog.json');
 const approved=[];
 for(const row of work.rows){
  const r=await identify(row);
  if(r.id!==row.id||r.sourceHash!==row.sourceHash||row.approved!==true||!samePlaceholders(r.en??r.key,r.ko))throw Error('INVALID_APPROVED_ROW');
  const existing=base.entries[r.id]??extra.entries[r.id];
  if(existing?.sourceHash===r.sourceHash)continue;
  const record={...existing,sourceHash:r.sourceHash,ko:r.ko,placeholders:placeholders(r.en??r.key)};
  if(r.kind==='wiki')record.scope='wiki';
  const target=Object.hasOwn(base.entries,r.id)?base:extra;
  target.entries[r.id]=record;
  if(Object.hasOwn(base.entries,r.id)&&Object.hasOwn(extra.entries,r.id))extra.entries[r.id]=record;
  approved.push(r);
 }
 if(!approved.length)return 0;
 const version=/^(\d+)\.(\d+)\.(\d+)$/.exec(extra.version);
 if(!version)throw Error('INVALID_VERSION');
 extra.version=version[1]+'.'+version[2]+'.'+(Number(version[3])+1);
 extra.gameBuild=work.build;
 await saveParts(base,extra,approved);
 const next=await read('translations/catalog.json');
 await writeFile('translations/catalog.json',JSON.stringify({...prev,...next},null,2)+'\n');
 await loadCatalog();
 return approved.length;
}
async function main(){
 const [mode,dir,llmdir]=process.argv.slice(2);
 if(mode==='plan'){
  const catalog=await loadCatalog(),entries=mergeRecords(catalog.base,catalog.extra).entries;
  const p=await plan(await read(join(dir,'game.json')),await read(join(dir,'wiki.json')),entries,catalog.decisions);
  await mkdir(llmdir,{recursive:true,mode:0o700});
  await write(join(dir,'plan.json'),p);
  await write(join(llmdir,'pending.json'),p.pending);
  console.log('LLM_PLAN '+JSON.stringify({build:p.build,missing:p.rows.length,reused:p.reused.length,pending:p.pending.length,deferred:p.deferred.length}));
 }else if(mode==='apply'){
  const p=await read(join(dir,'plan.json'));
  const verified=p.pending.length?await read(join(llmdir,'verified.json')):[];
  const work=await assemble(p,verified);
  const count=await apply(work);
  await write(join(dir,'summary.json'),{build:p.build,candidates:count,memory:p.reused.length,model:work.rows.filter(r=>r.origin==='MODEL_VERIFIED').length,unresolved:work.unresolved});
  console.log('LLM_UPDATE_CANDIDATES='+count+' UNRESOLVED='+work.unresolved.length);
 }else throw Error('UPDATE_MODE');
}
if(process.argv[1]&&import.meta.url===pathToFileURL(resolve(process.argv[1])).href)await main();
