// Offline benchmark preparation. Never contact the game or reselect the sample.
import {readFile,writeFile,mkdir} from 'node:fs/promises';
import {resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
import {createHash} from 'node:crypto';
const root=resolve(process.argv[2]),temp=resolve(process.argv[3]);
const fixture=JSON.parse(await readFile(new URL('./colab-benchmark-fixture.json',import.meta.url),'utf8'));
const baseline=JSON.parse(await readFile(new URL('./colab-benchmark-baseline.json',import.meta.url),'utf8'));
const {loadCatalog,mergeRecords}=await import(pathToFileURL(root+'/tools/records.mjs'));
const {base,extra}=await loadCatalog(root+'/translations');
const pack=mergeRecords(base,extra);
const refs=fixture.rows;
const fail=message=>{throw Error('FIXED_BENCHMARK_INVALID: '+message);};
if(fixture.schema!==1||fixture.build!==baseline.build||fixture.referenceCommit!=='1533e8cd8b4507fa4cfd5b709dc0f6a722ba7b81'||fixture.baselineRun!==45939491249||fixture.baselineJob!==140310272517)fail('provenance');
if(!Array.isArray(refs)||refs.length!==200||new Set(refs.map(r=>r.source)).size!==200||JSON.stringify(refs.map(({id,recordId})=>({id,recordId})))!==JSON.stringify(baseline.rows))fail('sample identity');
const quotas={skill:40,gear:40,job:30,wiki:40,news:20,ui:30};
const counts=Object.fromEntries(Object.keys(quotas).map(k=>[k,0]));
for(const [i,r] of refs.entries()){
 if(Object.keys(r).sort().join(',')!=='context,group,id,recordId,reference,source'||r.id!==String(i+1).padStart(3,'0')||typeof r.source!=='string'||typeof r.reference!=='string'||typeof r.context!=='string'||!Object.hasOwn(quotas,r.group))fail('row schema '+i);
 const record=pack.entries[r.recordId];
 const hash=createHash('sha256').update(r.source,'utf8').digest('hex');
 if(!record||record.sourceHash!==hash||record.ko!==r.reference)fail('approved source/reference mismatch '+r.id);
 counts[r.group]++;
}
for(const [k,n] of Object.entries(quotas))if(counts[k]!==n)fail('quota '+k);
await mkdir(temp,{recursive:true,mode:0o700});
await writeFile(temp+'/references.json',JSON.stringify(refs),{mode:0o600});
await writeFile(temp+'/inputs.json',JSON.stringify(refs.map(({id,source,group,context})=>({id,source,group,context}))),{mode:0o600});
console.log('BASELINE_MATCH 200/200');
console.log('FIXED_BENCHMARK_SOURCE_HASH_MATCH 200/200');
console.log('FIXED_BENCHMARK_REFERENCE_MATCH 200/200');
console.log('BENCHMARK_BUILD '+fixture.build+' (frozen; no live extraction)');
