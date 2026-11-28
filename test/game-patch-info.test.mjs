import test from 'node:test';
import assert from 'node:assert/strict';
import {gamePatchInfoBottom,bindGamePatchInfo} from '../src/browser.mjs';

const view={innerHeight:800,getComputedStyle:pad=>pad.css??{display:'block',visibility:'visible'}};
const element=(rect,extra={})=>({hidden:false,classList:{contains:()=>false},getBoundingClientRect:()=>rect,...extra});
const visiblePad=()=>element({top:760,bottom:790,width:420,height:30});
test('controller hints offset the footer and hidden or absent hints do not',()=>{
  assert.equal(gamePatchInfoBottom(null,view),8);
  assert.equal(gamePatchInfoBottom(visiblePad(),view),46);
  assert.equal(gamePatchInfoBottom(element({}, {hidden:true}),view),8);
  assert.equal(gamePatchInfoBottom(element({}, {classList:{contains:()=>true}}),view),8);
  assert.equal(gamePatchInfoBottom(element({}, {css:{display:'none'}}),view),8);
  assert.equal(gamePatchInfoBottom(element({}, {css:{visibility:'hidden'}}),view),8);
  assert.equal(gamePatchInfoBottom(element({top:800,bottom:800,width:0,height:0}),view),8);
});
test('footer responds to screen transitions, dynamic pad hints and resize',()=>{
  const observers=[];
  class Observer{
    constructor(callback){this.callback=callback;observers.push(this);}
    observe(target){this.target=target;}
    disconnect(){this.target=null;}
  }
  const screens=Object.fromEntries(['splash','charselect','lobby-ui','hud'].map(id=>[id,element({}, {hidden:true})]));
  const body={};
  let pad=null,onResize;
  const doc={body,defaultView:{...view,MutationObserver:Observer,ResizeObserver:Observer,addEventListener:(_,fn)=>{onResize=fn;}},getElementById:id=>id==='pad-hints'?pad:screens[id]};
  const footer={style:{}};
  bindGamePatchInfo(footer,doc,'/');
  assert.equal(footer.style.display,'none');
  screens['lobby-ui'].hidden=false;
  observers[2].callback();
  assert.equal(footer.style.display,'block');
  assert.equal(footer.style.bottom,'8px');
  pad=visiblePad();
  observers[3].callback();
  assert.equal(footer.style.bottom,'46px');
  pad.hidden=true;
  observers[1].callback();
  assert.equal(footer.style.bottom,'8px');
  pad.hidden=false;
  pad.getBoundingClientRect=()=>({top:730,bottom:790,width:420,height:60});
  observers[0].callback();
  assert.equal(footer.style.bottom,'76px');
  screens['lobby-ui'].hidden=true;
  screens.hud.hidden=false;
  onResize();
  assert.equal(footer.style.display,'block');
  pad=null;
  observers[3].callback();
  assert.equal(footer.style.bottom,'8px');
  screens.charselect.hidden=false;
  observers[2].callback();
  assert.equal(footer.style.display,'none');
});
