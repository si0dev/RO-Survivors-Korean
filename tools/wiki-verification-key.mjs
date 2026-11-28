import {createHash} from 'node:crypto';
import {readFile} from 'node:fs/promises';
import {pathToFileURL} from 'node:url';

// The browser status section and the session's status labels are presentation only.
// If a boundary is missing or ambiguous, retain the source to invalidate the cache.
function withoutSection(source,start,end){
  const a=source.indexOf(start),b=source.indexOf(end);
  if(a<0||b<=a||source.indexOf(start,a+start.length)!==-1||source.indexOf(end,b+end.length)!==-1)return source;
  return source.slice(0,a)+source.slice(b);
}
export function wikiRuntimeKey(browser,session,packageSource){
  const relevantBrowser=withoutSection(browser,'// Keep status presentation separate from the translation session.','function sameOriginBuild(');
  const relevantSession=withoutSection(session,'export const ENGINE_UPDATE_LABEL=','// Dependency-injected storage/network/scan adapters.');
  const {version,...packageInputs}=JSON.parse(packageSource);
  return createHash('sha256').update(JSON.stringify([relevantBrowser,relevantSession,packageInputs])).digest('hex');
}
if(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href){
  const inputs=await Promise.all(['src/browser.mjs','src/session.mjs','package.json'].map(path=>readFile(path,'utf8')));
  console.log(wikiRuntimeKey(...inputs));
}
