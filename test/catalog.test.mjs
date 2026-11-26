import test from 'node:test';
import assert from 'node:assert/strict';
import {identify,compare,worklist,validateRecords} from '../src/core.mjs';
import {preparePublication} from '../tools/publish-data.mjs';
import {buildCatalog,expandCatalog,rebuildCatalog,classifyNew,loadCatalog,loadRecords,mergeRecords,saveParts} from '../tools/records.mjs';
import {mkdtemp,readFile,writeFile,rm,mkdir} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {fileURLToPath} from 'node:url';
import {execFileSync} from 'node:child_process';

const pack=(entries,version='0.3.23')=>({schema:1,version,gameBuild:'fixture',entries});
const record=(row,ko,scope)=>({sourceHash:row.sourceHash,ko,placeholders:[],...(scope?{scope}:{})});
async function fixture(){
 const a=await identify({kind:'ui',key:'stable-key',en:'Poring Card'});
 const b=await identify({kind:'wiki',key:'Poring Card',en:'Poring Card'});
 const base=pack({[a.id]:record(a,'포링 카드')});
 const extra=pack({[b.id]:record(b,'포링 카드','wiki'),[a.id]:record(a,'포링 카드')});
 const decisions={[a.id]:{type:'fixed',reason:'history-name'},[b.id]:{type:'fixed',reason:'same-named-source'}};
 const common={[a.id]:{...base.entries[a.id],reason:'fixture'}};
 const refs={[a.id]:a.id,[b.id]:a.id};
 return {a,b,base,extra,...buildCatalog(base,extra,decisions,common,refs)};
}
test('all managed records expand and rebuild without changing either original part or publication format',async()=>{
 const old=await loadCatalog();
 const rebuilt=rebuildCatalog(old.base,old.extra,old);
 const next=expandCatalog(rebuilt.catalog,rebuilt.files,rebuilt.common);
 assert.equal(JSON.stringify(next.base),JSON.stringify(old.base));
 assert.equal(JSON.stringify(next.extra),JSON.stringify(old.extra));
 const published=await loadRecords();
 assert.equal(JSON.stringify(published),JSON.stringify(mergeRecords(next.base,next.extra)));
 validateRecords(published);
 assert.equal(Object.keys(old.decisions).length,Object.keys(published.entries).length);
 assert.ok(Object.values(old.decisions).some(x=>x.type==='fixed'));
 assert.ok(Object.values(old.decisions).some(x=>x.type==='variable'));
 assert.ok(Object.values(old.decisions).some(x=>x.type==='news'));
 assert.ok(Object.keys(old.common).length>0);
 const initial=await preparePublication(published);
 const repeat=await preparePublication(mergeRecords(next.base,next.extra),initial);
 assert.equal(repeat.changed,false);
 assert.equal(repeat.raw,initial.raw);
 assert.deepEqual(repeat.manifest,initial.manifest);
});
test('common edit changes intended uses, preserving each source ID, hash, scope and duplicate position',async()=>{
 const f=await fixture();
 f.common[f.a.id].ko='포링 카드 수정';
 const {base,extra}=expandCatalog(f.catalog,f.files,f.common);
 for(const id of [f.a.id,f.b.id])assert.equal(mergeRecords(base,extra).entries[id].ko,'포링 카드 수정');
 assert.equal(base.entries[f.a.id].sourceHash,f.a.sourceHash);
 assert.equal(extra.entries[f.b.id].sourceHash,f.b.sourceHash);
 assert.equal(extra.entries[f.b.id].scope,'wiki');
 assert.deepEqual(base.entries[f.a.id],extra.entries[f.a.id]);
});
test('independent source change invalidates only its own ID, then splits a shared value on import',async()=>{
 const f=await fixture();
 const previous=expandCatalog(f.catalog,f.files,f.common);
 const changed=await identify({kind:'ui',key:f.a.key,en:'New card label'});
 assert.equal(changed.id,f.a.id);
 assert.deepEqual(compare([changed,f.b],mergeRecords(previous.base,previous.extra).entries),{missing:0,changed:1,hasMissing:true});
 const next=record(changed,'새 카드 명칭');
 f.base.entries[changed.id]=next;f.extra.entries[changed.id]=next;
 const rebuilt=rebuildCatalog(f.base,f.extra,previous,[changed]);
 const after=expandCatalog(rebuilt.catalog,rebuilt.files,rebuilt.common);
 assert.equal(Object.keys(after.common).length,0);
 assert.deepEqual(after.extra.entries[f.b.id],previous.extra.entries[f.b.id]);
 assert.deepEqual(after.base.entries[changed.id],next);
 assert.deepEqual(compare([changed,f.b],mergeRecords(after.base,after.extra).entries),{missing:0,changed:0,hasMissing:false});
});
test('management file writes preserve classification and shared values, including an incremental import',async()=>{
 const f=await fixture(),dir=await mkdtemp(join(tmpdir(),'ro-catalog-'));
 try{
  for(const [name,data] of Object.entries({catalog:f.catalog,common:f.common,...f.files}))await writeFile(join(dir,name+'.json'),JSON.stringify(data));
  const previous=await loadCatalog(dir);
  const added=await identify({kind:'name',key:'New monster',en:'New monster'});
  previous.extra.entries[added.id]=record(added,'새 몬스터');
  await saveParts(previous.base,previous.extra,[added],dir);
  const stored=JSON.parse(await readFile(join(dir,'game-talents-fixed.json'),'utf8'));
  assert.equal(Object.hasOwn(stored[added.id],'type'),false);
  assert.equal(Object.hasOwn(stored[added.id].record,'placeholders'),false);
  const next=await loadCatalog(dir);
  assert.deepEqual(next.extra.entries[added.id].placeholders,[]);
  assert.deepEqual(next.decisions[added.id],{type:'fixed',reason:'import-name'});
  assert.equal(next.refs[f.b.id],f.a.id);
  assert.equal(next.extra.entries[added.id].ko,'새 몬스터');
 }finally{await rm(dir,{recursive:true,force:true});}
});
test('source detection is independent of classification, including numeric and nonnumeric changes',async()=>{
 const original=await identify({kind:'ui',key:'damage',en:'Damage increases 10%'});
 const numeric=await identify({kind:'ui',key:'damage',en:'Damage increases 20%'});
 const condition=await identify({kind:'ui',key:'damage',en:'Damage increases when frozen'});
 const newName=await identify({kind:'name',key:'New',en:'New'});
 const records={[original.id]:record(original,'피해량 10% 증가')};
 assert.equal(classifyNew(records[original.id],original).type,'variable');
 assert.equal(classifyNew(record(newName,'신규'),newName).type,'fixed');
 assert.equal(classifyNew(record(newName,'새 소식'),{kind:'news'}).type,'news');
 assert.equal(classifyNew(record(newName,'미확인 문구')).reason,'insufficient-context');
 for(const changed of [numeric,condition])assert.equal((await worklist({rows:[changed]},records))[0].status,'changed');
 assert.equal((await worklist({rows:[original]},records))[0].status,'translated');
 assert.equal((await worklist({rows:[newName]},records))[0].status,'missing');
 assert.deepEqual(await worklist({rows:[]},records),[]);
 assert.equal(Object.keys(records).length,1); // an absent extraction never deletes a record
});
test('different contextual translations are never merged automatically; malformed references are rejected',async()=>{
 const f=await fixture();
 const previous=expandCatalog(f.catalog,f.files,f.common);
 const diff=record(f.b,'다른 문맥','wiki');
 f.extra.entries[f.b.id]=diff;
 const result=rebuildCatalog(f.base,f.extra,previous);
 assert.equal(Object.keys(result.common).length,0);
 assert.deepEqual(expandCatalog(result.catalog,result.files,result.common).extra.entries[f.b.id],diff);
 const broken=await fixture();
 broken.common[broken.a.id].sourceHash='f'.repeat(64);
 assert.throws(()=>expandCatalog(broken.catalog,broken.files,broken.common),/Common source mismatch/);
 const duplicate=await fixture();
 duplicate.extra.entries[duplicate.a.id]=record(duplicate.a,'다른 번역');
 assert.throws(()=>buildCatalog(duplicate.base,duplicate.extra,previous.decisions),/Conflicting duplicate ID/);
});

test('approved import command updates one shared source without affecting the other',async()=>{
 const f=await fixture(),dir=await mkdtemp(join(tmpdir(),'ro-import-'));
 try{
  const translations=join(dir,'translations');await mkdir(translations);
  for(const [name,data] of Object.entries({catalog:f.catalog,common:f.common,...f.files}))await writeFile(join(translations,name+'.json'),JSON.stringify(data));
  const changed=await identify({kind:'ui',key:f.a.key,en:'Changed card label'});
  const added=await identify({kind:'name',key:'New monster',en:'New monster'});
  const rows=[{...changed,approved:true,ko:'변경된 카드'},{...added,approved:true,ko:'새 몬스터'},{...f.b,approved:false,ko:'수정하면 안 됨'}];
  const work=join(dir,'worklist.json');await writeFile(work,JSON.stringify({build:'fixture-new',rows}));
  execFileSync(process.execPath,[fileURLToPath(new URL('../tools/import.mjs',import.meta.url)),work,'0.3.24'],{cwd:dir,encoding:'utf8'});
  const next=await loadCatalog(translations);
  assert.equal(next.extra.version,'0.3.24');
  assert.equal(next.extra.gameBuild,'fixture-new');
  assert.equal(next.base.gameBuild,f.base.gameBuild);
  assert.equal(next.base.entries[changed.id].sourceHash,changed.sourceHash);
  assert.equal(next.base.entries[changed.id].ko,'변경된 카드');
  assert.deepEqual(next.base.entries[changed.id],next.extra.entries[changed.id]);
  assert.deepEqual(next.extra.entries[f.b.id],f.extra.entries[f.b.id]);
  assert.equal(next.extra.entries[added.id].ko,'새 몬스터');
  assert.equal(next.decisions[added.id].type,'fixed');
  assert.equal(Object.keys(next.common).length,0);
 }finally{await rm(dir,{recursive:true,force:true});}
});
test('common variable records retain independent hashes and split when only one condition changes',async()=>{
 const source='Damage increases by 10%';
 const a=await identify({kind:'ui',key:'damage-ui',en:source});
 const b=await identify({kind:'wiki',key:source,en:source});
 const base=pack({[a.id]:record(a,'피해량 10% 증가')});
 const extra=pack({[b.id]:record(b,'피해량 10% 증가','wiki')});
 const decisions=Object.fromEntries([a.id,b.id].map(id=>[id,{type:'variable',reason:'effect-or-condition'}]));
 const shared=buildCatalog(base,extra,decisions,{[a.id]:{...base.entries[a.id],reason:'fixture'}},{[a.id]:a.id,[b.id]:a.id});
 const prior=expandCatalog(shared.catalog,shared.files,shared.common);
 const changed=await identify({kind:'ui',key:a.key,en:'Damage increases when frozen'});
 assert.equal(compare([changed,b],mergeRecords(base,extra).entries).changed,1);
 base.entries[a.id]=record(changed,'동빙 시 피해량 증가');
 const next=rebuildCatalog(base,extra,prior,[changed]);
 const after=expandCatalog(next.catalog,next.files,next.common);
 assert.equal(after.decisions[a.id].type,'variable');
 assert.equal(after.decisions[b.id].type,'variable');
 assert.deepEqual(after.extra.entries[b.id],extra.entries[b.id]);
 assert.equal(after.base.entries[a.id].sourceHash,changed.sourceHash);
 assert.equal(Object.keys(after.refs).length,0);
});
