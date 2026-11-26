import test from 'node:test';
import assert from 'node:assert/strict';
import {createEngineUpdate,parseEngineVersion} from '../src/session.mjs';

const metadata=v=>'// ==UserScript==\n// @version '+v+'\n// ==/UserScript==\n';
test('engine metadata version is validated',()=>{
  assert.equal(parseEngineVersion(metadata('0.4.10')),'0.4.10');
  assert.throws(()=>parseEngineVersion('not a metadata file'));
  assert.throws(()=>parseEngineVersion(metadata('invalid')));
});
function fixture(previous){
  let stored=previous,remote='0.4.8',fail=false;
  const states=[],timers=[];
  const update=createEngineUpdate({
    version:'0.4.8',read:()=>stored,write:v=>{stored=v;},
    check:async()=>{if(fail)throw Error('offline');return metadata(remote);},
    notify:s=>states.push(s),schedule:(fn,ms)=>timers.push({fn,ms})
  });
  return {update,states,timers,get stored(){return stored;},setRemote:v=>{remote=v;},offline:()=>{fail=true;}};
}
test('first install and unchanged version do not show completion',()=>{
  for(const previous of [undefined,'0.4.8','0.4.9','invalid']){
    const f=fixture(previous);
    assert.deepEqual(f.states[0],{engineUpdateAvailable:false,engineUpdated:false});
    assert.equal(f.stored,'0.4.8');
    assert.equal(f.timers.length,0);
  }
});
test('upgrade completion is emitted for five seconds',()=>{
  const f=fixture('0.4.7');
  assert.equal(f.states.at(-1).engineUpdated,true);
  assert.equal(f.timers[0].ms,5000);
  f.timers[0].fn();
  assert.equal(f.states.at(-1).engineUpdated,false);
  assert.equal(fixture(f.stored).states[0].engineUpdated,false);
});
test('newer remote version is detected numerically and persists on failure',async()=>{
  const f=fixture('0.4.8');
  await f.update.poll();
  assert.equal(f.states.at(-1).engineUpdateAvailable,false);
  f.setRemote('0.4.10');
  await f.update.poll();
  assert.equal(f.states.at(-1).engineUpdateAvailable,true);
  f.setRemote('invalid');
  await f.update.poll();
  assert.equal(f.states.at(-1).engineUpdateAvailable,true);
  f.offline();
  await f.update.poll();
  assert.equal(f.states.at(-1).engineUpdateAvailable,true);
});
test('older or equal published version never advertises an update',async()=>{
  const f=fixture('0.4.8');
  f.setRemote('0.4.7');
  await f.update.poll();
  assert.equal(f.states.at(-1).engineUpdateAvailable,false);
});
