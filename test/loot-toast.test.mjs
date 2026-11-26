import test from 'node:test';
import assert from 'node:assert/strict';
import {translateLootToast} from '../src/language-adapter.mjs';

const toast = {matches: selector => selector === '#toasts > .toast.q'};
const other = {matches: () => false};
const grades = [
  ['Común','Common','일반'],
  ['Poco común','Uncommon','고급'],
  ['Raro','Rare','희귀'],
  ['Épico','Epic','영웅'],
  ['Legendario','Legendary','전설']
];
const dictionary = new Map(grades.flatMap(([es,en,ko])=>[[es,ko],[en,ko]]).concat([['Sword','소드'],['Knife','나이프']]));
const lookup = value => dictionary.get(value);
const translate = value => lookup(value) ?? value;
const apply = (value,parent=toast) => translateLootToast(value,parent,lookup,translate);

test('gear pickup toast translates all five qualities and existing item names',()=>{
  for(const [es,en,ko] of grades) for(const prefix of [es,en,ko]){
    assert.equal(apply(prefix+': Sword'),ko+': 소드');
    assert.equal(apply(prefix+': Knife'),ko+': 나이프');
  }
});
test('gear pickup toast preserves punctuation, spacing, unknown items and translated text',()=>{
  assert.equal(apply('  Rare:  Sword  '),'  희귀:  소드  ');
  assert.equal(apply('Legendary: Unknown item'),'전설: Unknown item');
  assert.equal(apply('일반: 소드'),'일반: 소드');
  assert.equal(apply('Common: Sword: variant'),'일반: Sword: variant');
});
test('non-gear toasts and unrelated elements are untouched',()=>{
  for(const value of ['Common: Sword','일반: Sword']) assert.equal(apply(value,other),value);
  for(const value of ['System: Sword','¡Sword!','Common','Common: ','Common:']) assert.equal(apply(value),value);
  assert.equal(apply(null),null);
});
