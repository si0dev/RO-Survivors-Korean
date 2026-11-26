import {createWikiTranslator} from './core.mjs';
// Gear pickups compose the quality and item name at runtime, outside the language table.
const lootQualities = [['Común','Common'],['Poco común','Uncommon'],['Raro','Rare'],['Épico','Epic'],['Legendario','Legendary']];
export function translateLootToast(value, parent, lookup, translate) {
  if (typeof value !== 'string' || !parent?.matches('#toasts > .toast.q')) return value;
  const match = /^(\s*)([^:\n]+):([ \t]+)(\S[^\n]*?)(\s*)$/.exec(value);
  if (!match) return value;
  const [,leading,quality,separator,item,trailing] = match;
  for (const [es,en] of lootQualities) {
    const ko = lookup(es) ?? lookup(en);
    if (quality === es || quality === en || quality === ko) {
      return leading + (ko ?? quality) + ':' + separator + translate(item) + trailing;
    }
  }
  return value;
}
export function installLanguageAdapter(entries,engineVersion,newsEntries={},wikiEntries={}) {
  if (window.__roKoLocal) return;
  const dictionary=new Map(Object.entries(entries));
  const newsDictionary=new Map(Object.entries(newsEntries));
  const wikiTranslate=createWikiTranslator(wikiEntries);
  const inWiki=el=>!!el?.closest('#wk-nav, #wk-detail, #wk-search, #wk-close');
  const lookup = s => dictionary.get(s);
  // Build reusable rules once rather than for each untranslated string.
  const rules = [
        [/^(Points remaining|Remaining points|Puntos restantes):?\s*(\d+)$/i, m => `남은 포인트: ${m[2]}`],
        [/^(Base Lv\.?|Base Level)\s*(\d+)$/i, m => `Base Lv ${m[2]}`],
        [/^(Job Lv\.?|Job Level)\s*(\d+)$/i, m => `Job Lv ${m[2]}`],
        [/^(\d+) (players?|jugadores?)$/i, m => `플레이어 ${m[1]}명`],
        [/^(Channel|Canal) (\d+)\s*·\s*(\d+)$/i, m => `채널 ${m[2]} · ${m[3]}`],
        [/^(Talents of|Talentos de) (.+)$/, m => lookup(m[2]) ? `${lookup(m[2])} 특성` : undefined],
        [/^(Cargando assets de Ragnarok…|Loading Ragnarok assets…) (\d+)%$/, m => `라그나로크 리소스 불러오는 중… ${m[2]}%`],
        [/^([+][0-9]+ )?(.+?)( \[[0-9]+\])$/, m => lookup(m[2]) ? `${m[1] || ''}${lookup(m[2])}${m[3]}` : undefined],
        [/^(\+\d+) (.+)$/, m => lookup(m[2]) ? `${m[1]} ${lookup(m[2])}` : undefined],
        [/^(.+?) (Card|Egg)$/, m => lookup(m[1]) ? `${lookup(m[1])} ${m[2] === 'Card' ? '카드' : '알'}` : undefined],
  ];
  const translate = (value, news=false) => {
    if (typeof value !== 'string' || !value.trim()) return value;
    const s = value.trim();
    let result = news ? newsDictionary.get(s.replace(/\s+/g,' ')) ?? lookup(s) : lookup(s);
    if (result === undefined) {
      for (const [re, fn] of rules) {
        const m = re.exec(s);
        if (m) { result = fn(m); if (result !== undefined) break; }
      }
    }
    if (result === undefined || result === s) return value;
    return value.replace(s, () => result);
  };
  // The game uses a Spanish-keyed English translation table. Only add a
  // non-enumerable language accessor for objects matching that shape.
  const own = (o, k) => Object.prototype.hasOwnProperty.call(o, k);
  const tables = new WeakMap();
  const existing = Object.getOwnPropertyDescriptor(Object.prototype, 'ko');
  if (!existing) Object.defineProperty(Object.prototype, 'ko', {
    configurable: true, enumerable: false,
    get() {
      if (!own(this, 'es') || !own(this, 'en')) return undefined;
      if (this.es === null && this.en && typeof this.en === 'object') {
        const en = this.en;
        if (!tables.has(en)) tables.set(en, new Proxy(Object.create(null), {
          get(_, key) {
            if (typeof key !== 'string') return undefined;
            if (dictionary.has(key)) return dictionary.get(key);
            if (own(en, key)) return translate(en[key]);
            return undefined;
          },
          has(_, key) { return typeof key === 'string' && (dictionary.has(key) || own(en, key)); }
        }));
        return tables.get(en);
      }
      if (typeof this.es === 'string' && typeof this.en === 'string') {
        return dictionary.get(this.es) ?? translate(this.en);
      }
      return undefined;
    },
    set(value) { Object.defineProperty(this, 'ko', {value, writable:true, enumerable:true, configurable:true}); }
  });
  const active = () => /^ko(?:-|$)/i.test(document.documentElement?.lang || '');
  const SETTINGS = 'ro-survivors:settings';
  const PREF = 'ro-ko:language-selected';
  let previous = 'en', restorePending = false;
  try {
    const saved = JSON.parse(localStorage.getItem(SETTINGS) || '{}');
    if (typeof saved.lang === 'string' && saved.lang !== 'ko') previous = saved.lang;
    restorePending = localStorage.getItem(PREF) === '1';
  } catch {}
  // Keep the game's saved settings compatible if this userscript is removed.
  // Only the language field of the known settings entry is adjusted.
  try {
    const setItem = Storage.prototype.setItem;
    Storage.prototype.setItem = function(key, value) {
      if (this === localStorage && key === SETTINGS && typeof value === 'string') {
        try {
          const data = JSON.parse(value);
          if (data && typeof data.lang === 'string') {
            if (data.lang === 'ko') value = JSON.stringify({...data, lang:previous});
            else previous = data.lang;
          }
        } catch {}
      }
      return setItem.call(this, key, value);
    };
  } catch {}
  const remember = value => { try { localStorage.setItem(PREF, value ? '1' : '0'); } catch {} };
  const originals = new WeakMap();
  const savedAttrs = new WeakMap();
  const SKIP = 'script,style,noscript,template,textarea,input,select,option,[contenteditable]:not([contenteditable="false"]),[role="log"],#chat,#chat-log,.chat-log,.chat-messages,.chat-message,.player-name,.character-name,.username,.friend-name,.guild-name,.player-chat,[data-player-name],[data-character-name]';
  const ATTRS = ['title','aria-label','placeholder'];
  const blocked = el => {
    if(!el)return true;
    const excluded=el.closest(SKIP);
    if(!excluded)return false;
    // Explicit option values are safe to preserve while translating their
    // display labels inside the wiki. Never change a value or user input.
    if(inWiki(el)&&excluded.matches('option[value]'))return false;
    if(inWiki(el)&&excluded.matches('select')&&[...excluded.options].every(o=>o.hasAttribute('value')))return false;
    return true;
  };
  const replaceWikiValue=(value,ko)=>ko===undefined?translate(value):value.replace(value.trim(),()=>ko);
  function translateText(node) {
    if (!active() || blocked(node.parentElement)) return;
    const v = node.nodeValue;
    if(originals.get(node)?.[1]===v)return;
    if(inWiki(node.parentElement)){
      if(!v?.trim())return;
      void wikiTranslate(v).then(ko=>{
        if(!active()||!node.isConnected||node.nodeValue!==v||!inWiki(node.parentElement))return;
        const next=replaceWikiValue(v,ko);
        if(v!==next){originals.set(node,[v,next]);node.nodeValue=next;}
      }).catch(()=>{});
      return;
    }
    const loot = translateLootToast(v,node.parentElement,lookup,translate);
    const next = loot === v ? translate(v,!!node.parentElement?.closest('#news-body, #news-tabs')) : loot;
    if (v !== next) { originals.set(node, [v,next]); node.nodeValue = next; }
  }
  function translateAttr(el, key) {
    if (!active()) return;
    // Never modify input values, option values, data attributes or editable content.
    // Placeholder text on an input is presentational only, and is safe outside chat.
    if (key === 'placeholder' && el.matches('input,textarea')) {
      if (el.parentElement && blocked(el.parentElement)) return;
    } else if (blocked(el)) return;
    const value = el.getAttribute(key);
    if(savedAttrs.get(el)?.get(key)?.[1]===value)return;
    const apply=next=>{
      if(value!==next){
        let record=savedAttrs.get(el);
        if(!record)savedAttrs.set(el,record=new Map());
        record.set(key,[value,next]);el.setAttribute(key,next);
      }
    };
    if(inWiki(el)&&value?.trim()){
      void wikiTranslate(value).then(ko=>{
        if(active()&&el.isConnected&&el.getAttribute(key)===value&&inWiki(el))apply(replaceWikiValue(value,ko));
      }).catch(()=>{});
      return;
    }
    apply(translate(value));
  }
  function walk(root) {
    if (root.nodeType === 3) return translateText(root);
    if (![1,9,11].includes(root.nodeType)) return;
    if (root.nodeType === 1 && blocked(root)) {
      if (root.matches('input,textarea')) translateAttr(root,'placeholder');
      return;
    }
    if (root.nodeType === 1) for (const attr of ATTRS) translateAttr(root,attr);
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT, {
      acceptNode(n) {
        if (n.nodeType === 1 && blocked(n)) {
          if (n.matches('input,textarea')) translateAttr(n,'placeholder');
          return NodeFilter.FILTER_REJECT;
        }
        return NodeFilter.FILTER_ACCEPT;
      }
    });
    for (let n = walker.nextNode(); n; n = walker.nextNode()) {
      if (n.nodeType === 3) translateText(n);
      else for (const attr of ATTRS) translateAttr(n,attr);
    }
  }
  function restoreDOM() {
    const walker = document.createTreeWalker(document, NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT);
    for (let n = walker.nextNode(); n; n = walker.nextNode()) {
      if (n.nodeType === 3) {
        const pair = originals.get(n);
        if (pair && n.nodeValue === pair[1]) n.nodeValue = pair[0];
        originals.delete(n);
      } else {
        const attrs = savedAttrs.get(n);
        if (attrs) for (const [key,pair] of attrs) {
          if (n.getAttribute(key) === pair[1]) n.setAttribute(key,pair[0]);
        }
        savedAttrs.delete(n);
      }
    }
  }
  const talentMenu=location.pathname==='/talents.html'||location.pathname==='/talents'?'.lang':'header .lang';
  function addLanguageOptions() {
    for (const seg of document.querySelectorAll('.opt-seg')) {
      if (!seg.querySelector('[data-lang]') || seg.querySelector('[data-lang="ko"]')) continue;
      const button = document.createElement('button');
      button.type = 'button'; button.className = 'ro-btn small';
      button.dataset.lang = 'ko'; button.textContent = '한국어';
      seg.appendChild(button);
    }
    for (const list of document.querySelectorAll('.sp-lang-list')) {
      if (!list.querySelector('[data-lang]') || list.querySelector('[data-lang="ko"]')) continue;
      const li = document.createElement('li');
      li.setAttribute('role','option'); li.tabIndex = -1; li.dataset.lang = 'ko';
      const code = document.createElement('small'); code.textContent = 'KO';
      li.append('한국어',code); list.appendChild(li);
    }
    const talent = document.querySelector(talentMenu);
    if (talent?.querySelector('[data-l]') && !talent.querySelector('[data-l="ko"]')) {
      const button = document.createElement('button'); button.type = 'button';
      button.dataset.l = 'ko'; button.textContent = '한국어'; talent.appendChild(button);
    }
    if (active()) for (const group of document.querySelectorAll('.opt-seg, .sp-lang-list, '+talentMenu)) {
      for (const option of group.querySelectorAll('[data-lang], [data-l]')) {
        const selected = (option.dataset.lang || option.dataset.l) === 'ko';
        if (group.matches('.opt-seg, '+talentMenu)) option.classList.toggle('active', selected);
        if (option.hasAttribute('aria-selected') || group.matches('.sp-lang-list')) option.setAttribute('aria-selected', String(selected));
      }
    }
  }
  let wasActive = active();
  function syncLanguage() {
    const now = active();
    if (now !== wasActive) {
      wasActive = now;
      if (now) { restorePending = false; remember(true); walk(document); }
      else { remember(false); restoreDOM(); }
    }
    addLanguageOptions();
  }
  // Let the game's existing delegated language handler process data-lang=ko.
  // No synthetic ro-lang event: the game's own handler must change the language.
  document.addEventListener('click', event => {
    const option = event.target?.closest?.('.opt-seg [data-lang], .sp-lang-list [data-lang], '+talentMenu+' button[data-l]');
    if (!option) return;
    if ((option.dataset.lang || option.dataset.l) !== 'ko') restorePending = false;
    queueMicrotask(syncLanguage);
  }, true);
  window.addEventListener('ro-lang', () => queueMicrotask(syncLanguage));
  const observer = new MutationObserver(records => {
    syncLanguage();
    if (!active()) return;
    for (const m of records) {
      if (m.type === 'characterData') translateText(m.target);
      else if (m.type === 'attributes') {
        if (ATTRS.includes(m.attributeName)) translateAttr(m.target,m.attributeName);
      } else for (const n of m.addedNodes) walk(n);
    }
  });
  observer.observe(document,{subtree:true,childList:true,characterData:true,attributes:true,attributeFilter:[...ATTRS,'lang']});
  addLanguageOptions();
  if (active()) walk(document);
  // Restore an explicitly chosen Korean language after reload, once the game's
  // menu and delegated handler are available. Never select it on first install.
  if (restorePending) {
    let attempts = 0;
    const timer = setInterval(() => {
      if (!restorePending || active() || ++attempts > 75) { clearInterval(timer); return; }
      addLanguageOptions();
      const opt = document.querySelector('.sp-lang-list [data-lang="ko"], .opt-seg [data-lang="ko"], '+talentMenu+' button[data-l="ko"]');
      if (opt) opt.click();
    },400);
  }
  // PixiJS may rasterize labels through Canvas2D. Apply the same translation to
  // measurement and rendering. WebGL bitmap fonts / worker-only text are not covered.
  const patched = new Set();
  for (const ctor of [window.CanvasRenderingContext2D, window.OffscreenCanvasRenderingContext2D]) {
    if (!ctor?.prototype || patched.has(ctor.prototype)) continue;
    const proto = ctor.prototype;
    patched.add(proto);
    for (const key of ['fillText','strokeText','measureText']) {
      const original = proto[key];
      if (typeof original !== 'function') continue;
      try { proto[key] = function (text, ...args) { return original.call(this,active() ? translate(text) : text,...args); }; }
      catch { /* locked prototype: DOM translation remains active */ }
    }
  }
  Object.defineProperty(window,'__roKoLocal',{value:Object.freeze({version:engineVersion,entries:dictionary.size,translate,active}),configurable:true});
}
