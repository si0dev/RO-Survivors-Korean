import {chromium} from 'playwright';
import {createHash} from 'node:crypto';
import {readFile} from 'node:fs/promises';
import {loadRecords} from './records.mjs';
import {identify} from '../src/core.mjs';

const origin='https://ro-survivors.com';
const browser=await chromium.launch({headless:true,args:['--use-angle=swiftshader','--enable-unsafe-swiftshader']});
const sha=s=>createHash('sha256').update(s).digest('hex');
const verify=process.argv.includes('--verify');
async function scanWiki(korean=false){
 const page=await browser.newPage({locale:'en-US'});
 try{
 if(korean){
  const assets=Object.fromEntries(await Promise.all(['manifest.json','ko.json','ro-ko.meta.js','ro-ko.user.js'].map(async name=>[name,await readFile('dist/'+name,'utf8')])));
  await page.route('https://raw.githubusercontent.com/si0dev/RO-Survivors-Korean/translation-data/**',async route=>{
   const name=new URL(route.request().url()).pathname.split('/').pop();
   if(!Object.hasOwn(assets,name))return route.abort();
   await route.fulfill({body:assets[name],contentType:name.endsWith('.json')?'application/json':'text/javascript',headers:{'access-control-allow-origin':'*'}});
  });
  await page.addInitScript({content:"localStorage.setItem('ro-survivors:settings',JSON.stringify({lang:'en'}));\n"+assets['ro-ko.user.js']});
 }else await page.addInitScript(()=>{localStorage.setItem('ro-survivors:settings',JSON.stringify({lang:'en'}));});
 page.on('pageerror',e=>console.log('PAGE ERROR '+e.message.slice(0,250)));
 await page.goto(origin+'/',{waitUntil:'domcontentloaded',timeout:60000});
 const button=page.locator('#wiki-btn');
 const dialog=page.locator('#npc-dialog');
 const wikiPanel=page.locator('#wiki');
 const nav=wikiPanel.locator('#wk-nav'), detail=wikiPanel.locator('#wk-detail');
 const wikiVisible=async()=>await wikiPanel.isVisible()&&await nav.isVisible()&&await detail.isVisible();
 async function dismissNotice(){
  if(!await dialog.isVisible())return false;
  const title=(await page.locator('#npc-name').textContent()??'').trim();
  const body=(await page.locator('#npc-text').textContent()??'').trim();
  const buttons=dialog.locator('#npc-options button');
  const labels=await buttons.allTextContents();
  console.log('STARTUP NOTICE '+JSON.stringify({title,body:body.slice(0,500),labels}));
  if(title==='You now need an account'&&body==='You need an account to play RO Survivors. It is free and asks for no email.'&&labels.length===2&&labels.includes('I have an account')&&labels.includes('Create account')){
   // Choose the ordinary login view; never submit credentials or create an account.
   await buttons.getByText('I have an account',{exact:true}).click({noWaitAfter:true});
   await dialog.waitFor({state:'hidden',timeout:10000});
   return true;
  }
  if(!/^(no connection|disconnected|connection lost|sin conexión|server unavailable|maintenance|mantenimiento)$/i.test(title)||labels.length!==1||!/^(ok|accept|close|aceptar|cerrar)$/i.test(labels[0].trim()))throw Error('Unrecognized startup dialog; not dismissed');
  await buttons.first().click({noWaitAfter:true});
  await dialog.waitFor({state:'hidden',timeout:10000});
  return true;
 }
 await button.waitFor({state:'visible',timeout:90000});
 if(korean){
  await dismissNotice();
  await page.waitForFunction(()=>!!window.__roKoLocal,null,{timeout:90000});
  const option='.sp-lang-list [data-lang="ko"], .opt-seg [data-lang="ko"]';
  await page.waitForFunction(selector=>!!document.querySelector(selector),option,{timeout:20000});
  await page.evaluate(selector=>document.querySelector(selector).click(),option);
  await page.waitForFunction(()=>window.__roKoLocal?.active()===true,null,{timeout:20000});
 }
 try {
  // Wiki is an in-page panel: wait for its actual UI, not unrelated navigation.
  for(let attempt=1;attempt<=3;attempt++){
   if(await wikiVisible())break;
   await dismissNotice();
   await button.waitFor({state:'visible',timeout:20000});
   try {
    await button.click({timeout:15000,noWaitAfter:true});
    await Promise.all([wikiPanel.waitFor({state:'visible',timeout:20000}),nav.waitFor({state:'visible',timeout:20000}),detail.waitFor({state:'visible',timeout:20000})]);
    break;
   } catch(error){
    if(await wikiVisible())break;
    console.log('WIKI OPEN RETRY '+JSON.stringify({attempt,url:page.url(),noticeVisible:await dialog.isVisible(),error:error.message.slice(0,300)}));
    if(attempt===3)throw error;
   }
  }
 } catch(error) {
  console.log('WIKI OPEN DIAGNOSTIC '+JSON.stringify(await page.evaluate(()=>{
   const el=document.querySelector('#wiki-btn');
   if(!el)return {url:location.href,title:document.title,ready:document.readyState,button:false};
   const r=el.getBoundingClientRect();
   const top=document.elementFromPoint(r.x+r.width/2,r.y+r.height/2);
   return {url:location.href,title:document.title,ready:document.readyState,button:true,rect:{x:r.x,y:r.y,width:r.width,height:r.height},disabled:el.disabled,hit:top?.tagName,hitId:top?.id,hitClass:String(top?.className??''),htmlLang:document.documentElement.lang,wikiPresent:!!document.querySelector('#wiki'),wikiVisible:!!document.querySelector('#wiki')?.getClientRects().length,dialogVisible:!!document.querySelector('#npc-dialog')?.getClientRects().length,dialogTitle:document.querySelector('#npc-name')?.textContent,dialogText:document.querySelector('#npc-text')?.textContent?.slice(0,500),dialogButtons:[...document.querySelectorAll('#npc-options button')].map(b=>b.textContent)};
  }).catch(e=>({error:e.message}))));
  throw error;
 }
 await wikiPanel.waitFor({state:'visible',timeout:20000});
 await nav.waitFor({state:'visible',timeout:20000});
 await detail.waitFor({state:'visible',timeout:20000});
 const names=await nav.evaluate(el=>[...el.querySelectorAll('button[data-sec]')].map(x=>({id:x.dataset.sec,label:x.querySelector('b')?.textContent.trim()}))); 
 if(names.length<20||new Set(names.map(n=>n.id)).size!==names.length||names.some(n=>!n.id||!n.label))throw Error('Incomplete or ambiguous wiki navigation');
 console.log('NAV '+JSON.stringify(names));
 const currentBuild=await page.evaluate(async()=>{
  const urls=[...document.scripts].map(x=>x.src).concat(performance.getEntriesByType('resource').map(x=>x.name));
  const url=urls.find(x=>x&&new URL(x).origin===location.origin&&/\/build\/main-[^/]+\.js$/.test(new URL(x).pathname));
  if(!url)throw Error('Main bundle missing');
  const r=await fetch(url);if(!r.ok)throw Error('Main bundle HTTP '+r.status);
  return (await r.text()).match(/RO Survivors[^*\n]*?Build\s+([0-9a-f]{7,64})\b/i)?.[1];
 });
 if(!currentBuild)throw Error('Build missing');

 const labels=['Prontera Librarian','(Rare/Epic)','(Epic/Legendary)','(Legendary)',': Soldier Skeleton, Sohee','Dragon Breath','Snake Ring','Search','Búsqueda'];
 const shell=await wikiPanel.evaluate(el=>[...el.querySelectorAll('*')].filter(n=>n.getClientRects().length&&n.childElementCount===0).map(n=>n.textContent.trim()).filter(Boolean));
 console.log('SHELL_AUDIT '+JSON.stringify({build:currentBuild,matches:shell.filter(x=>labels.includes(x)),header:shell.slice(0,8)}));
 for(const label of labels.slice(0,7)){
  await page.locator('#wk-search').fill(label);
  await page.waitForFunction(()=>!!document.querySelector('#wk-detail .wk-result')||document.querySelector('#wk-detail .info-panel')?.textContent.includes('Nothing found'),null,{timeout:10000});
  await page.waitForTimeout(500);
  const results=await detail.locator('.wk-result').evaluateAll(els=>els.map(e=>({id:e.dataset.res,heading:e.querySelector('b')?.textContent,snippet:e.querySelector('small')?.textContent})));
  console.log('SEARCH_AUDIT '+JSON.stringify({label,results,heading:await detail.locator('h1,h2,h3,.wk-title').first().textContent().catch(()=>null)}));
  await page.locator('#wk-search').fill('');
  await page.waitForTimeout(300);
 }
 }finally{await page.close();}
}
try{await scanWiki()}finally{await browser.close()}
