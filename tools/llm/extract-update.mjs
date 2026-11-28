import {writeFile} from 'node:fs/promises';
import {sourceSnapshot,findPageBundle} from '../../src/browser.mjs';
import {identify,worklist} from '../../src/core.mjs';
import {loadRecords} from '../records.mjs';
const origin='https://ro-survivors.com';
async function get(url){
 const r=await fetch(url,{cache:'no-store',signal:AbortSignal.timeout(25000)});
 if(!r.ok||new URL(r.url).origin!==origin)throw Error('Game resource HTTP '+r.status);
 return r.text();
}
async function getMain(kind='main'){
 const page=origin+(kind==='main'?'/':'/talents.html');
 const html=await get(page);
 const urls=[...html.matchAll(/(?:src|href)\s*=\s*["']([^"']+)["']/gi)].map(m=>m[1]);
 const url=findPageBundle(urls,page);
 if(!url||new URL(url).origin!==origin)throw Error('Game entry bundle missing');
 const content=await get(url);
 const build=content.match(/RO Survivors[^*\n]*?Build\s+([0-9a-f]{7,64})\b/i)?.[1];
 if(!build)throw Error('Build missing');
 return {kind,url,content,build};
}
const [output]=process.argv.slice(2);
const all=process.argv.includes('--all');
if(!output)throw Error('Output path missing');
const main=await getMain();
if(output==='--build-only'){console.log(main.build);}
else{
 const talents=await getMain('talents');
 if(talents.build!==main.build)throw Error('Game build mismatch');
 const snapshots=await Promise.all([sourceSnapshot(main,get),sourceSnapshot(talents,get)]);
 if(snapshots[0].newsScanFailed)throw Error('Latest news extraction failed');
 const unique=new Map();
 for(const snapshot of snapshots)for(const row of all?[...snapshot.rows,...snapshot.newsHistory]:snapshot.rows){
  const r=await identify(row);
  if(unique.has(r.id)&&unique.get(r.id).sourceHash!==r.sourceHash)throw Error('Conflicting source ID');
  unique.set(r.id,r);
 }
 const records=await loadRecords();
 const rows=all?[...unique.values()]:(await worklist({rows:[...unique.values()]},records.entries)).filter(r=>r.status!=='translated');
 await writeFile(output,JSON.stringify({build:main.build,rows}),{mode:0o600});
 console.log('GAME_UPDATE_BUILD='+main.build+(all?' ALL_EXTRACTED=':' NEW_OR_CHANGED=')+rows.length);
}
