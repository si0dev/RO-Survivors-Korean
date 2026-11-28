// One live extraction, full inventory, private transient batch inputs.
import {readFile,writeFile,mkdir,readdir} from 'node:fs/promises';
import {join,resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
import {createHash,createHmac,createCipheriv,createDecipheriv,randomBytes} from 'node:crypto';
import {identify} from '../../src/core.mjs';
import {loadCatalog,mergeRecords} from '../records.mjs';
import {buildMemory} from './memory.mjs';
const read=async p=>JSON.parse(await readFile(p,'utf8'));
const write=async(p,v)=>writeFile(p,JSON.stringify(v)+'\n',{mode:0o600});
const batchSize=200;
const hash=s=>createHash('sha256').update(s).digest('hex');
function key(){
 const secret=process.env.AUDIT_SEAL_SECRET,run=process.env.GITHUB_RUN_ID,repo=process.env.GITHUB_REPOSITORY;
 if(!secret||!run||!repo)throw Error('AUDIT_SEAL_CONFIGURATION');
 return createHmac('sha256',secret).update('ro-live-audit-v1\0'+repo+'\0'+run).digest();
}
export function seal(data,batch,k=key()){
 const nonce=randomBytes(12),cipher=createCipheriv('aes-256-gcm',k,nonce);
 cipher.setAAD(Buffer.from('batch:'+batch));
 return Buffer.concat([nonce,cipher.update(JSON.stringify(data),'utf8'),cipher.final(),cipher.getAuthTag()]);
}
export function unseal(data,batch,k=key()){
 if(data.length<28)throw Error('AUDIT_SEAL_INVALID');
 const decipher=createDecipheriv('aes-256-gcm',k,data.subarray(0,12));
 decipher.setAAD(Buffer.from('batch:'+batch));
 decipher.setAuthTag(data.subarray(-16));
 return JSON.parse(Buffer.concat([decipher.update(data.subarray(12,-16)),decipher.final()]));
}
export async function inventory(game,wiki,entries,decisions={}){
 if(!game.build||game.build!==wiki.build)throw Error('AUDIT_BUILD_MISMATCH');
 const memory=buildMemory(entries,decisions),wikiHashes=new Map(),seen=new Map(),rows=[];
 for(const r of Object.values(entries))if(r.scope==='wiki'){
  const set=wikiHashes.get(r.sourceHash)??new Set();set.add(r.ko);wikiHashes.set(r.sourceHash,set);
 }
 for(const row of [...game.rows,...wiki.rows]){
  const r=await identify(row);
  if(r.id!==row.id||r.sourceHash!==row.sourceHash)throw Error('AUDIT_SOURCE_ID');
  if(seen.has(r.id)){
   if(seen.get(r.id)!==r.sourceHash)throw Error('AUDIT_SOURCE_CONFLICT');
   continue;
  }
  seen.set(r.id,r.sourceHash);
  const source=r.en??r.key;
  if(typeof source!=='string'||!source.trim())throw Error('AUDIT_EMPTY_SOURCE');
  const old=entries[r.id],wikiValues=wikiHashes.get(r.sourceHash);
  const reference=old?.sourceHash===r.sourceHash?old.ko:r.kind==='wiki'&&wikiValues?.size===1?[...wikiValues][0]:null;
  const context=r.kind==='wiki'?'wiki visible text':r.kind==='news'?'game patch notes':r.kind==='name'?'game item, monster or skill name':'game/talent language table';
  const terms=Object.fromEntries(Object.entries(memory.terms(source)).filter(([k,v])=>k.toLowerCase()!==source.trim().toLowerCase()&&v!==reference));
  rows.push({id:String(rows.length+1),recordId:r.id,sourceHash:r.sourceHash,kind:r.kind,source,context,terms,reference,sourceFallback:r.en===null});
 }
 if(!rows.length||rows.length>999999)throw Error('AUDIT_INVENTORY_SIZE');
 return {build:game.build,rows};
}
function counts(rows){
 return Object.fromEntries([...new Set(rows.map(r=>r.kind))].sort().map(k=>[k,rows.filter(r=>r.kind===k).length]));
}
async function prepare(dir,out){
 const catalog=await loadCatalog(),entries=mergeRecords(catalog.base,catalog.extra).entries;
 const inv=await inventory(await read(join(dir,'game.json')),await read(join(dir,'wiki.json')),entries,catalog.decisions);
 await mkdir(out,{recursive:true,mode:0o700});
 const batches=[];
 for(let i=0;i<inv.rows.length;i+=batchSize){
  const rows=inv.rows.slice(i,i+batchSize),batch=String(batches.length+1).padStart(4,'0');
  const digest=hash(JSON.stringify(rows.map(r=>[r.id,r.recordId,r.sourceHash])));
  await writeFile(join(out,'batch-'+batch+'.enc'),seal({build:inv.build,batch,rows},batch),{mode:0o600});
  batches.push({batch,count:rows.length,digest});
 }
 if(batches.length>256)throw Error('AUDIT_MATRIX_LIMIT');
 const manifest={build:inv.build,total:inv.rows.length,kinds:counts(inv.rows),withReference:inv.rows.filter(r=>r.reference!==null).length,
  sourceFallback:inv.rows.filter(r=>r.sourceFallback).length,productionDeferred:inv.rows.filter(r=>r.source==='1M'||r.source.length>1200||/[\r\n]/.test(r.source)).length,batches};
 await write(join(out,'manifest.json'),manifest);
 console.log('LIVE_AUDIT_INVENTORY '+JSON.stringify(manifest));
 if(process.env.GITHUB_OUTPUT)await import('node:fs/promises').then(fs=>fs.appendFile(process.env.GITHUB_OUTPUT,'matrix='+JSON.stringify({include:batches.map(({batch})=>({batch}))})+'\n'));
}
async function unpack(dir,batch,out){
 const manifest=await read(join(dir,'manifest.json')),expected=manifest.batches.find(b=>b.batch===batch);
 if(!expected)throw Error('AUDIT_BATCH_UNKNOWN');
 const data=unseal(await readFile(join(dir,'batch-'+batch+'.enc')),batch);
 if(data.build!==manifest.build||data.batch!==batch||data.rows.length!==expected.count||
  hash(JSON.stringify(data.rows.map(r=>[r.id,r.recordId,r.sourceHash])))!==expected.digest)throw Error('AUDIT_BATCH_INTEGRITY');
 await mkdir(out,{recursive:true,mode:0o700});
 await write(join(out,'audit-batch.json'),data);
 await write(join(out,'pending.json'),data.rows.map(({id,source,context,terms})=>({id,source,context,terms})));
 await write(join(out,'audit-references.json'),Object.fromEntries(data.rows.map(r=>[r.id,r.reference])));
 console.log('LIVE_AUDIT_BATCH '+batch+' ROWS='+data.rows.length);
}
async function summarize(dir,results){
 const manifest=await read(join(dir,'manifest.json'));
 let files=[];try{files=await readdir(results)}catch(e){if(e.code!=='ENOENT')throw e}
 const summaries=new Map(),totals={},examples=[];
 for(const file of files.filter(f=>/^result-\d{4}\.json$/.test(f))){
  const report=await read(join(results,file)),expected=manifest.batches.find(b=>b.batch===report.batch);
  if(!expected||summaries.has(report.batch)||report.build!==manifest.build||report.count!==expected.count||report.digest!==expected.digest)throw Error('AUDIT_REPORT_INTEGRITY');
  summaries.set(report.batch,report);
  for(const [k,v] of Object.entries(report.metrics)){
   if(typeof v!=='number'||!Number.isFinite(v)||v<0)throw Error('AUDIT_METRIC');
   totals[k]=(totals[k]??0)+v;
  }
  examples.push(...report.examples);
 }
 const missing=manifest.batches.filter(b=>!summaries.has(b.batch));
 const processed=[...summaries.values()].reduce((n,r)=>n+r.count,0);
 const summary={build:manifest.build,expected:manifest.total,processed,unprocessed:manifest.total-processed,completedBatches:summaries.size,totalBatches:manifest.batches.length,missingBatches:missing.map(b=>b.batch),metrics:totals};
 console.log('LIVE_AUDIT_FINAL '+JSON.stringify(summary));
 for(const e of examples.slice(0,20))console.log('LIVE_AUDIT_EXAMPLE '+JSON.stringify(e));
 if(process.env.GITHUB_STEP_SUMMARY){
  const lines=['# Full live translation audit','', 'Build: '+manifest.build,'','Processed: '+processed+'/'+manifest.total+' (batches '+summaries.size+'/'+manifest.batches.length+')','','| Metric | Count |','| --- | ---: |',...Object.entries(totals).map(([k,v])=>'| '+k+' | '+v+' |'),'','Reference wording matches and Qwen opinions are diagnostics, not proof of human-level translation accuracy. No candidates were published.'];
  await import('node:fs/promises').then(fs=>fs.appendFile(process.env.GITHUB_STEP_SUMMARY,lines.join('\n')+'\n'));
 }
 if(missing.length)throw Error('AUDIT_INCOMPLETE');
}
async function main(){
 const [mode,dir,arg,out]=process.argv.slice(2);
 if(mode==='prepare')await prepare(dir,arg);
 else if(mode==='unpack')await unpack(dir,arg,out);
 else if(mode==='summarize')await summarize(dir,arg);
 else throw Error('AUDIT_MODE');
}
if(process.argv[1]&&import.meta.url===pathToFileURL(resolve(process.argv[1])).href)await main();
