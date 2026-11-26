import test from 'node:test';
import assert from 'node:assert/strict';
import {buildScanDictionary,patchStatusPlacement,gameNoticeTop,pageBundleType,findPageBundle,sourceSnapshot,matchingTalentFallback,hasGameNotice} from '../src/browser.mjs';
import {shouldPublishEngine} from '../tools/publish-engine.mjs';

test('main status uses the verified sp-version element, never a floating fallback',()=>{
 const screens=new Map();
 const doc={getElementById:id=>screens.get(id)};
 const set=(id,visible)=>screens.set(id,{hidden:false,classList:{contains:c=>c==='hidden'&&!visible},contains:el=>el===screens.get('sp-version')});
 const anchor={textContent:'v\u2060\u200b2026.11.24 · 6b5475ee1',closest:()=>null};
 assert.deepEqual(patchStatusPlacement(doc),{mode:'hidden'});
 set('splash',true);set('charselect',false);set('lobby-ui',false);set('hud',false);
 assert.deepEqual(patchStatusPlacement(doc),{mode:'hidden'});
 screens.set('sp-version',anchor);
 assert.deepEqual(patchStatusPlacement(doc),{mode:'panel',anchor});
 anchor.textContent=''; // insertion does not depend on text or locale
 assert.deepEqual(patchStatusPlacement(doc),{mode:'panel',anchor});
 anchor.closest=()=>({});
 assert.deepEqual(patchStatusPlacement(doc),{mode:'hidden'});
 anchor.closest=()=>null;
 screens.get('splash').contains=()=>false;
 assert.deepEqual(patchStatusPlacement(doc),{mode:'hidden'});
 screens.get('splash').contains=()=>true;
 set('charselect',true);
 assert.deepEqual(patchStatusPlacement(doc),{mode:'hidden'});
 set('charselect',false);set('splash',false);set('lobby-ui',true);
 assert.deepEqual(patchStatusPlacement(doc),{mode:'game',screen:screens.get('lobby-ui')});
 set('lobby-ui',false);set('hud',true);
 assert.deepEqual(patchStatusPlacement(doc),{mode:'game',screen:screens.get('hud')});
 set('splash',true);
 assert.deepEqual(patchStatusPlacement(doc),{mode:'game',screen:screens.get('hud')});
 set('hud',false);
 assert.deepEqual(patchStatusPlacement(doc),{mode:'panel',anchor});
 assert.deepEqual(patchStatusPlacement(doc,'/talents.html'),{mode:'standalone'});
});
const make=version=>{
 const meta=['// ==UserScript==','// @version '+version,'// @updateURL https://raw.githubusercontent.com/si0dev/RO-Survivors-Korean/translation-data/ro-ko.meta.js','// @downloadURL https://raw.githubusercontent.com/si0dev/RO-Survivors-Korean/translation-data/ro-ko.user.js','// ==/UserScript==',''].join('\n');
 return {meta,script:meta+'void 0;\n'};
};
test('publish userscript once per engine version, independent of data changes',()=>{
 const first=make('0.4.4');
 assert.equal(shouldPublishEngine(first),true);
 assert.equal(shouldPublishEngine({...first,script:first.script+'// new data\n'},first.meta),false);
 assert.equal(shouldPublishEngine(make('0.4.5'),first.meta),true);
 assert.throws(()=>shouldPublishEngine(make('0.4.3'),first.meta),/decreased/);
 assert.throws(()=>shouldPublishEngine({...first,script:'broken'}),/Invalid engine/);
});

test('talent page selects its own same-origin entry bundle',()=>{
 const home='https://ro-survivors.com/';
 const talents=home+'talents.html';
 const urls=['https://example.com/build/talents-fake.js','/build/main-test.js','/build/soul_linker-shared.js','/build/talents-test.js'];
 assert.equal(pageBundleType('/'),'main');
 assert.equal(pageBundleType('/talents.html'),'talents');
 assert.equal(pageBundleType('/talents'),'talents');
 assert.equal(findPageBundle(urls,home),home+'build/main-test.js');
 assert.equal(findPageBundle(urls,talents),home+'build/talents-test.js');
 assert.equal(findPageBundle(urls.slice(0,3),talents),undefined);
});

test('talents load the shared language table without depending on the item manifest',async()=>{
 const pairs=Object.fromEntries(Array.from({length:100},(_,i)=>['label'+i,'English '+i]));
 const names=Object.fromEntries(Array.from({length:100},(_,i)=>['name'+i,'Name '+i]));
 const table=JSON.stringify(pairs),nameTable=JSON.stringify(names);
 const shared='const a='+table+',an='+nameTable+',b='+table+',bn='+nameTable+',c='+table+',cn='+nameTable+',d='+table+',dn='+nameTable+';const lang={es:null,en:a,"zh-TW":b,"pt-BR":c,ja:d};';
 const main={kind:'talents',build:'6b5475ee1',url:'https://ro-survivors.com/build/talents-test.js',content:'/* RO Survivors Build 6b5475ee1 */\nimport {t} from "./shared.js";'};
 const fetched=[];
 const read=async url=>{fetched.push(url);if(url.endsWith('/shared.js'))return shared;throw Error('Manifest unavailable');};
 const snapshot=await sourceSnapshot(main,read);
 assert.equal(snapshot.rows.filter(row=>row.kind==='ui').length,100);
 assert.deepEqual(fetched,['https://ro-survivors.com/build/shared.js']);
 await assert.rejects(sourceSnapshot({...main,kind:'main'},read),/Manifest unavailable/);
});

test('talent scan failure can reuse only a verified same-build and same-data main dictionary',()=>{
 const main={kind:'talents',build:'game'};
 const cache={build:'game',translationVersion:'hash',dictionary:{hello:'안녕'},hasMissing:false};
 assert.deepEqual(matchingTalentFallback(main,'hash',cache),{...cache,scanFailed:true});
 assert.equal(matchingTalentFallback(main,'new',cache),null);
 assert.equal(matchingTalentFallback({...main,build:'new'},'hash',cache),null);
 assert.equal(matchingTalentFallback({...main,kind:'main'},'hash',cache),null);
 assert.equal(matchingTalentFallback(main,'hash',{...cache,dictionary:{}}),null);
});

test('game notice is placed below the compact top-centred timer, currency or region display',()=>{
 const el=(left,top,width,height,hidden=false)=>({textContent:'label',closest:()=>hidden?{}:null,getBoundingClientRect:()=>({left,right:left+width,top,bottom:top+height,width,height})});
 const screen={querySelectorAll:()=>[el(470,10,60,28),el(435,44,130,20),el(10,15,200,80),el(780,10,200,100),el(450,100,100,20,true),el(0,0,1000,800)]};
 assert.equal(gameNoticeTop(screen,1000,800),72);
 const lobby={querySelectorAll:()=>[el(445,12,110,53)]};
 assert.equal(gameNoticeTop(lobby,1000,800),73);
 assert.equal(gameNoticeTop({querySelectorAll:()=>[]},1000,800),80);
});

test('only engine updates create a lobby or combat notice',()=>{
 assert.equal(hasGameNotice({updateReady:true}),false);
 assert.equal(hasGameNotice({hasMissing:true,scanFailed:true,updateReady:true}),false);
 assert.equal(hasGameNotice({engineUpdateAvailable:true,updateReady:true}),true);
 assert.equal(hasGameNotice({engineUpdated:true}),true);
 assert.equal(hasGameNotice({}),false);
});

test('only verified records are applied, even when an old cached pack contains a fallback dictionary',()=>{
 const rows=[
   {id:'a',kind:'ui',key:'a',en:'Approved',sourceHash:'1'},
   {id:'b',kind:'name',key:'Missing',en:'Missing',sourceHash:'2'},
   {id:'c',kind:'ui',key:'c',en:'Changed',sourceHash:'3'}
 ];
 const history=[{id:'d',kind:'news',key:'News',en:'News',sourceHash:'4'}];
 const pack={entries:{a:{sourceHash:'1',ko:'승인'},c:{sourceHash:'old',ko:'이전'},d:{sourceHash:'4',ko:'소식'}},legacy:{Missing:'초안',Changed:'초안'}};
 const result=buildScanDictionary(rows,history,pack);
 assert.equal(result.dictionary.a,'승인');
 assert.equal(result.dictionary.Approved,'승인');
 assert.equal(Object.hasOwn(result.dictionary,'Missing'),false);
 assert.equal(Object.hasOwn(result.dictionary,'c'),false);
 assert.equal(result.newsDictionary.News,'소식');
 assert.equal(result.missing,1);
 assert.equal(result.changed,1);
});

test('main manifest includes card names as verified name rows',async()=>{
 const pairs=Object.fromEntries(Array.from({length:100},(_,i)=>['label'+i,'English '+i]));
 const names=Object.fromEntries(Array.from({length:100},(_,i)=>['name'+i,'Name '+i]));
 const table=JSON.stringify(pairs),nameTable=JSON.stringify(names);
 const shared='const a='+table+',an='+nameTable+',b='+table+',bn='+nameTable+',c='+table+',cn='+nameTable+',d='+table+',dn='+nameTable+';const lang={es:null,en:a,"zh-TW":b,"pt-BR":c,ja:d};';
 const main={kind:'main',build:'6b5475ee1',url:'https://ro-survivors.com/build/main-test.js',content:'/* RO Survivors Build 6b5475ee1 */\nimport {t} from "./shared.js";'};
 const snapshot=await sourceSnapshot(main,async url=>url.endsWith('/shared.js')?shared:JSON.stringify({items:{1:{name:'Item'}},cards:{2:{name:'Baphomet Card'}}}));
 assert.ok(snapshot.rows.some(r=>r.kind==='name'&&r.key==='Baphomet Card'&&r.en==='Baphomet Card'));
 assert.ok(snapshot.rows.some(r=>r.kind==='name'&&r.key==='Item'));
});
