import {chromium} from 'playwright';
import {createHash} from 'node:crypto';
import {loadRecords} from './records.mjs';
import {identify} from '../src/core.mjs';

const origin='https://ro-survivors.com';
const browser=await chromium.launch({headless:true,args:['--use-angle=swiftshader','--enable-unsafe-swiftshader']});
const sha=s=>createHash('sha256').update(s).digest('hex');
try {
 const page=await browser.newPage({locale:'en-US'});
 await page.addInitScript(()=>{localStorage.setItem('ro-survivors:settings',JSON.stringify({lang:'en'}));});
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
 const source=new Set();
 const collect=async()=>{
  const texts=await page.evaluate(()=>{
   const out=[];
   const norm=s=>s.trim().replace(/\s+/g,' ');
   const skip='script,style,noscript,template,textarea,input,[contenteditable=true]';
   for(const root of document.querySelectorAll('#wk-nav,#wk-detail,#wk-search,#wk-close')){
    const walker=document.createTreeWalker(root,NodeFilter.SHOW_TEXT);
    while(walker.nextNode()){
     const n=walker.currentNode,p=n.parentElement;
     if(!p||p.closest(skip)||(!p.getClientRects().length&&!p.matches('option')))continue;
     const v=norm(n.nodeValue);if(v&&/\p{L}/u.test(v))out.push(v);
    }
    for(const select of root.querySelectorAll('select'))for(const opt of select.options){const v=norm(opt.textContent);if(v&&/\p{L}/u.test(v))out.push(v);}
    for(const el of [root,...root.querySelectorAll('[title],[aria-label],[placeholder]')]){
     if(!el.getClientRects().length)continue;
     for(const key of ['title','aria-label','placeholder']){
      const v=norm(el.getAttribute(key)||'');if(v&&/\p{L}/u.test(v))out.push(v);
     }
    }
   }
   return out;
  });
  for(const t of texts)source.add(t);
 };
 const settle=async()=>{await detail.waitFor({state:'visible'});await page.waitForTimeout(180);};
 const covered=[];let tabCount=0;
 for(const {id,label} of names){
  const item=nav.locator('button[data-sec='+JSON.stringify(id)+']');
  if(await item.count()!==1)throw Error('Missing or ambiguous category: '+label);
  await item.click();await settle();
  const seen=new Set();
  const attrs=['data-sjob','data-job','data-pane-tab'];
  async function scan(depth=0,path=[]){
   if(depth>attrs.length)throw Error('Unexpected wiki tab nesting');
   await collect();
   for(let k=depth;k<attrs.length;k++){
    const attr=attrs[k];
    const values=await detail.locator('button['+attr+']').evaluateAll((els,attribute)=>els.filter(el=>el.getClientRects().length).map(el=>el.getAttribute(attribute)),attr);
    if(!values.length)continue;
    for(const value of [...new Set(values)]){
     const id=JSON.stringify([...path,attr,value]);if(seen.has(id))continue;seen.add(id);
     const t=detail.locator('button['+attr+'='+JSON.stringify(value)+']');
     if(await t.count()!==1)throw Error('Ambiguous wiki tab: '+id);
     await t.click();await settle();tabCount++;
     await scan(k+1,[...path,attr,value]);
    }
    break;
   }
  }
  await scan();
  console.log('CATEGORY '+JSON.stringify({label,tabs:seen.size}));
  covered.push(label);
 }
 const records=await loadRecords();
 const wiki=new Map(Object.values(records.entries).filter(v=>v.scope==='wiki').map(v=>[v.sourceHash,v.ko]));
 const hashes=new Set(),missing=[];
 for(const key of source){const hash=sha(key);hashes.add(hash);if(!wiki.has(hash))missing.push(await identify({kind:'wiki',key,en:key}));}
 console.log('WIKI SUMMARY '+JSON.stringify({build:currentBuild,categories:covered.length,tabs:tabCount,total:source.size,matched:source.size-missing.length,missing:missing.length}));
 if(covered.length<20||tabCount<72||source.size<1700)throw Error('Incomplete wiki coverage');
 const unmatched=Object.entries(records.entries).filter(([,r])=>r.scope==='wiki'&&!hashes.has(r.sourceHash));
 console.log('AUDIT '+JSON.stringify({build:currentBuild,scope:'wiki',unmatched:unmatched.length}));
 for(const [id,r] of unmatched)console.log('UNMATCHED '+JSON.stringify({id,sourceHash:r.sourceHash}));
 for(const row of missing)console.log('WIKIROW '+JSON.stringify(row));
} finally {await browser.close();}
