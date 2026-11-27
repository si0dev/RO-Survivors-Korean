import {readFile,writeFile,mkdtemp,cp,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join,resolve} from 'node:path';
import {spawnSync} from 'node:child_process';
import assert from 'node:assert/strict';
const reference=resolve(process.argv[2]);
const tools=new URL('.',import.meta.url);
const tmp=await mkdtemp(join(tmpdir(),'ro-fixed-test-'));
try{
 for(const f of ['colab-benchmark-prepare.mjs','colab-benchmark-fixture.json','colab-benchmark-baseline.json'])await cp(new URL(f,tools),join(tmp,f));
 const fixturePath=join(tmp,'colab-benchmark-fixture.json');
 const fixture=JSON.parse(await readFile(fixturePath,'utf8'));
 const out=join(tmp,'out');
 const run=()=>spawnSync(process.execPath,[join(tmp,'colab-benchmark-prepare.mjs'),reference,out],{encoding:'utf8',timeout:30000});
 const normal=run();
 assert.equal(normal.status,0,normal.stderr);
 const refs=JSON.parse(await readFile(join(out,'references.json'),'utf8'));
 const inputs=JSON.parse(await readFile(join(out,'inputs.json'),'utf8'));
 assert.equal(refs.length,200);
 assert.deepEqual(inputs,refs.map(({id,source,group,context})=>({id,source,group,context})));
 assert.ok(normal.stdout.includes('FIXED_BENCHMARK_SOURCE_HASH_MATCH 200/200'));
 console.log(normal.stdout.trim());
 for(const key of ['source','reference','recordId','group']){
  const bad=structuredClone(fixture);
  bad.rows[0][key]+=' altered';
  await writeFile(fixturePath,JSON.stringify(bad));
  assert.notEqual(run().status,0,key+' was not rejected');
 }
 console.log('FIXED_BENCHMARK_TESTS 5/5 PASS');
}finally{await rm(tmp,{recursive:true,force:true});}
