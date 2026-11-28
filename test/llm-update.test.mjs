import {test} from 'node:test';
import assert from 'node:assert/strict';
import {identify} from '../src/core.mjs';
import {plan,assemble} from '../tools/llm/update.mjs';
test('production plan uses only new or changed source and unique memory',async()=>{
 const a=await identify({kind:'ui',key:'a',en:'Haste'}),b=await identify({kind:'wiki',key:'Haste',en:'Haste'}),c=await identify({kind:'ui',key:'c',en:'New skill'});
 const p=await plan({build:'one',rows:[a,c]},{build:'one',rows:[b]},{[a.id]:{sourceHash:a.sourceHash,ko:'가속',placeholders:[]}});
 assert.equal(p.rows.length,2);
 assert.equal(p.pending.length,1);
 assert.equal(p.reused.length,1);
 const work=await assemble(p,[{id:p.pending[0].id,ko:'신규 스킬',status:'MODEL_VERIFIED'}]);
 assert.equal(work.rows.length,2);
 assert.equal(work.unresolved.length,0);
 await assert.rejects(assemble(p,[]),/INCOMPLETE_MODEL_RESULTS/);
 const rejected=await assemble(p,[{id:p.pending[0].id,ko:'',status:'REVIEW_REQUIRED'}]);
 assert.equal(rejected.rows.length,1);
 assert.equal(rejected.unresolved.length,1);
 await assert.rejects(plan({build:'one',rows:[]},{build:'two',rows:[]},{}),/SOURCE_BUILD_MISMATCH/);
});
test('changed source never reuses old translation or ambiguous hash',async()=>{
 const a=await identify({kind:'ui',key:'a',en:'New name'}),old=await identify({kind:'ui',key:'a',en:'Old name'});
 const p=await plan({build:'one',rows:[a]},{build:'one',rows:[]},{[a.id]:{sourceHash:old.sourceHash,ko:'이전 이름',placeholders:[]},b:{sourceHash:a.sourceHash,ko:'이름 A',placeholders:[]},c:{sourceHash:a.sourceHash,ko:'이름 B',placeholders:[]}});
 assert.equal(p.pending.length,1);
 assert.equal(p.reused.length,0);
});
