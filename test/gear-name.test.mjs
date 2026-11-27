import test from 'node:test';
import assert from 'node:assert/strict';
import {createGearNameTranslator,isGearNameElement} from '../src/language-adapter.mjs';
import {buildScanDictionary} from '../src/browser.mjs';
import {identify} from '../src/core.mjs';

test('inventory gear composition uses verified names and preserves refine and unknown affixes',async()=>{
  const rows=await Promise.all(['Adventurer Suit','Sword','Sword Mace','Tidal Shoes'].map(key=>identify({kind:'name',key,en:key})));
  const ko=['어드밴쳐러 슈츠','소드','소드 메이스','타이달 슈즈'];
  const entries=Object.fromEntries(rows.map((r,i)=>[r.id,{sourceHash:r.sourceHash,ko:ko[i],placeholders:[]}]));
  const scan=buildScanDictionary(rows,[],{entries});
  const translate=createGearNameTranslator(scan.nameDictionary,s=>({'of Power':'힘의'}[s]));
  assert.equal(translate('Adventurer Suit of Power'),'어드밴쳐러 슈츠 힘의');
  assert.equal(translate('+7 Sword Mace of Power'),'+7 소드 메이스 힘의');
  assert.equal(translate('  +9 Tidal Shoes Unknown affix  '),'  +9 타이달 슈즈 Unknown affix  ');
  assert.equal(translate('Sword'),'소드');
  assert.equal(translate('Swordfish Unknown affix'),'Swordfish Unknown affix');
  assert.equal(translate('+7 소드 메이스 힘의'),'+7 소드 메이스 힘의');
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
