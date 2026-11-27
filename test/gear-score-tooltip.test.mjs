import test from 'node:test';
import assert from 'node:assert/strict';
import {createGearScoreTooltip} from '../src/language-adapter.mjs';

function element(value,title=null,gs=true){
  return {
    nodeType:1,textContent:value,gs,childNodes:[],
    matches(selector){return selector==='.gs'&&this.gs;},
    getAttribute:()=>title,setAttribute:(_,v)=>{title=v;},removeAttribute:()=>{title=null;}
  };
}
test('actual .gs class is annotated regardless of text or nested elements',()=>{
  const sync=createGearScoreTooltip();
  for(const text of ['GS','GS 123','1,234','', 'GS: 42']){
    const el=element(text);sync(el);sync(el);
    assert.equal(el.getAttribute('title'),'장비 점수');
    assert.equal(el.textContent,text);
    sync(el,false);
    assert.equal(el.getAttribute('title'),null);
  }
});
test('other classes are untouched even if text is GS',()=>{
  const sync=createGearScoreTooltip();
  const el=element('GS 42','Original tooltip',false);sync(el);sync(el,false);
  assert.equal(el.getAttribute('title'),'Original tooltip');
  const bare=element('GS',null,false);sync(bare);
  assert.equal(bare.getAttribute('title'),null);
});
test('class changes and language switches restore original title',()=>{
  const sync=createGearScoreTooltip();
  for(const original of [null,'','Gear Score']){
    const el=element('42',original);sync(el);
    assert.equal(el.getAttribute('title'),'장비 점수');
    el.gs=false;sync(el);
    assert.equal(el.getAttribute('title'),original);
    el.gs=true;sync(el);sync(el,false);
    assert.equal(el.getAttribute('title'),original);
  }
});
test('a game title changed during Korean mode is restored when leaving',()=>{
  const sync=createGearScoreTooltip();
  const el=element('42','Gear Score');sync(el);
  el.setAttribute('title','New game tooltip');sync(el);sync(el,false);
  assert.equal(el.getAttribute('title'),'New game tooltip');
});
