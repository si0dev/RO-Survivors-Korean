// UI integration is kept separate from state; no game-function hooks here.
export function compareTranslationVersions(a,b){
  function parse(v){
    const m=/^(\d+)\.(\d+)\.(\d+)(?:-([a-zA-Z0-9.-]+))?$/.exec(v);
    if(!m)throw Error('Invalid translation version');
    return [Number(m[1]),Number(m[2]),Number(m[3]),m[4]??''];
  }
  const x=parse(a),y=parse(b);
  for(let i=0;i<3;i++){if(x[i]!==y[i])return Math.sign(x[i]-y[i]);}
  if(x[3]===y[3])return 0;
  if(!x[3])return 1;
  if(!y[3])return -1;
  return x[3].localeCompare(y[3],undefined,{numeric:true});
}
export const UPDATE_INTERVAL_MS=60*60*1000;
export function shouldScan({navigationType,build,translationVersion,previous}){
  return navigationType!=='reload'||!previous||previous.build!==build||previous.translationVersion!==translationVersion;
}
export const ENGINE_UPDATE_LABEL='새 한국어 패치가 있습니다. 업데이트하려면 클릭해 주세요.';
export function stateLabel({hasMissing,scanFailed}){
  return scanFailed?'번역 상태 확인 불가':hasMissing?'일부 미번역':'';
}
// Dependency-injected storage/network/scan adapters.
export function createSession({read,write,check,download,scan,notify,verify}){
  let result=null, busy=false, started=false;
  const emit=()=>notify({hasMissing:!!result?.hasMissing,scanFailed:!!result?.scanFailed});
  async function poll(){
    if(busy)return;
    busy=true;
    try{
      const manifest=await check();
      const saved=await read('translation');
      if(saved?.hash!==manifest.translationHash&&(!saved||compareTranslationVersions(manifest.translationVersion,saved.version)>=0)){
        const pack=await download(manifest);
        if(!await verify(pack,manifest))throw Error('Translation integrity check failed');
        await write('translation',{hash:manifest.translationHash,version:manifest.translationVersion,pack});
      }
    } catch{/* offline: keep previous cache and notice */}
    finally{busy=false;emit();}
  }
  async function start({navigationType,build}){
    if(started)throw Error('Session already started');
    started=true;
    await poll();
    const active=await read('translation');
    if(!active){result={scanFailed:true};emit();return null;}
    const previous=await read('scan');
    if(shouldScan({navigationType,build,translationVersion:active.hash,previous})){
      try{
        result={...await scan(active.pack),build,translationVersion:active.hash};
        await write('scan',result);
      } catch {result={scanFailed:true};}
    } else result=previous;
    emit();return active.pack;
  }
  return {start,poll,getScanResult:()=>result};
}

// Engine releases are independent of the translation data manifest.
export function parseEngineVersion(metadata){
  if(!/^\/\/ ==UserScript==\r?$/m.test(metadata)||!/^\/\/ ==\/UserScript==\r?$/m.test(metadata))throw Error('Invalid userscript metadata');
  const version=metadata.match(/^\/\/[ \t]+@version[ \t]+([^\s]+)[ \t]*\r?$/m)?.[1];
  if(!version)throw Error('Missing engine version');
  compareTranslationVersions(version,version);
  return version;
}
export function createEngineUpdate({version,read,write,check,notify,schedule}){
  let available=false,completed=false,busy=false;
  const emit=()=>notify({engineUpdateAvailable:available,engineUpdated:completed});
  const previous=read();
  try{completed=typeof previous==='string'&&compareTranslationVersions(version,previous)>0;}catch{}
  write(version);
  if(completed)schedule(()=>{completed=false;emit();},5000);
  emit();
  async function poll(){
    if(busy)return;
    busy=true;
    try{
      available=compareTranslationVersions(parseEngineVersion(await check()),version)>0;
      emit();
    }catch{/* offline or invalid metadata: retain last known status */}
    finally{busy=false;}
  }
  return {poll};
}
