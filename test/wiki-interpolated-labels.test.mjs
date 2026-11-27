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
