import test from 'node:test';
import assert from 'node:assert/strict';
import {engineNoticeText,patchStatusContent} from '../src/browser.mjs';
import {ENGINE_UPDATE_LABEL,stateLabel} from '../src/session.mjs';

test('initial notice, install instructions and retry link are available in both layouts',()=>{
  for(const inGame of [false,true])assert.deepEqual(engineNoticeText(false,inGame),{message:'',link:ENGINE_UPDATE_LABEL});
  assert.deepEqual(engineNoticeText(true,false),{message:'업데이트 설치 후 게임을 새로고침해 주세요.',link:'업데이트 설치 창 다시 열기'});
  assert.deepEqual(engineNoticeText(true,true),{message:'업데이트 설치 후 새로고침 (',link:'다시 설치',suffix:')'});
});
test('missing translations and failure use distinct labels',()=>{
  assert.equal(stateLabel({hasMissing:true}),'일부 콘텐츠는 번역이 반영될 때까지 원문으로 표시됩니다.');
  assert.equal(stateLabel({hasMissing:true,scanFailed:true}),'현재 한국어 패치의 최신 상태를 확인할 수 없습니다.');
});

function mockElement(tag){
  return {tag,style:{},children:[],textContent:'',append(...children){this.children.push(...children);},addEventListener(type,fn){this[type]=fn;}};
}
const doc={createElement:mockElement};
test('main and talents use separate block rows for version and status',()=>{
  for(const state of [{hasMissing:true},{scanFailed:true},{engineUpdated:true},{engineUpdateAvailable:true}]){
    const rows=patchStatusContent(doc,state,'1.2.3',false,false,()=>{});
    assert.equal(rows.length,2);
    assert.equal(rows[0].tag,'div');
    assert.equal(rows[0].textContent,'비공식 한국어 패치 / 엔진 v1.2.3');
    assert.equal(rows[1].tag,'div');
    assert.ok(rows[1].textContent||rows[1].children.length);
  }
});
test('install instructions retain two lines outside game and a single line in game',()=>{
  const state={engineUpdateAvailable:true};
  let clicks=0;
  const main=patchStatusContent(doc,state,'1.2.3',false,true,()=>{clicks++;});
  assert.equal(main[1].children[0].tag,'div');
  assert.equal(main[1].children[0].textContent,'업데이트 설치 후 게임을 새로고침해 주세요.');
  assert.equal(main[1].children[1].textContent,'업데이트 설치 창 다시 열기');
  main[1].children[1].click();
  assert.equal(clicks,1);
  const game=patchStatusContent(doc,state,'1.2.3',true,true,()=>{});
  assert.equal(game.length,1);
  assert.equal(game[0].tag,'span');
  assert.equal(game[0].children[1].textContent,'다시 설치');
});
