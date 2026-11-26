import {readFile,writeFile,mkdir} from 'node:fs/promises';
import {resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
import {sha256,validateRecords} from '../src/core.mjs';
import {compareTranslationVersions} from '../src/session.mjs';

const payload = ({version,...data})=>JSON.stringify(data);
export async function preparePublication(pack,previous=null){
  validateRecords(pack);
  const sourceHash=await sha256(payload(pack));
  if(previous){
    const {raw,manifest}=previous;
    const old=validateRecords(JSON.parse(raw));
    if(manifest.schema!==1||manifest.file!=='ko.json'||manifest.translationVersion!==old.version||manifest.translationHash!==await sha256(raw))throw Error('Invalid previous publication');
    if(await sha256(payload(old))===sourceHash)return {raw,manifest,changed:false};
    if(Object.keys(pack.entries).length<Object.keys(old.entries).length)throw Error('Translation record count decreased');
  }
  let version='0.4.0';
  if(previous){
    const m=/^(\d+)\.(\d+)\.(\d+)$/.exec(previous.manifest.translationVersion);
    if(!m)throw Error('Invalid previous publication version');
    version=m[1]+'.'+m[2]+'.'+(Number(m[3])+1);
  }
  if(compareTranslationVersions(pack.version,version)>0){
    if(!/^\d+\.\d+\.\d+$/.test(pack.version))throw Error('Publication requires stable data version');
    version=pack.version;
  }
  const published={...pack,version};
  const raw=JSON.stringify(published);
  const manifest={schema:1,translationVersion:version,gameBuild:pack.gameBuild,translationHash:await sha256(raw),file:'ko.json'};
  return {raw,manifest,changed:true};
}
async function main(){
  const previousDir=process.argv[2];
  const pack=JSON.parse(await readFile('dist/ko.json','utf8'));
  const previous=previousDir?{raw:await readFile(resolve(previousDir,'ko.json'),'utf8'),manifest:JSON.parse(await readFile(resolve(previousDir,'manifest.json'),'utf8'))}:null;
  const result=await preparePublication(pack,previous);
  await mkdir('dist/published',{recursive:true});
  await writeFile('dist/published/ko.json',result.raw);
  await writeFile('dist/published/manifest.json',JSON.stringify(result.manifest,null,2)+'\n');
  console.log((result.changed?'Updated':'Unchanged')+' translation '+result.manifest.translationVersion);
}
if(process.argv[1]&&import.meta.url===pathToFileURL(resolve(process.argv[1])).href)await main();
