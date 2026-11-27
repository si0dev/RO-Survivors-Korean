import test from 'node:test';
import assert from 'node:assert/strict';
import {createWikiTranslator,sha256} from '../src/core.mjs';

test('interpolated Korean labels require a verified full wiki hash',async()=>{
  const en='Use the «To chat» button.';
  const inventory='Select the «Only new» box.';
  const multiple='Select «To chat» or «Only new».';
  const entries={
    [await sha256(en)]:'채팅하기 버튼을 사용합니다.',
    [await sha256(inventory)]:'신규만 항목을 선택합니다.',
    [await sha256(multiple)]:'채팅하기 또는 신규만을 선택합니다.'
  };
  const translate=createWikiTranslator(entries,{'To chat':'채팅하기','Only new':'신규만','Chat':'채팅하기'});
  assert.equal(await translate(en),entries[await sha256(en)]);
  assert.equal(await translate('Use the «채팅하기» button.'),entries[await sha256(en)]);
  assert.equal(await translate('Select the «신규만» box.'),entries[await sha256(inventory)]);
  assert.equal(await translate('Select «채팅하기» or «신규만».'),entries[await sha256(multiple)]);
  assert.equal(await translate('Use the «채팅하기» button twice.'),undefined);
  assert.equal(await translate('Use the 채팅하기 button.'),undefined);
});
test('direct wiki hash wins; ambiguous reverse matches are rejected',async()=>{
  const a=await sha256('Use «Chat».');
  const b=await sha256('Use «To chat».');
  const mixed=await sha256('Use «채팅하기».');
  const labels={'Chat':'채팅하기','To chat':'채팅하기'};
  assert.equal(await createWikiTranslator({[a]:'A',[b]:'B'},labels)('Use «채팅하기».'),undefined);
  assert.equal(await createWikiTranslator({[a]:'A',[b]:'B',[mixed]:'C'},labels)('Use «채팅하기».'),'C');
});

test('native full translations and unquoted interpolated labels recover approved wiki strings',async()=>{
  const sources={
    'The knight keeps every Swordsman skill.':'나이트는 검사의 모든 스킬을 유지합니다.',
    'Bash Deity':'배쉬의 신',
    'HP/s +0.5 · Max HP +25':'초당 HP 회복 +0.5 · 최대 HP +25',
    'Taunts nearby enemies.':'주변 적을 도발합니다.'
  };
  const entries=Object.fromEntries(await Promise.all(Object.entries(sources).map(async ([en,ko])=>[await sha256(en),ko])));
  const translate=createWikiTranslator(entries,{'The knight':'나이트','Swordsman':'검사','Bash':'배쉬','HP/s':'초당 HP','Max HP':'최대 HP','Taunts nearby enemies.':'주변 적을 도발합니다!'});
  assert.equal(await translate('나이트 keeps every 검사 skill.'),sources['The knight keeps every Swordsman skill.']);
  assert.equal(await translate('배쉬 Deity'),sources['Bash Deity']);
  assert.equal(await translate('초당 HP +0.5 · 최대 HP +25'),sources['HP/s +0.5 · Max HP +25']);
  assert.equal(await translate('주변 적을 도발합니다!'),sources['Taunts nearby enemies.']);
  assert.equal(await translate('배쉬 Deity twice'),undefined);
  assert.equal(await translate('초당 HP +0.6 · 최대 HP +25'),undefined);
});
test('ambiguous complete native translations do not overwrite wiki text',async()=>{
  const a=await sha256('Armor'),b=await sha256('Body armor');
  const translate=createWikiTranslator({[a]:'방어력',[b]:'갑옷'},{Armor:'갑옷','Body armor':'갑옷'});
  assert.equal(await translate('갑옷'),undefined);
});
