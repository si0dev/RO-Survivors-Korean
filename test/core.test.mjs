import test from 'node:test';
import assert from 'node:assert/strict';
import {readMap,extractSnapshot,identify,worklist,compare,validateRecords,samePlaceholders,readNewsReleases,wikiTranslationLookup,createWikiTranslator} from '../src/core.mjs';
import {shouldScan,createSession,UPDATE_INTERVAL_MS,stateLabel,compareTranslationVersions} from '../src/session.mjs';
test('static map parser never evaluates values',()=>{
 assert.equal(readMap('{"a":"b",c:"d"}',0).map.c,'d');
 assert.throws(()=>readMap('{x:run()}',0));
});
test('source changes invalidate otherwise identical keys',async()=>{
 const a=await identify({kind:'ui',key:'x',en:'Damage {n}'});
 const b=await identify({kind:'ui',key:'x',en:'Damage {n} + 1'});
 assert.equal(a.id,b.id);assert.notEqual(a.sourceHash,b.sourceHash);
 const rec={[a.id]:{sourceHash:a.sourceHash,ko:'피해 {n}',placeholders:['{n}']}};
 assert.equal(compare([a],rec).hasMissing,false);
 assert.equal(compare([b],rec).changed,1);
 assert.equal(compare([await identify({kind:'ui',key:'y',en:'Y'})],rec).missing,1);
 assert.equal(samePlaceholders('{n} {n}','{n}'),false);
 assert.equal((await worklist({rows:[a]},rec))[0].approved,true);
 validateRecords({schema:1,version:'1',entries:rec});
});
test('only same-version reload skips scan',()=>{
 const base={build:'a',translationVersion:'b',previous:{build:'a',translationVersion:'b'}};
 assert.equal(shouldScan({...base,navigationType:'navigate'}),true);
 assert.equal(shouldScan({...base,navigationType:'reload'}),false);
 assert.equal(shouldScan({...base,navigationType:'reload',build:'c'}),true);
 assert.equal(shouldScan({...base,navigationType:'reload',translationVersion:'c'}),true);
 assert.equal(shouldScan({...base,navigationType:'reload',previous:null}),true);
 assert.equal(UPDATE_INTERVAL_MS,3600000);
});
test('download pending update silently without changing active translation or repeating scan',async()=>{
 const cache=new Map();let scans=0,latest='0.3.1',fail=false,notice;
 const session=createSession({read:async k=>cache.get(k),write:async(k,v)=>cache.set(k,v),check:async()=>{if(fail)throw Error('offline');return {translationHash:latest,translationVersion:latest}},download:async m=>m.translationHash,verify:async()=>true,scan:async()=>{scans++;return {hasMissing:true}},notify:v=>notice=v});
 assert.equal(await session.start({navigationType:'navigate',build:'build'}), '0.3.1');
 assert.equal(scans,1);assert.equal(notice.hasMissing,true);
 latest='0.3.2';await session.poll();assert.equal(notice.updateReady,true);assert.equal(notice.label,'일부 미번역');
 assert.equal(cache.get('translation').version,'0.3.2');
 fail=true;await session.poll();assert.equal(notice.updateReady,true);
 assert.equal(scans,1);
 const reloaded=createSession({read:async k=>cache.get(k),write:async(k,v)=>cache.set(k,v),check:async()=>{throw Error('offline')},download:async()=>null,verify:async()=>true,scan:async()=>{scans++;return {hasMissing:false}},notify:v=>notice=v});
 assert.equal(await reloaded.start({navigationType:'reload',build:'build'}),'0.3.2');
 assert.equal(notice.updateReady,false);assert.equal(notice.label,'');
 assert.equal(scans,2);
});

test('Unicode and single-quoted source strings are parsed',()=>{
 const map=readMap("{Común:'Common',Épico:\"Epic\",x:'a\\'b',y:'\\x41'}",0).map;
 assert.equal(map['Común'],'Common');assert.equal(map['Épico'],'Epic');
 assert.equal(map.x,"a'b");assert.equal(map.y,'A');
});

test('translation status never announces pending translation updates',()=>{
 assert.equal(stateLabel({hasMissing:true}),'일부 미번역');
 assert.equal(stateLabel({}),'');
 assert.equal(stateLabel({updateReady:true}),'');
 assert.equal(stateLabel({hasMissing:true,updateReady:true}),'일부 미번역');
 assert.equal(stateLabel({scanFailed:true,updateReady:true}),'번역 상태 확인 불가');
});

test('embedded and cached translation versions compare numerically without downgrading',()=>{
 assert.equal(compareTranslationVersions('0.3.3','0.3.0-dev'),1);
 assert.equal(compareTranslationVersions('0.3.3','0.3.10'),-1);
 assert.equal(compareTranslationVersions('0.3.3','0.3.3-dev'),1);
 assert.equal(compareTranslationVersions('0.3.3','0.3.3'),0);
});

test('corrupt or older remote data does not replace the cache',async()=>{
 const cache=new Map([['translation',{hash:'old',version:'0.4.1',pack:'old'}]]);
 let version='0.4.0',downloads=0,notice,valid=false;
 const session=createSession({read:async k=>cache.get(k),write:async(k,v)=>cache.set(k,v),check:async()=>({translationHash:'new',translationVersion:version}),download:async()=>{downloads++;return 'new';},verify:async()=>valid,scan:async()=>({hasMissing:false}),notify:s=>notice=s});
 await session.start({navigationType:'navigate',build:'game'});
 assert.equal(downloads,0);
 version='0.4.2';await session.poll();
 assert.equal(downloads,1);assert.equal(cache.get('translation').hash,'old');assert.equal(notice.updateReady,false);
 valid=true;await session.poll();
 assert.equal(cache.get('translation').hash,'new');assert.equal(notice.updateReady,true);
});

test('news extraction skips drafts, normalizes text and keeps latest separate from history',async()=>{
 const markdown=['# Changelog','English version of CHANGELOG.md','## Unreleased','- draft','## Beta 1.2 — date','### General','- [Change] A change','  continued here.','- [Fix] **Bold** and code','## Beta 1.1 — date','- Old untranslated news'].join('\n');
 const source='const news='+String.fromCharCode(96)+markdown+String.fromCharCode(96)+';';
 const releases=readNewsReleases([{content:source}]);
 assert.equal(releases.length,2);
 assert.deepEqual(releases[0].rows.map(r=>r.en),['Beta 1.2 — date','General','Change','A change continued here.','Fix','Bold','and code']);
 const latest=await Promise.all(releases[0].rows.map(identify));
 const history=await Promise.all(releases[1].rows.map(identify));
 const records=Object.fromEntries(latest.map(r=>[r.id,{sourceHash:r.sourceHash,ko:'번역',placeholders:[]}]));
 assert.equal(compare(latest,records).hasMissing,false);
 assert.equal(compare([...latest,...history],records).hasMissing,true);
 const edited=await identify({kind:'news',key:'Changed announcement',en:'Changed announcement'});
 assert.equal(compare([...latest,edited],records).hasMissing,true);
 assert.throws(()=>readNewsReleases([{content:'no changelog'}]));
});

test('wiki translations are scoped and matched by normalized source hash',async()=>{
 const row=await identify({kind:'wiki',key:'How to play',en:'How to play'});
 const other=await identify({kind:'news',key:'Other',en:'Other'});
 const lookup=wikiTranslationLookup({entries:{
  [row.id]:{sourceHash:row.sourceHash,ko:'플레이 방법',scope:'wiki'},
  [other.id]:{sourceHash:other.sourceHash,ko:'다른 소식'}
 }});
 const translateWiki=createWikiTranslator(lookup);
 assert.equal(await translateWiki('  How   to\nplay '),'플레이 방법');
 assert.equal(await translateWiki('How to play'),'플레이 방법');
 assert.equal(await translateWiki('How to play now'),undefined);
 assert.equal(await translateWiki('Other'),undefined);
 assert.equal(await translateWiki(null),undefined);
});

test('worklist does not seed missing rows from an obsolete dictionary',async()=>{
 const row={kind:'name',key:'Missing',en:'Missing'};
 const [item]=await worklist({rows:[row]}, {}, {Missing:'초안'});
 assert.equal(item.status,'missing');
 assert.equal(item.ko,'');
 assert.equal(item.approved,false);
});

test('literal MATK status label is extracted only when present',async()=>{
 const map=JSON.stringify(Object.fromEntries(Array.from({length:100},(_,i)=>['k'+i,'v'+i])));
 const fixture='// RO Survivors Build 1234567\n'+['en','zh','pt','ja'].map(k=>'const '+k+'='+map+','+k+'Names='+map+';').join('\n')+'\nconst languages={es:null,en:en,"zh-TW":zh,"pt-BR":pt,ja:ja};';
 const snapshot=content=>extractSnapshot([{url:'https://example.test/game.js',content}]);
 assert.equal(snapshot(fixture).rows.some(r=>r.kind==='ui'&&r.key==='MATK'),false);
 const row=snapshot(fixture+'\nconst stats=[["MATK",t=>t.matk,"int"]];').rows.find(r=>r.kind==='ui'&&r.key==='MATK');
 assert.deepEqual(row,{kind:'ui',key:'MATK',en:'MATK'});
 assert.equal((await identify(row)).id,'86d3e7c31f49ae65d0ed9b41226d31e848df6a2e3b5684afb394b1fc671ff2ff');
});
