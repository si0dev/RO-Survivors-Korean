import test from 'node:test';
import assert from 'node:assert/strict';
import {createGearScoreTooltip} from '../src/language-adapter.mjs';

function element(value,title=null){
  return {
    nodeType:1,textContent:value,childNodes:[{nodeType:3,nodeValue:value}],
    getAttribute:()=>title,setAttribute:(_,v)=>{title=v;},removeAttribute:()=>{title=null;}
  };
}
test('GS labels retain their text and get a Korean native tooltip',()=>{
  const sync=createGearScoreTooltip();
  for(const text of ['GS','GS 123','GS: 1,234',' GS 42 ']){
    const el=element(text);sync(el);sync(el);
    assert.equal(el.getAttribute('title'),'장비 점수');
    assert.equal(el.textContent,text);
    sync(el,false);
    assert.equal(el.getAttribute('title'),null);
  }
});
test('unrelated text and existing game tooltips are untouched',()=>{
  const sync=createGearScoreTooltip();
  for(const text of ['장비 점수','AGS','GS bonus','Sword GS 10','GS: unknown']){
    const el=element(text);sync(el);assert.equal(el.getAttribute('title'),null);
  }
  const el=element('GS 42','Original tooltip');sync(el);sync(el,false);
  assert.equal(el.getAttribute('title'),'Original tooltip');
});
test('reused elements lose only the tooltip added by the patch',()=>{
  const sync=createGearScoreTooltip();
  const el=element('GS');sync(el);
  el.textContent='ATK';el.childNodes[0].nodeValue='ATK';sync(el);
  assert.equal(el.getAttribute('title'),null);
  el.textContent='GS';el.childNodes[0].nodeValue='GS';sync(el);
  el.setAttribute('title','New game tooltip');sync(el,false);
  assert.equal(el.getAttribute('title'),'New game tooltip');
});
