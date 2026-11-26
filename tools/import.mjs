import {readFile} from 'node:fs/promises';
import {identify,placeholders,samePlaceholders} from '../src/core.mjs';
const file=process.argv[2],version=process.argv[3];if(!file||!version)throw Error('Usage: node tools/import.mjs private/worklist.json NEW_VERSION');
import {loadParts,saveParts} from './records.mjs';
const work=JSON.parse(await readFile(file,'utf8'));
const {base,extra}=await loadParts();
const data=extra;
if(data.version===version)throw Error('Bump translation version');
let count=0;const approvedRows=[];
for(const row of work.rows){
  if(row.approved!==true)continue;
  const r=await identify(row);
  if(r.id!==row.id||r.sourceHash!==row.sourceHash||typeof r.ko!=='string'||!r.ko.trim()||!samePlaceholders(r.en??r.key,r.ko))throw Error('Invalid approved row: '+r.id);
  const target=Object.hasOwn(base.entries,r.id)?base:extra;
  const record={...target.entries[r.id],sourceHash:r.sourceHash,ko:r.ko,placeholders:placeholders(r.en??r.key)};
  if(r.kind==='wiki')record.scope='wiki';
  target.entries[r.id]=record;
  // One logical ID may have two original positions. Keep both views identical.
  if(Object.hasOwn(base.entries,r.id)&&Object.hasOwn(extra.entries,r.id))extra.entries[r.id]=record;
  approvedRows.push(r);count++;
}
if(!count)throw Error('No approved translations');
data.version=version;data.gameBuild=work.build;
await saveParts(base,extra,approvedRows);console.log('Imported '+count+' approved translations');
