import {test} from 'node:test';
import assert from 'node:assert/strict';
import {identify} from '../src/core.mjs';
import {inventory,seal,unseal} from '../tools/llm/live-audit.mjs';
test('full audit includes known rows, unknown rows and production-deferred rows',async()=>{
 const a=await identify({kind:'ui',key:'a',en:'Haste'}),b=await identify({kind:'wiki',key:'1M',en:'1M'}),c=await identify({kind:'news',key:'c',en:'Long\nnews'});
 const rows=(await inventory({build:'x',rows:[a,c,a]},{build:'x',rows:[b]},{[a.id]:{sourceHash:a.sourceHash,ko:'가속',placeholders:[]}})).rows;
 assert.equal(rows.length,3);
 assert.equal(rows[0].reference,'가속');
 assert.deepEqual(rows[0].terms,{});
 assert.equal(rows[2].source,'1M');
 assert.equal(rows[1].source,'Long\nnews');
});
test('transient archive authenticated and bound to batch',()=>{
 const k=Buffer.alloc(32,4),data={source:'private',reference:'정답'};
 const ciphertext=seal(data,'0001',k);
 assert.deepEqual(unseal(ciphertext,'0001',k),data);
 assert.throws(()=>unseal(ciphertext,'0002',k));
 assert.throws(()=>unseal(ciphertext,'0001',Buffer.alloc(32,5)));
});
