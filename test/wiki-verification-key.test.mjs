import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {wikiRuntimeKey} from '../tools/wiki-verification-key.mjs';
const [browser,session,pkg,workflow]=await Promise.all(['src/browser.mjs','src/session.mjs','package.json','.github/workflows/extract-wiki.yml'].map(path=>readFile(new URL('../'+path,import.meta.url),'utf8')));
const key=wikiRuntimeKey(browser,session,pkg);
test('UI position, status text and engine version do not invalidate wiki cache',()=>{
  const uiMarker='// Keep status presentation separate from the translation session.';
  const labelMarker='export const ENGINE_UPDATE_LABEL=';
  assert.ok(browser.includes(uiMarker));
  assert.ok(session.includes(labelMarker));
  assert.equal(wikiRuntimeKey(browser.replace(uiMarker,uiMarker+'\n// presentation change'),session.replace(labelMarker,labelMarker+' /* label edit */ '),JSON.stringify({...JSON.parse(pkg),version:'99.0.0'})),key);
});
test('translation runtime, build configuration and unknown boundaries invalidate wiki cache',()=>{
  assert.notEqual(wikiRuntimeKey(browser+'\n// runtime edit',session,pkg),key);
  assert.notEqual(wikiRuntimeKey(browser,session.replace('async function poll(){','async function poll(){ /* changed */'),pkg),key);
  assert.notEqual(wikiRuntimeKey(browser,session,JSON.stringify({...JSON.parse(pkg),scripts:{test:'changed'}})),key);
  assert.notEqual(wikiRuntimeKey(browser.replace('// Keep status presentation separate from the translation session.','// moved boundary'),session,pkg),key);
});
test('UI files do not trigger immediate wiki extraction',()=>{
  const push=workflow.slice(workflow.indexOf('  push:'),workflow.indexOf('concurrency:'));
  assert.doesNotMatch(push,/src\/|package\.json|\.github\/workflows/);
  assert.match(push,/tools\/extract-wiki\.mjs/);
  assert.match(push,/translations\/wiki-fixed\.json/);
  assert.match(workflow,/cron: '0 2 \* \* \*'/);
  assert.match(workflow,/workflow_dispatch/);
});
