import test from 'node:test';
import assert from 'node:assert/strict';
import {preparePublication} from '../tools/publish-data.mjs';
import {sha256} from '../src/core.mjs';
const id='a'.repeat(64),entry=ko=>({sourceHash:'b'.repeat(64),ko,placeholders:[]});
const pack={schema:1,version:'0.3.19',gameBuild:'old',entries:{[id]:entry('기존')}};
test('publish only data changes, advance version automatically and verify hash',async()=>{
 const first=await preparePublication(pack);
 assert.equal(first.manifest.translationVersion,'0.4.0');
 assert.equal(first.manifest.translationHash,await sha256(first.raw));
 const same=await preparePublication({...pack,version:'0.3.20'},first);
 assert.equal(same.changed,false);
 assert.equal(same.raw,first.raw);
 const next=await preparePublication({...pack,entries:{[id]:entry('수정')}},first);
 assert.equal(next.manifest.translationVersion,'0.4.1');
 assert.equal(JSON.parse(next.raw).entries[id].ko,'수정');
 assert.equal(next.manifest.translationHash,await sha256(next.raw));
 const third=await preparePublication({...pack,gameBuild:'new'},next);
 assert.equal(third.manifest.translationVersion,'0.4.2');
});
test('reject corrupt previous data and accidental loss of records',async()=>{
 const first=await preparePublication(pack);
 await assert.rejects(()=>preparePublication(pack,{...first,raw:first.raw+' '}),/Invalid previous/);
 await assert.rejects(()=>preparePublication({...pack,entries:{}},first),/Unapproved translation removal/);
});

test('only explicitly retired IDs with matching old source hashes may be removed',async()=>{
 const first=await preparePublication(pack);
 const replacement={...pack,entries:{['c'.repeat(64)]:entry('추가')}};
 await assert.rejects(()=>preparePublication(replacement,first),/Unapproved translation removal/);
 await assert.rejects(()=>preparePublication(replacement,first,{[id]:'d'.repeat(64)}),/Unapproved translation removal/);
 const result=await preparePublication(replacement,first,{[id]:pack.entries[id].sourceHash});
 assert.equal(result.changed,true);
 assert.deepEqual(JSON.parse(result.raw).entries,replacement.entries);
});

test('retiring an old fallback dictionary republishes identical verified records',async()=>{
 const first=await preparePublication({...pack,legacy:{old:'이전 번역'}});
 const next=await preparePublication(pack,first);
 assert.equal(next.changed,true);
 assert.equal(next.manifest.translationVersion,'0.4.1');
 assert.deepEqual(JSON.parse(next.raw).entries,pack.entries);
 assert.equal(Object.hasOwn(JSON.parse(next.raw),'legacy'),false);
 assert.equal((await preparePublication(pack,next)).changed,false);
});
