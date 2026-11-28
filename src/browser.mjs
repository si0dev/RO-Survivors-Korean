import {extractSnapshot,identify,compare,sha256,validateRecords,wikiTranslationLookup} from './core.mjs';
import {createSession,UPDATE_INTERVAL_MS,TRANSLATION_CHECK_INTERVAL_MS,compareTranslationVersions,ENGINE_UPDATE_LABEL,createEngineUpdate,stateLabel} from './session.mjs';
import {installLanguageAdapter} from './language-adapter.mjs';

const STORAGE='ro-ko:v3:';
const DATA_URL='https://raw.githubusercontent.com/si0dev/RO-Survivors-Korean/translation-data/';
const memory=new Map();
function getSaved(key){
  if(memory.has(key))return memory.get(key);
  try{return JSON.parse(localStorage.getItem(STORAGE+key));}catch{return null;}
}
function setSaved(key,value){
  memory.set(key,value);
  try{localStorage.setItem(STORAGE+key,JSON.stringify(value));}catch{}
}
async function fetchText(url,cache='force-cache'){
  const controller=new AbortController();
  const timer=setTimeout(()=>controller.abort(),15000);
  try {
    const response=await fetch(url,{credentials:'omit',cache,signal:controller.signal});
    if(!response.ok)throw Error('HTTP '+response.status);
    return await response.text();
  } finally {clearTimeout(timer);}
}
// Keep status presentation separate from the translation session.
const STATUS_SCREENS=['splash','charselect','lobby-ui','hud'];
export function patchStatusPlacement(doc,pathname='/'){
  if(pageBundleType(pathname)==='talents')return {mode:'standalone'};
  const shown=id=>{
    const el=doc.getElementById(id);
    return !!el&&!el.hidden&&!el.classList.contains('hidden');
  };
  if(shown('charselect'))return {mode:'hidden'};
  if(shown('lobby-ui'))return {mode:'game',screen:doc.getElementById('lobby-ui')};
  if(shown('hud'))return {mode:'game',screen:doc.getElementById('hud')};
  if(!shown('splash'))return {mode:'hidden'};
  const splash=doc.getElementById('splash');
  // The game assigns its build label to #sp-version. Use that exact element
  // instead of matching its formatted text (which may include invisible marks).
  const anchor=doc.getElementById('sp-version');
  return anchor&&splash.contains(anchor)&&!anchor.closest('[hidden], .hidden')
    ?{mode:'panel',anchor}:{mode:'hidden'};
}
// Find the bottom of the visible, compact, top-centred game labels without
// relying on translated text or private game element IDs.
export function gameNoticeTop(screen,width,height){
  const center=width/2;
  const limit=Math.min(150,height*0.22);
  let bottom=0;
  for(const el of screen.querySelectorAll('*')){
    if(el.closest('[hidden], .hidden, #ro-ko-status')||!el.textContent?.trim())continue;
    const r=el.getBoundingClientRect();
    if(r.width<12||r.height<8||r.width>Math.min(420,width*0.58)||r.height>110)continue;
    if(r.top<0||r.bottom>limit||Math.abs((r.left+r.right)/2-center)>Math.max(18,Math.min(42,width*0.035)))continue;
    bottom=Math.max(bottom,r.bottom);
  }
  return Math.ceil(bottom?bottom+8:Math.min(80,height*0.15));
}
export function bindStatusPosition(node,doc=document,pathname=location.pathname){
  const sync=()=>{
    const {mode,anchor,screen}=patchStatusPlacement(doc,pathname);
    if(mode==='hidden'||(mode==='game'&&node.dataset.roKoNotice!=='true')){
      node.style.display='none';
      return;
    }
    if(mode==='panel'){
      if(anchor.nextElementSibling!==node)anchor.after(node);
      Object.assign(node.style,{display:'block',position:'static',left:'auto',top:'auto',transform:'none',right:'auto',bottom:'auto',zIndex:'auto',fontSize:'10px',lineHeight:'1.5',color:'#64748b',background:'transparent',padding:'0',margin:'4px 0 0',borderRadius:'0',maxWidth:'100%',whiteSpace:'normal',textAlign:'center'});
    }else if(mode==='game'){
      if(node.parentElement!==doc.body)doc.body.append(node);
      const view=doc.defaultView;
      const top=gameNoticeTop(screen,view.innerWidth,view.innerHeight);
      Object.assign(node.style,{display:'block',position:'fixed',left:'50%',top:top+'px',transform:'translateX(-50%)',right:'auto',bottom:'auto',zIndex:'2147483640',fontSize:'12px',lineHeight:'1.5',color:'#e5e7eb',background:'#171717e6',padding:'4px 8px',margin:'0',borderRadius:'4px',maxWidth:'90vw',whiteSpace:'normal',textAlign:'center'});
    }else{
      if(node.parentElement!==doc.body)doc.body.append(node);
      Object.assign(node.style,{display:'block',position:'fixed',left:'auto',top:'auto',transform:'none',right:'12px',bottom:'10px',zIndex:'2147483640',fontSize:'12px',lineHeight:'1.5',color:'#b0b0b0',background:'#171717e6',padding:'4px 8px',margin:'0',borderRadius:'4px',maxWidth:'95vw',whiteSpace:'normal',textAlign:'center'});
    }
    node.style.setProperty('--ro-ko-warning',mode==='panel'?'#966300':'#fbbf24');
    node.style.setProperty('--ro-ko-success',mode==='panel'?'#15803d':'#86efac');
  };
  // Rebuild contents only on a screen transition; otherwise reposition.
  const observer=new MutationObserver(()=>{if(node.dataset.roKoMode!==patchStatusPlacement(doc,pathname).mode)statusRefresh?.();else sync();});
  for(const id of STATUS_SCREENS){
    const el=doc.getElementById(id);
    if(el)observer.observe(el,{attributes:true,attributeFilter:['class','hidden'],...(id==='splash'?{subtree:true,childList:true,characterData:true}:id==='lobby-ui'||id==='hud'?{childList:true,subtree:true}:{})});
  }
  doc.defaultView?.addEventListener('resize',sync);
  sync();
  return sync;
}
export function hasGameNotice({engineUpdateAvailable,engineUpdated}){
  return !!(engineUpdateAvailable||engineUpdated);
}
// The game creates #pad-hints directly under body and toggles .hidden.
export function gamePatchInfoBottom(pad,view){
  if(!pad||pad.hidden||pad.classList.contains('hidden'))return 8;
  const style=view.getComputedStyle(pad);
  if(style.display==='none'||style.visibility==='hidden'||style.visibility==='collapse')return 8;
  const rect=pad.getBoundingClientRect();
  if(rect.width<=0||rect.height<=0||rect.bottom<=0||rect.top>=view.innerHeight)return 8;
  return Math.max(8,Math.ceil(view.innerHeight-rect.top+6));
}
export function bindGamePatchInfo(node,doc=document,pathname=location.pathname){
  const view=doc.defaultView;
  let pad=null;
  const sync=()=>{
    const visible=patchStatusPlacement(doc,pathname).mode==='game';
    node.style.display=visible?'block':'none';
    if(visible)node.style.bottom=gamePatchInfoBottom(pad,view)+'px';
  };
  const resizeObserver=view.ResizeObserver?new view.ResizeObserver(sync):null;
  const padObserver=new view.MutationObserver(sync);
  const findPad=()=>{
    const next=doc.getElementById('pad-hints');
    if(next!==pad){
      padObserver.disconnect();
      resizeObserver?.disconnect();
      pad=next;
      if(pad){
        padObserver.observe(pad,{attributes:true,attributeFilter:['class','hidden','style'],childList:true,subtree:true,characterData:true});
        resizeObserver?.observe(pad);
      }
    }
    sync();
  };
  const screenObserver=new view.MutationObserver(sync);
  for(const id of STATUS_SCREENS){
    const screen=doc.getElementById(id);
    if(screen)screenObserver.observe(screen,{attributes:true,attributeFilter:['class','hidden']});
  }
  // The controller hint may not exist until the first controller interaction.
  new view.MutationObserver(findPad).observe(doc.body,{childList:true});
  view.addEventListener('resize',sync);
  findPad();
}
export function engineNoticeText(requested,inGame){
  if(!requested)return {message:'',link:ENGINE_UPDATE_LABEL};
  return inGame
    ?{message:'업데이트 설치 후 새로고침 (',link:'다시 설치',suffix:')'}
    :{message:'업데이트 설치 후 게임을 새로고침해 주세요.',link:'업데이트 설치 창 다시 열기'};
}
let statusNode,statusSync,statusRefresh,engineInstallRequested=false;
function showStatus(state,engineVersion){
  if(!statusNode){
    statusNode=document.createElement('div');statusNode.id='ro-ko-status';statusNode.setAttribute('role','status');
    Object.assign(statusNode.style,{display:'none',pointerEvents:'none'});
    document.body.append(statusNode);
    statusSync=bindStatusPosition(statusNode);
    const info=document.createElement('div');
    info.id='ro-ko-game-info';
    info.textContent='비공식 한국어 패치 · v'+engineVersion;
    Object.assign(info.style,{display:'none',position:'fixed',right:'43px',bottom:'8px',zIndex:'2147483639',fontSize:'11px',lineHeight:'1.4',color:'#fff',opacity:'1',fontWeight:'600',textShadow:'-1px 0 #000, 1px 0 #000, 0 -1px #000, 0 1px #000, 0 1px 3px #000',background:'transparent',whiteSpace:'nowrap',pointerEvents:'none',userSelect:'none'});
    document.body.append(info);
    bindGamePatchInfo(info);
  }
  const node=statusNode;
  const mode=patchStatusPlacement(document,location.pathname).mode;
  node.dataset.roKoMode=mode;
  node.dataset.roKoNotice=String(hasGameNotice(state));
  statusRefresh=()=>showStatus(state,engineVersion);
  const inGame=mode==='game';
  if(!state.engineUpdateAvailable)engineInstallRequested=false;
  node.replaceChildren(...patchStatusContent(document,state,engineVersion,inGame,engineInstallRequested,()=>{
    engineInstallRequested=true;
    // Keep the clicked link intact until the browser opens its installation tab.
    setTimeout(()=>statusRefresh?.(),0);
  }));
  statusSync();
}
export function patchStatusContent(doc,state,engineVersion,inGame,installRequested,onInstall){
  const parts=[];
  if(!inGame){
    const title=doc.createElement('div');
    title.textContent='비공식 한국어 패치 / 엔진 v'+engineVersion;
    parts.push(title);
  }
  function add(text,color){
    const span=doc.createElement(inGame?'span':'div');
    span.textContent=(inGame&&parts.length?' · ':'')+text;
    span.style.color=color;
    parts.push(span);
  }
  const label=stateLabel(state);
  if(!inGame&&label)add(label,state.scanFailed?'var(--ro-ko-warning)':'inherit');
  if(state.engineUpdated&&!state.engineUpdateAvailable)add('최신 한국어 패치가 적용되었습니다.','var(--ro-ko-success)');
  if(state.engineUpdateAvailable){
    const {message,link:linkText,suffix}=engineNoticeText(installRequested,inGame);
    const link=doc.createElement('a');
    link.textContent=linkText;
    link.href=DATA_URL+'ro-ko.user.js';
    link.target='_blank';link.rel='noopener noreferrer';
    link.title='한국어 패치 스크립트 업데이트';
    Object.assign(link.style,{color:'var(--ro-ko-warning)',pointerEvents:'auto',textDecoration:'underline',cursor:'pointer'});
    link.addEventListener('click',onInstall);
    const notice=doc.createElement(inGame?'span':'div');
    notice.style.color='var(--ro-ko-warning)';
    if(message){
      if(!inGame){
        const instruction=doc.createElement('div');
        instruction.textContent=message;
        notice.append(instruction,link);
      }else notice.append(message,link,suffix??'');
    }else notice.append(link);
    parts.push(notice);
  }
  return parts;
}
function sameOriginBuild(value,base=location.href){
  try{
    const url=new URL(value,base);
    return url.origin===new URL(base).origin&&/^\/build\/[^/]+\.m?js$/.test(url.pathname)?url.href:null;
  }catch{return null;}
}
export function pageBundleType(pathname){
  return pathname==='/talents.html'||pathname==='/talents'?'talents':'main';
}
export function findPageBundle(urls,pageUrl){
  const kind=pageBundleType(new URL(pageUrl).pathname);
  const pattern=kind==='talents'?/\/talents-[^/]+\.js$/:/\/main-[^/]+\.js$/;
  return urls.map(value=>sameOriginBuild(value,pageUrl)).find(url=>url&&pattern.test(new URL(url).pathname));
}
async function gameMain(){
  const urls=[...document.querySelectorAll('script[src]')].map(e=>e.src)
    .concat(performance.getEntriesByType('resource').map(e=>e.name));
  const kind=pageBundleType(location.pathname);
  const url=findPageBundle(urls,location.href);
  if(!url)throw Error('Page bundle not found: '+kind);
  const bundleKey=kind==='talents'?'bundle:talents':'bundle';
  const saved=getSaved(bundleKey);
  if(saved?.url===url&&saved.build)return {url,build:saved.build,kind};
  const content=await fetchText(url);
  const build=content.match(/RO Survivors[^*\n]*?Build\s+([0-9a-f]{7,64})\b/i)?.[1];
  if(!build)throw Error('Game build not found');
  setSaved(bundleKey,{url,build});
  return {url,build,content,kind};
}
export async function sourceSnapshot(main,read=fetchText){
  const content=main.content??await read(main.url);
  const imported=[...content.matchAll(/\bfrom\s*["'](\.\/[^"']+\.m?js)["']/g)].map(m=>sameOriginBuild(m[1],main.url)).filter(Boolean);
  const urls=[...new Set(imported)].filter(url=>url!==main.url);
  const files=[{url:main.url,content}];
  for(const url of urls)files.push({url,content:await read(url)});
  // The talent page shares the language table, but does not need the main
  // game's item manifest to translate its labels and descriptions.
  if(main.kind!=='talents'){
    const manifest=new URL('/assets/manifest.json',main.url);
    manifest.searchParams.set('v',main.build);
    files.push({url:manifest.href,content:await read(manifest.href)});
  }
  const snapshot=extractSnapshot(files);
  if(snapshot.build!==main.build)throw Error('Build mismatch');
  return snapshot;
}
export function matchingTalentFallback(main,hash,cached){
  if(main.kind!=='talents'||cached?.build!==main.build||cached?.translationVersion!==hash||!cached.dictionary||!Object.keys(cached.dictionary).length)return null;
  return {...cached,scanFailed:true};
}
async function scanPack(main,pack){
  let snapshot;
  try{snapshot=await sourceSnapshot(main);}
  catch(error){
    if(main.kind==='talents'){
      const fallback=matchingTalentFallback(main,await sha256(JSON.stringify(pack)),getSaved('scan-v6:main'));
      if(fallback)return fallback;
    }
    throw error;
  }
  const rows=await Promise.all(snapshot.rows.map(identify));
  const historical=await Promise.all((snapshot.newsHistory??[]).map(identify));
  return {...buildScanDictionary(rows,historical,pack),scanFailed:main.kind!=='talents'&&snapshot.newsScanFailed};
}
export function buildScanDictionary(rows,historical,pack){
  const byKey=Object.create(null),newsDictionary=Object.create(null),nameDictionary=Object.create(null),english=new Map(),conflicts=new Set();
  for(const row of [...rows,...historical]){
    const record=pack.entries[row.id];
    const ko=record?.sourceHash===row.sourceHash?record.ko:null;
    if(row.kind==='news'){
      if(ko)newsDictionary[row.key]=ko;
      continue;
    }
    if(!ko)continue;
    byKey[row.key]=ko;
    if(row.kind==='name')nameDictionary[row.key]=ko;
    if(row.en!==null){
      if(english.has(row.en)&&english.get(row.en)!==ko)conflicts.add(row.en);
      else english.set(row.en,ko);
    }
  }
  for(const [key,ko] of english)if(!conflicts.has(key)&&!Object.hasOwn(byKey,key))byKey[key]=ko;
  return {...compare(rows,pack.entries),dictionary:byKey,newsDictionary,nameDictionary};
}
export async function startBrowser(embedded,engineVersion){
  if(document.readyState==='loading')await new Promise(resolve=>document.addEventListener('DOMContentLoaded',resolve,{once:true}));
  if(!document.body)return;
  let translationState={},engineState={};
  const renderStatus=()=>showStatus({...translationState,...engineState},engineVersion);
  const engineUpdate=createEngineUpdate({
    version:engineVersion,
    read:()=>getSaved('engine-version'),
    write:version=>setSaved('engine-version',version),
    check:()=>fetchText(DATA_URL+'ro-ko.meta.js','no-store'),
    notify:state=>{engineState=state;renderStatus();},
    schedule:(fn,ms)=>setTimeout(fn,ms)
  });
  void engineUpdate.poll();
  setInterval(()=>{void engineUpdate.poll();},UPDATE_INTERVAL_MS);
  try{
    validateRecords(embedded);
    let saved=getSaved('translation');
    try{if(saved){validateRecords(saved.pack);compareTranslationVersions(saved.version,embedded.version);}}catch{saved=null;}
    if(!saved||compareTranslationVersions(embedded.version,saved.version)>0){
      setSaved('translation',{version:embedded.version,hash:await sha256(JSON.stringify(embedded)),pack:embedded});
    }
    const main=await gameMain();
    const scanKey=main.kind==='talents'?'scan-v6:talents':'scan-v6:main';
    let refreshAdapter;
    const applyPack=(pack,result)=>{
      if(!result?.dictionary)throw Error('Translation scan failed');
      const wiki=wikiTranslationLookup(pack);
      if(refreshAdapter)refreshAdapter(result.dictionary,result.newsDictionary,wiki,result.nameDictionary);
      else refreshAdapter=installLanguageAdapter(result.dictionary,engineVersion,result.newsDictionary,wiki,result.nameDictionary);
    };
    const session=createSession({
      read:async key=>getSaved(key==='scan'?scanKey:key),
      write:async (key,value)=>setSaved(key==='scan'?scanKey:key,value),
      check:async()=>{
        const url=new URL('manifest.json',DATA_URL);
        url.searchParams.set('t',String(Math.floor(Date.now()/TRANSLATION_CHECK_INTERVAL_MS)));
        const m=JSON.parse(await fetchText(url.href,'no-store'));
        if(m.schema!==1||typeof m.translationVersion!=='string'||! /^[a-f0-9]{64}$/.test(m.translationHash)||m.file!=='ko.json')throw Error('Invalid manifest');
        return m;
      },
      download:async m=>{
        const url=new URL(m.file,DATA_URL);url.searchParams.set('v',m.translationHash);
        const raw=await fetchText(url.href,'no-store');
        const pack=validateRecords(JSON.parse(raw));
        if(await sha256(raw)!==m.translationHash||pack.version!==m.translationVersion)throw Error('Invalid translation download');
        return pack;
      },
      verify:async (pack,m)=>await sha256(JSON.stringify(pack))===m.translationHash,
      scan:pack=>scanPack(main,pack),
      onUpdate:applyPack,
      notify:state=>{translationState=state;renderStatus();}
    });
    const activePack=await session.start({navigationType:performance.getEntriesByType('navigation')[0]?.type??'navigate',build:main.build});
    const result=session.getScanResult();
    if(result?.dictionary)applyPack(activePack,result);
    let lastCheck=Date.now();
    const checkTranslation=()=>{
      if(Date.now()-lastCheck<5000)return;
      lastCheck=Date.now();void session.poll();
    };
    setInterval(checkTranslation,TRANSLATION_CHECK_INTERVAL_MS);
    window.addEventListener('focus',checkTranslation);
    document.addEventListener('visibilitychange',()=>{if(!document.hidden)checkTranslation();});
  }catch(error){
    translationState={scanFailed:true};renderStatus();
    console.warn('[RO Korean] Initialization failed',error);
  }
}
