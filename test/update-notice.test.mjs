import test from 'node:test';
import assert from 'node:assert/strict';
import {engineNoticeText} from '../src/browser.mjs';
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
