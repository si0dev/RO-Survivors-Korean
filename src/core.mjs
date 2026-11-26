// Read static string maps without executing game JavaScript.
const ident = '[A-Za-z_$][\\w$]*';
const escapeRegExp = s => s.replace(/[.*+?^$\x7b\x7d()|[\]\\]/g, '\\$&');
function decodeString(token) {
  return token.slice(1,-1).replace(/\\(?:u\{[\da-fA-F]+\}|u[\da-fA-F]{4}|x[\da-fA-F]{2}|\r\n|[\s\S])/g, esc=>{
    const body=esc.slice(1);
    if(body.startsWith('u{'))return String.fromCodePoint(parseInt(body.slice(2,-1),16));
    if(/^[ux][\da-fA-F]+$/.test(body))return String.fromCharCode(parseInt(body.slice(1),16));
    if(body==='\r\n'||body==='\n'||body==='\r')return '';
    return ({n:'\n',r:'\r',t:'\t',b:'\b',f:'\f',v:'\v','0':'\0'})[body]??body;
  });
}
export function readMap(code, start) {
  const tok = /\s*(?:"(?:\\[\s\S]|[^"\\])*"|'(?:\\[\s\S]|[^'\\])*'|[$_\p{ID_Start}][$\p{ID_Continue}]*|[{}:,])/uy;
  tok.lastIndex = start;
  function next() {
    const pos = tok.lastIndex;
    const m = tok.exec(code);
    if (!m) throw Error('Unsupported static map syntax at '+pos);
    return m[0].trim();
  }
  const result = Object.create(null);
  if (next() !== '{') throw Error('Expected map');
  let key = next();
  while (key !== '}') {
    if (/^["']/.test(key)) key = decodeString(key);
    else if (!/^[$_\p{ID_Start}][$\p{ID_Continue}]*$/u.test(key)) throw Error('Invalid key');
    if (next() !== ':') throw Error('Expected colon');
    const value = next();
    if (!/^["']/.test(value)) throw Error('Expected string value');
    result[key] = decodeString(value);
    const sep = next();
    if (sep === '}') break;
    if (sep !== ',') throw Error('Expected comma');
    key = next();
  }
  return {map:result,end:tok.lastIndex};
}
function findMap(code,id) {
  const re = new RegExp('(?:\\bconst\\s+|\\blet\\s+|\\bvar\\s+|,)'+escapeRegExp(id)+'\\s*=\\s*\\{','g');
  for (const m of code.matchAll(re)) {
    try {
      const parsed = readMap(code,m.index+m[0].lastIndexOf('{'));
      if (Object.keys(parsed.map).length >= 100) return parsed;
    } catch {}
  }
  throw Error('Language map not found: '+id);
}
// Read the latest published English news without running the game bundle.
export function readNewsReleases(files) {
  const matches=[];
  for(const {content:code} of files){
    if(typeof code!=='string')continue;
    for(const match of code.matchAll(/=\s*(`(?:\\[\s\S]|[^\\`])*`)/g)){
      const token=match[1];
      if(!token.startsWith('`# Changelog')||!token.includes('English version of CHANGELOG.md'))continue;
      if(/(?<!\\)\$\{/.test(token))throw Error('Dynamic news source');
      matches.push(decodeString(token));
    }
  }
  if(matches.length!==1)throw Error('English news source not found or ambiguous');
  const releases=[];
  let title=null, parts=[], bullet=null, inList=false;
  const add=source=>{
    // The game's renderer wraps inline code and bold in separate text nodes.
    for(const part of source.split(/`([^`]+)`|\*\*([^*]+)\*\*/g)){
      const value=part?.replace(/\s+/g,' ').trim();
      if(value&&/\p{L}/u.test(value))parts.push(value);
    }
  };
  const flush=()=>{if(bullet!==null){const tag=/^\[([^\]]+)\]\s*/.exec(bullet);if(tag){add(tag[1]);add(bullet.slice(tag[0].length));}else add(bullet);bullet=null;}};
  const finish=()=>{flush();if(title&&!/^(unreleased|for the next push|sin publicar|para el siguiente push|未發布|下次推送)$/i.test(title)){releases.push({title,rows:[...new Set(parts)].map(key=>({kind:'news',key,en:key}))});}title=null;parts=[];inList=false;};
  for(const line of matches[0].split(/\r?\n/)){
    const d=line.trimEnd();
    if(d.startsWith('## ')){finish();title=d.slice(3).trim();add(title);continue;}
    if(!title)continue;
    if(d.startsWith('### ')){flush();inList=false;add(d.slice(4).trim());}
    else if(d.startsWith('- ')){flush();inList=true;bullet=d.slice(2).trim();}
    else if(bullet!==null&&/^\s+\S/.test(line))bullet+=' '+d.trim();
    else if(d.trim()){if(!inList)add(d.trim());}
    else flush();
  }
  finish();
  if(!releases.length||releases[0].rows.length<2)throw Error('No published news');
  return releases;
}
export function extractSnapshot(files) {
  const js=files.filter(f=>/\.m?js$/i.test(new URL(f.url).pathname) && typeof f.content==='string');
  const builds=new Set(js.map(f=>f.content.match(/RO Survivors[^*\n]*?Build\s+([0-9a-f]{7,64})\b/i)?.[1]).filter(Boolean));
  if(builds.size!==1) throw Error('Game build absent or inconsistent');
  for (const {content:code} of js) {
    const m=code.match(new RegExp('\\bes\\s*:\\s*null\\s*,\\s*en\\s*:\\s*('+ident+')\\s*,\\s*"zh-TW"\\s*:\\s*('+ident+')\\s*,\\s*"pt-BR"\\s*:\\s*('+ident+')\\s*,\\s*ja\\s*:\\s*('+ident+')'));
    if (!m) continue;
    const maps=m.slice(1).map(id=>findMap(code,id));
    const keys=new Set(maps.flatMap(x=>Object.keys(x.map)));
    const ui=[...keys].sort().map(key=>({kind:'ui',key,en:maps[0].map[key]??null}));
    // MATK is a literal status label outside the shared language table.
    if(!keys.has('MATK')&&js.some(({content})=>/\[\s*"MATK"\s*,/.test(content)))ui.push({kind:'ui',key:'MATK',en:'MATK'});
    const names=new Set();
    for(const map of maps){
      const following=code.slice(map.end,map.end+100).match(new RegExp('^\\s*,\\s*'+ident+'\\s*=\\s*\\{'));
      if(!following) throw Error('Adjacent name map not found');
      const next=readMap(code,map.end+following[0].lastIndexOf('{'));
      if(Object.keys(next.map).length<100) throw Error('Unexpected name map size');
      for(const key of Object.keys(next.map)) names.add(key);
    }
    // These are additional static names, not a complete item/monster inventory.
    for(const m of code.matchAll(/\b[A-Za-z_$][\w$]*\(\{id:"([^"]+)",name:"([^"]+)"/g)) names.add(m[2]);
    // The resource manifest contains the original item and card names.
    for(const f of files){
      if(!/\/manifest\.json$/i.test(new URL(f.url).pathname)) continue;
      const manifest=JSON.parse(f.content);
      for(const section of [manifest.items,manifest.cards]){
        for(const item of Object.values(section??{})) if(typeof item?.name==='string') names.add(item.name);
      }
    }
    let latestNews=[],newsHistory=[],newsRelease=null,newsScanFailed=false;
    try {
      const releases=readNewsReleases(js);
      newsRelease=releases[0].title;
      latestNews=releases[0].rows;
      const latestKeys=new Set(latestNews.map(row=>row.key));
      newsHistory=[...new Map(releases.slice(1).flatMap(release=>release.rows).filter(row=>!latestKeys.has(row.key)).map(row=>[row.key,row])).values()];
    } catch {newsScanFailed=true;}
    return {build:[...builds][0],rows:[...ui,...[...names].sort().map(key=>({kind:'name',key,en:key})),...latestNews],newsHistory,newsRelease,newsScanFailed};
  }
  throw Error('Unsupported game language-table layout');
}
export async function sha256(value){
  const bytes=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(value));
  return Array.from(new Uint8Array(bytes),b=>b.toString(16).padStart(2,'0')).join('');
}
export const placeholders = s => [...s.matchAll(/\{\w+\}/g)].map(x=>x[0]).sort();
export const samePlaceholders = (a,b)=>JSON.stringify(placeholders(a))===JSON.stringify(placeholders(b));
export async function identify(row) {
  const source=row.en??row.key;
  return {...row,id:await sha256(row.kind+'\0'+row.key),sourceHash:await sha256(source)};
}
export async function worklist(snapshot, records={}) {
  return Promise.all(snapshot.rows.map(async row=>{
    const r=await identify(row),old=records[r.id];
    const status=old?(old.sourceHash===r.sourceHash?'translated':'changed'):'missing';
    const draft=old?.ko??'';
    return {...r,status,ko:draft,approved:status==='translated'};
  }));
}
export function compare(rows, records) {
  let missing=0,changed=0;
  for(const row of rows){
    const entry=records[row.id];
    if(!entry) missing++;
    else if(entry.sourceHash!==row.sourceHash) changed++;
  }
  return {missing,changed,hasMissing:missing+changed>0};
}
export function validateRecords(data){
  if(data?.schema!==1||typeof data.version!=='string'||!data.entries||Array.isArray(data.entries)||typeof data.entries!=='object')throw Error('Invalid dictionary');
  for(const [key,v] of Object.entries(data.entries)){
    if(!/^[a-f0-9]{64}$/.test(key)||!v||! /^[a-f0-9]{64}$/.test(v.sourceHash)||typeof v.ko!=='string'||!v.ko.trim()||!Array.isArray(v.placeholders)||JSON.stringify(placeholders(v.ko))!==JSON.stringify(v.placeholders)) throw Error('Invalid translation: '+key);
  }
  return data;
}

 // Wiki strings are separate from the game's shared language table. Store only
 // the source hash and translated value; do not publish the raw source dump.
export function wikiTranslationLookup(pack){
  const result=Object.create(null);
  for(const entry of Object.values(pack?.entries??{})){
    if(entry.scope==='wiki')result[entry.sourceHash]=entry.ko;
  }
  return result;
}
export function createWikiTranslator(entries){
  const cache=new Map();
  return async value=>{
    if(typeof value!=='string'||!value.trim())return undefined;
    const normalized=value.trim().replace(/\s+/g,' ');
    if(!cache.has(normalized)){
      if(cache.size>=4096)cache.clear();
      cache.set(normalized,sha256(normalized).then(hash=>Object.hasOwn(entries,hash)?entries[hash]:undefined));
    }
    return cache.get(normalized);
  };
}
