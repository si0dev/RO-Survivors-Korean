import test from 'node:test';
import assert from 'node:assert/strict';
import {mergeRecords,loadRecords} from '../tools/records.mjs';
test('translation shards merge and retain existing duplicate records',()=>{
 const a='a'.repeat(64),b='b'.repeat(64),hash='c'.repeat(64),entry=ko=>({sourceHash:hash,ko,placeholders:[]});
 const merged=mergeRecords({schema:1,version:'1.0.0',entries:{[a]:entry('기존')}},{schema:1,version:'1.0.1',entries:{[a]:entry('중복'),[b]:entry('추가')}});
 assert.equal(merged.version,'1.0.1');assert.equal(merged.entries[a].ko,'기존');assert.equal(merged.entries[b].ko,'추가');
});
test('original baseline of 5963 translation records is not lost',async()=>{assert.ok(Object.keys((await loadRecords()).entries).length>=5963);});


test('wiki search result title translates both original language variants',async()=>{
 const {wikiTranslationLookup,createWikiTranslator}=await import('../src/core.mjs');
 const translate=createWikiTranslator(wikiTranslationLookup(await loadRecords()));
 assert.equal(await translate('Search'),'검색');
 assert.equal(await translate('Búsqueda'),'검색');
 assert.equal(await translate('Search the wiki…'),'위키 검색…');
});


test('Whisper monster and wiki names are distinct from private chat labels',async()=>{
 const {identify,wikiTranslationLookup,createWikiTranslator}=await import('../src/core.mjs');
 const {buildScanDictionary}=await import('../src/browser.mjs');
 const pack=await loadRecords();
 const rows=await Promise.all([{kind:'name',key:'Whisper',en:'Whisper'},{kind:'ui',key:'Susurro',en:'Whisper'},{kind:'ui',key:'Susurrar',en:'Whisper'}].map(identify));
 const result=buildScanDictionary(rows,[],pack);
 assert.equal(result.hasMissing,false);
 assert.equal(result.dictionary.Whisper,'위스퍼');
 assert.equal(result.dictionary.Susurro,'귓속말');
 assert.equal(result.dictionary.Susurrar,'귓속말');
 assert.equal(await createWikiTranslator(wikiTranslationLookup(pack))('Whisper'),'위스퍼');
});
