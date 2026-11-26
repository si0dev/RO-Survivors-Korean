import {readFile,writeFile} from 'node:fs/promises';
import {join} from 'node:path';
import {validateRecords} from '../src/core.mjs';

// Management-only catalog. Runtime output retains the original schema and order.
const fileNames=["game-talents-fixed","game-talents-variable-a","game-talents-variable-b","wiki-fixed","wiki-variable","news"];
const stableLabels=new Set(["로그인","로그아웃","캐릭터 선택","캐릭터 생성","캐릭터 변경","설정","⚙ 설정","한국어","영어","스페인어","일본어","중국어","포르투갈어","저장","취소","닫기","확인","다음","이전","뒤로","검색","위키","특성 트리","스테이터스","스탯","근거리 공격력","원거리 공격력","마법 공격력","공격력","방어력","마법 방어력","명중률","회피율","캐스팅 속도","캐스팅 시간","전투 레벨","최고 전투 레벨","남성","여성","♀ 여성","♂ 남성","직업","지역","맵","던전","장비","카드","아이템","펫","몬스터","보스","파티","창고","상점","도움말","나가기","가방","재화","속성","종족","크기","등급","중립","화속성","수속성","풍속성","지속성","성속성","암속성","독속성","불사속성","염속성","스턴","동빙","출혈","침묵","실명","크리티컬","피해량","회복량","최대 HP","최대 SP","범위","공격 속도","이동 속도","재사용 대기시간","지속시간","발동 확률","스턴 확률","제니","STR","AGI","VIT","INT","DEX","LUK"]);
const reasons=new Set(["history-news","history-name","stable-label","effect-or-condition","insufficient-context","same-named-source","import-news","import-name"]);

function check(condition,message){if(!condition)throw Error(message);}

function same(a,b){return JSON.stringify(a)===JSON.stringify(b);}

function plain(value){return value!==null&&typeof value==="object"&&!Array.isArray(value);}

export function classifyNew(record,row){
 if(row?.kind==="news")return {type:"news",reason:"import-news"};
 if(row?.kind==="name")return {type:"fixed",reason:"import-name"};
 if(stableLabels.has(record.ko.trim())&&!record.placeholders.length)return {type:"fixed",reason:"stable-label"};
 if(record.placeholders.length||(/피해량|회복량|확률|지속시간|재사용 대기시간|충전|발동|획득|소모|해금|조건|보상|제한|증가|감소|적용|효과|처치|공격|시전/.test(record.ko)&&/합니다|됩니다|증가|감소|[+%×]|할 때|이상|이하|마다|동안|조건|필요|소모|제한/.test(record.ko)))return {type:"variable",reason:"effect-or-condition"};
 return {type:"variable",reason:"insufficient-context"};
}

function partition(id,record,type){
 check(["fixed","variable","news"].includes(type),"Invalid translation type: "+id);
 check(record.scope===undefined||record.scope==="wiki","Unsupported translation scope: "+id);
 if(type==="news"){check(record.scope===undefined,"News cannot have wiki scope: "+id);return "news";}
 if(record.scope==="wiki")return "wiki-"+type;
 return type==="fixed"?"game-talents-fixed":"game-talents-variable-"+(parseInt(id[0],16)<8?"a":"b");
}

export function mergeRecords(base,extra){
 return validateRecords({...base,version:extra.version,gameBuild:extra.gameBuild,entries:{...extra.entries,...base.entries}});
}

export function expandCatalog(catalog,files,common){
 check(catalog?.schema===1&&plain(catalog.parts?.base)&&plain(catalog.parts?.extra)&&!Object.hasOwn(catalog.parts.base,"entries")&&!Object.hasOwn(catalog.parts.extra,"entries"),"Invalid catalog metadata");
 check(plain(common)&&plain(files)&&same(Object.keys(files).sort(),[...fileNames].sort()),"Invalid catalog files");
 const count=fileNames.reduce((n,name)=>{check(plain(files[name]),"Invalid catalog partition "+name);return n+Object.keys(files[name]).length;},0);
 const slots=[[],[]],decisions={},refs={},members=new Map(),seen=new Set();
 for(const name of fileNames)for(const [id,item] of Object.entries(files[name])){
  check(/^[a-f0-9]{64}$/.test(id)&&!seen.has(id)&&plain(item)&&plain(item.record),"Invalid or duplicate catalog ID: "+id);seen.add(id);
  const {positions,type,reason,record}=item;
  check(reasons.has(reason)&&partition(id,record,type)===name,"Incorrect classification: "+id);
  check(Array.isArray(positions)&&positions.length===2&&positions.some(p=>p!==null),"Missing original position: "+id);
  let value=record;
  if(typeof record.ko!=="string"){
   const pointer=record.ko;
   check(plain(pointer)&&same(Object.keys(pointer),["ref"])&&typeof pointer.ref==="string"&&Object.hasOwn(common,pointer.ref),"Invalid common reference: "+id);
   const c=common[pointer.ref];
   check(plain(c)&&c.sourceHash===record.sourceHash&&same(c.placeholders,record.placeholders)&&typeof c.ko==="string"&&typeof c.reason==="string"&&c.reason.length>0,"Common source mismatch: "+id);
   value={...record,ko:c.ko};refs[id]=pointer.ref;
   if(!members.has(pointer.ref))members.set(pointer.ref,[]);
   members.get(pointer.ref).push(value.scope??"game-talents");
  }
  decisions[id]={type,reason};
  positions.forEach((p,i)=>{if(p===null)return;check(Number.isInteger(p)&&p>=0&&p<count&&!Object.hasOwn(slots[i],p),"Invalid or duplicate original position: "+id);slots[i][p]=[id,value];});
 }
 for(const id of Object.keys(common)){
  const uses=members.get(id);
  check(/^[a-f0-9]{64}$/.test(id)&&uses?.length>=2&&new Set(uses).size>=2,"Unused or non-shared common translation: "+id);
 }
 for(const slot of slots)for(let i=0;i<slot.length;i++)check(Object.hasOwn(slot,i),"Missing original position "+i);
 const base=validateRecords({...catalog.parts.base,entries:Object.fromEntries(slots[0])});
 const extra=validateRecords({...catalog.parts.extra,entries:Object.fromEntries(slots[1])});
 return {base,extra,decisions,refs,common};
}

export function buildCatalog(base,extra,decisions,common={},refs={}){
 validateRecords(base);validateRecords(extra);
 const {entries:b,...bm}=base,{entries:e,...em}=extra;
 const bp=new Map(Object.keys(b).map((id,i)=>[id,i])),ep=new Map(Object.keys(e).map((id,i)=>[id,i]));
 const files=Object.fromEntries(fileNames.map(name=>[name,{}]));
 const entries=mergeRecords(base,extra).entries;
 for(const id of Object.keys(refs))check(Object.hasOwn(entries,id),"Reference without record: "+id);
 for(const [id,v] of Object.entries(entries)){
  if(bp.has(id)&&ep.has(id))check(same(b[id],e[id]),"Conflicting duplicate ID: "+id);
  const d=decisions[id];
  check(d&&reasons.has(d.reason),"Missing classification: "+id);
  const ref=refs[id];
  if(ref!==undefined)check(Object.hasOwn(common,ref)&&common[ref].ko===v.ko,"Common translation value mismatch: "+id);
  files[partition(id,v,d.type)][id]={positions:[bp.get(id)??null,ep.get(id)??null],type:d.type,reason:d.reason,record:ref===undefined?v:{...v,ko:{ref}}};
 }
 const catalog={schema:1,parts:{base:bm,extra:em}};
 const expanded=expandCatalog(catalog,files,common);
 check(same(expanded.base,base)&&same(expanded.extra,extra),"Catalog roundtrip changed translation data");
 return {catalog,files,common};
}

export function rebuildCatalog(base,extra,previous,rows=[]){
 const incoming=new Map(rows.map(row=>[row.id,row]));
 const old=mergeRecords(previous.base,previous.extra).entries;
 const current=mergeRecords(base,extra).entries;
 const decisions={},common={},refs={},groups=new Map();
 for(const [id,v] of Object.entries(current)){
  decisions[id]=old[id]?.sourceHash===v.sourceHash?previous.decisions[id]:classifyNew(v,incoming.get(id));
  const ref=previous.refs[id],c=previous.common[ref];
  if(c&&c.sourceHash===v.sourceHash&&c.ko===v.ko&&same(c.placeholders,v.placeholders)){
   if(!groups.has(ref))groups.set(ref,[]);
   groups.get(ref).push(id);
  }
 }
 for(const ref of Object.keys(previous.common)){
  const ids=groups.get(ref)??[];
  if(ids.length<2||new Set(ids.map(id=>current[id].scope??"game-talents")).size<2)continue;
  common[ref]=previous.common[ref];for(const id of ids)refs[id]=ref;
 }
 return buildCatalog(base,extra,decisions,common,refs);
}

export async function loadCatalog(directory='translations'){
 const read=async name=>JSON.parse(await readFile(join(directory,name+'.json'),'utf8'));
 const [catalog,common,...parts]=await Promise.all(['catalog','common',...fileNames].map(read));
 return expandCatalog(catalog,Object.fromEntries(fileNames.map((name,i)=>[name,parts[i]])),common);
}
export async function loadParts(){
 const {base,extra}=await loadCatalog();return {base,extra};
}
export async function loadRecords(){
 const {base,extra}=await loadParts();return mergeRecords(base,extra);
}
function formatManagementFile(name,data){
 if(name==='catalog')return JSON.stringify(data,null,2)+'\n';
 const lines=Object.entries(data).map(([id,item])=>'  '+JSON.stringify(id)+': '+JSON.stringify(item));
 return lines.length?'{\n'+lines.join(',\n')+'\n}\n':'{}\n';
}

export async function saveParts(base,extra,rows=[],directory='translations'){
 const previous=await loadCatalog(directory);
 const {catalog,files,common}=rebuildCatalog(base,extra,previous,rows);
 const output={catalog,common,...files};
 for(const [name,data] of Object.entries(output))await writeFile(join(directory,name+'.json'),formatManagementFile(name,data));
}
