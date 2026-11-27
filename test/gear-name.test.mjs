import test from 'node:test';
import assert from 'node:assert/strict';
import {createGearNameTranslator,isGearNameElement} from '../src/language-adapter.mjs';
import {buildScanDictionary} from '../src/browser.mjs';
import {identify,extractSnapshot} from '../src/core.mjs';
import {loadRecords} from '../tools/records.mjs';

test('inventory gear composition uses verified names and preserves refine and unknown affixes',async()=>{
  const rows=await Promise.all(['Adventurer Suit','Sword','Sword Mace','Tidal Shoes','of Strength'].map(key=>identify({kind:'name',key,en:key})));
  const ko=['어드밴쳐러 슈츠','소드','소드 메이스','타이달 슈즈','힘의'];
  const entries=Object.fromEntries(rows.map((r,i)=>[r.id,{sourceHash:r.sourceHash,ko:ko[i],placeholders:[]}]));
  const scan=buildScanDictionary(rows,[],{entries});
  const translate=createGearNameTranslator(scan.nameDictionary);
  assert.equal(translate('Adventurer Suit of Strength'),'힘의 어드밴쳐러 슈츠');
  assert.equal(translate('+7 Sword Mace of Strength'),'+7 힘의 소드 메이스');
  assert.equal(translate('  +9 Tidal Shoes Unknown affix  '),'  +9 타이달 슈즈 Unknown affix  ');
  assert.equal(translate('Sword'),'소드');
  assert.equal(translate('+7 Sword of Strength [2]',true),'+7 힘의 소드 [2]');
  assert.equal(translate('Sword Unknown affix',true),'Sword Unknown affix');
  assert.equal(translate('Sword of Strength',true),'힘의 소드');
  assert.equal(translate('Swordfish Unknown affix'),'Swordfish Unknown affix');
  assert.equal(translate('+7 힘의 소드 메이스'),'+7 힘의 소드 메이스');
  assert.equal(translate('Unknown item of Power'),'Unknown item of Power');
});
test('name lookup excludes UI records and source hash mismatches',async()=>{
  const rows=await Promise.all([{kind:'name',key:'Sword',en:'Sword'},{kind:'ui',key:'Status',en:'Status'},{kind:'name',key:'Changed',en:'Changed'}].map(identify));
  const entries=Object.fromEntries(rows.map(r=>[r.id,{sourceHash:r.key==='Changed'?'old':r.sourceHash,ko:'번역',placeholders:[]}]));
  const scan=buildScanDictionary(rows,[],{entries});
  assert.deepEqual({...scan.nameDictionary},{Sword:'번역'});
});
test('composite name matching is restricted to inventory, gear details and item tooltip name elements',()=>{
  const selector='#cp-inventory [data-uid], .eq-name, .tip-item > div > b';
  assert.equal(isGearNameElement({closest:s=>s===selector?{}:null}),true);
  assert.equal(isGearNameElement({closest:()=>null}),false);
  assert.equal(isGearNameElement(null),false);
});

test('all six actual stat affixes are extracted and present in approved records',async()=>{
  const expected={'of Strength':'힘의','of Agility':'민첩의','of Vitality':'체력의','of Intelligence':'지능의','of Dexterity':'손재주의','of Luck':'행운의'};
  const map=JSON.stringify(Object.fromEntries(Array.from({length:100},(_,i)=>['k'+i,'v'+i])));
  const fixture='// RO Survivors Build 1234567\n'+['en','zh','pt','ja'].map(k=>'const '+k+'='+map+','+k+'Names='+map+';').join('\n')+'\nconst languages={es:null,en:en,"zh-TW":zh,"pt-BR":pt,ja:ja};';
  const affixes='const stats={'+Object.keys(expected).map((key,i)=>['str','agi','vit','int','dex','luk'][i]+':{bonus:x,suffix:'+JSON.stringify(key)+'}').join(',')+'};';
  const snapshot=extractSnapshot([{url:'https://example.test/main.js',content:fixture},{url:'https://example.test/shared.js',content:affixes}]);
  const rows=await Promise.all(snapshot.rows.filter(r=>Object.hasOwn(expected,r.key)).map(identify));
  assert.equal(rows.length,6);
  const pack=await loadRecords();
  const scan=buildScanDictionary(rows,[],pack);
  assert.deepEqual({...scan.nameDictionary},expected);
  const translate=createGearNameTranslator({...scan.nameDictionary,Sword:'소드'});
  for(const [en,ko] of Object.entries(expected)){
    assert.equal(translate('Sword '+en),ko+' 소드');
    assert.equal(translate('+10 Sword '+en),'+10 '+ko+' 소드');
  }
});
