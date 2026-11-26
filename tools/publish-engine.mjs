import {readFile,writeFile,mkdir} from 'node:fs/promises';
import {resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
import {compareTranslationVersions} from '../src/session.mjs';

function engineVersion(meta){
  const matches=[...meta.matchAll(/^\/\/ @version (\d+\.\d+\.\d+)$/gm)];
  if(matches.length!==1)throw Error('Invalid engine version metadata');
  return matches[0][1];
}
export function shouldPublishEngine({meta,script},previousMeta=null){
  const version=engineVersion(meta);
  if(!script.startsWith(meta)||!meta.includes('// @updateURL https://raw.githubusercontent.com/si0dev/RO-Survivors-Korean/translation-data/ro-ko.meta.js\n')||!meta.includes('// @downloadURL https://raw.githubusercontent.com/si0dev/RO-Survivors-Korean/translation-data/ro-ko.user.js\n'))throw Error('Invalid engine publication');
  if(previousMeta===null)return true;
  const order=compareTranslationVersions(version,engineVersion(previousMeta));
  if(order<0)throw Error('Engine version decreased');
  return order>0;
}
async function main(){
  const meta=await readFile('dist/ro-ko.meta.js','utf8');
  const script=await readFile('dist/ro-ko.user.js','utf8');
  const previousMeta=process.argv[2]?await readFile(process.argv[2],'utf8'):null;
  if(!shouldPublishEngine({meta,script},previousMeta)){
    console.log('Engine unchanged; keep published script.');
    return;
  }
  await mkdir('dist/published',{recursive:true});
  await writeFile('dist/published/ro-ko.meta.js',meta);
  await writeFile('dist/published/ro-ko.user.js',script);
  console.log('Publishing engine '+engineVersion(meta));
}
if(process.argv[1]&&import.meta.url===pathToFileURL(resolve(process.argv[1])).href)await main();
