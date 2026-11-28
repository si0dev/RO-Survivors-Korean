import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {buildMemory,assertFrozenCatalog} from './colab-benchmark-memory.mjs';
const row=(en,ko)=>({sourceHash:createHash('sha256').update(en).digest('hex'),ko,placeholders:[]});
test('exact source only, conflicts fail closed, longest term wins',()=>{
 const m=buildMemory({a:row('Discovery','아이템 희귀도'),b:row('Ore Discovery','광석발견'),c:row('Haste','가속'),d:row('Flee','회피'),e:row('Flee','도주')});
 assert.equal(m.lookup('Ore Discovery'),'광석발견');
 assert.equal(m.lookup('ore discovery'),null);
 assert.equal(m.lookup('Flee'),null);
 assert.deepEqual(m.terms('Ore Discovery and Haste'),{'Ore Discovery':'광석발견','Haste':'가속'});
 assert.deepEqual(m.terms('Flee'),{});
 assert.deepEqual(m.terms('Hasteful'),{});
});

test('record ID resolves same-source conflicts but never reuses changed source',()=>{
 const m=buildMemory({a:row('Flee','회피'),b:row('Flee','도주'),c:row('Armor','방어력'),d:row('Pierce','피어스')});
 assert.equal(m.lookup('Flee'),null);
 assert.equal(m.lookup('Flee','a'),'회피');
 assert.equal(m.lookup('Flee','b'),'도주');
 assert.equal(m.lookup('Changed','a'),null);
 assert.equal(m.lookup('Flee','missing'),null);
 assert.deepEqual(m.terms('pierce on armor'),{});
});

test('frozen evaluation rejects a removed or changed record before allocating GPU',()=>{
 const sample=[{id:'043',recordId:'a',source:'A +10–20% bonus',reference:'보너스 +10~20%'}];
 const entries={a:row(sample[0].source,sample[0].reference)};
 assert.doesNotThrow(()=>assertFrozenCatalog(sample,entries));
 assert.throws(()=>assertFrozenCatalog(sample,{}),/MEMORY_FROZEN_CATALOG_MISMATCH 043/);
 assert.throws(()=>assertFrozenCatalog(sample,{a:row('A +10–30% bonus',sample[0].reference)}),/MEMORY_FROZEN_CATALOG_MISMATCH 043/);
 assert.throws(()=>assertFrozenCatalog(sample,{a:row(sample[0].source,'다른 번역')}),/MEMORY_FROZEN_CATALOG_MISMATCH 043/);
});
