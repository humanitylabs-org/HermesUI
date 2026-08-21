(function(){
  'use strict';

  const MAX_BOOKMARKS_PER_GROUP=20;
  const STORAGE_KEY='hermesui.tailnet-app';
  const BOOKMARK_STORAGE_KEY='hermesui.app-selector.bookmarks.v1';
  const FRAME_DECISION_STORAGE_KEY='hermesui.app-selector.frame-decisions.v1';
  const FRAME_CHECK_PATH='/frame-check/';
  const FRAME_INLINE_DECISION_TTL_MS=6*60*60*1000;
  const FRAME_BROWSER_DECISION_TTL_MS=5*60*1000;
  const URL_SCHEME_RE=/^[a-z][a-z0-9+.-]*:/i;
  const GROUPS={
    company:{label:'work app',plural:'work apps',icon:'company'},
    public:{label:'web bookmark',plural:'web bookmarks',icon:'globe'}
  };
  const ICONS={
    pipeline:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="4" width="18" height="16" rx="2"/><path d="M8 4v16M16 4v16M3 10h18"/></svg>',
    apps:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/></svg>',
    draw:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L8 18l-4 1 1-4z"/></svg>',
    browser:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18"/></svg>',
    terminal:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="4" width="18" height="16" rx="2"/><path d="m7 9 3 3-3 3M13 15h4"/></svg>',
    monitor:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="2.5" y="3.5" width="19" height="13" rx="2"/><path d="M8 20h8M12 16.5V20"/></svg>',
    company:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 21V5l8-3 8 3v16"/><path d="M9 21v-4h6v4M8 7h.01M12 7h.01M16 7h.01M8 11h.01M12 11h.01M16 11h.01"/></svg>',
    globe:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18"/></svg>',
    link:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M10 13a5 5 0 0 0 7.5.5l2-2a5 5 0 0 0-7-7l-1.1 1.1"/><path d="M14 11a5 5 0 0 0-7.5-.5l-2 2a5 5 0 0 0 7 7l1.1-1.1"/></svg>'
  };

  const root=document.documentElement;
  const workspace=document.getElementById('tailnetAppWorkspace');
  const frame=document.getElementById('tailnetAppFrame');
  const wizardHome=document.getElementById('tailnetWizardHome');
  const managerPanel=document.getElementById('tailnetAppManager');
  const home=document.getElementById('tailnetAppHome');
  const links=document.getElementById('tailnetAppLinks');
  const companyLinks=document.getElementById('tailnetCompanyAppLinks');
  const publicLinks=document.getElementById('tailnetPublicAppLinks');
  const privateAdd=document.getElementById('tailnetPrivateAdd');
  const companyAdd=document.getElementById('tailnetCompanyAdd');
  const publicAdd=document.getElementById('tailnetPublicAdd');
  const privateMarketplace={
    id:'private-marketplace',
    label:'Private app library',
    href:'https://www.aiwizards.com/apps',
    frameHref:new URL('/tailnet-frame/?app=private-marketplace&library=aiwizards-v2',location.origin).href,
    icon:'apps'
  };
  const appsById=new Map();
  const reservedBrowserTabs=new Map();
  let bookmarkActivationGeneration=0;
  let activeBookmarkNavigation=null;
  let savedGroups={company:[],public:[]};
  let activeId='';
  let tooltip=null;
  let bookmarkMenu=null;
  let menuBookmark=null;
  let longPress=null;
  let suppressBookmarkClick='';
  let frameDecisions=readFrameDecisions();


  function normalizeBookmarkUrl(raw){
    let value=typeof raw==='string'?raw.trim():'';
    if(!value)return '';
    if(!URL_SCHEME_RE.test(value))value=`https://${value}`;
    let url;
    try{url=new URL(value);}catch(_){return '';}
    if(url.protocol!=='https:'||url.username||url.password)return '';
    return url.href;
  }

  function readFrameDecisions(){
    try{
      const payload=JSON.parse(localStorage.getItem(FRAME_DECISION_STORAGE_KEY)||'null');
      if(!payload||payload.version!==1||!payload.entries||typeof payload.entries!=='object')return {};
      const result={};
      Object.entries(payload.entries).slice(0,MAX_BOOKMARKS_PER_GROUP*2).forEach(([href,entry])=>{
        if(!normalizeBookmarkUrl(href)||!entry||typeof entry!=='object')return;
        if(entry.mode!=='inline'&&entry.mode!=='browser')return;
        const checkedAt=Number(entry.checkedAt);
        if(!Number.isFinite(checkedAt)||checkedAt<=0)return;
        result[href]={mode:entry.mode,reason:typeof entry.reason==='string'?entry.reason:'',checkedAt};
      });
      return result;
    }catch(_){return {};}
  }

  function writeFrameDecisions(){
    try{
      frameDecisions=Object.fromEntries(
        Object.entries(frameDecisions)
          .sort(([,left],[,right])=>right.checkedAt-left.checkedAt)
          .slice(0,MAX_BOOKMARKS_PER_GROUP*2)
      );
      localStorage.setItem(FRAME_DECISION_STORAGE_KEY,JSON.stringify({version:1,entries:frameDecisions}));
      return true;
    }catch(_){return false;}
  }

  function freshFrameDecision(href){
    const decision=frameDecisions[href];
    if(!decision)return null;
    const ttl=decision.mode==='browser'?FRAME_BROWSER_DECISION_TTL_MS:FRAME_INLINE_DECISION_TTL_MS;
    if(Date.now()-decision.checkedAt>ttl)return null;
    return decision;
  }

  async function refreshFrameDecision(app,{force=false}={}){
    if(!app||!app.href)return null;
    const current=freshFrameDecision(app.href);
    if(current&&!force)return current;
    const controller=typeof AbortController==='function'?new AbortController():null;
    const timeout=controller?setTimeout(()=>controller.abort(),6000):null;
    try{
      const endpoint=new URL(FRAME_CHECK_PATH,location.origin);
      endpoint.searchParams.set('url',app.href);
      const options={cache:'no-store',credentials:'same-origin'};
      if(controller)options.signal=controller.signal;
      const response=await fetch(endpoint.href,options);
      if(!response.ok)return null;
      const payload=await response.json();
      if(!payload||payload.ok!==true||(payload.mode!=='inline'&&payload.mode!=='browser'))return null;
      const decision={mode:payload.mode,reason:typeof payload.reason==='string'?payload.reason:'',checkedAt:Date.now()};
      frameDecisions[app.href]=decision;
      writeFrameDecisions();
      return decision;
    }catch(_){return null;}finally{if(timeout)clearTimeout(timeout);}
  }

  async function refreshSavedFrameDecisions(){
    const bookmarks=[...savedGroups.company,...savedGroups.public];
    let index=0;
    async function worker(){
      while(index<bookmarks.length){
        const app=bookmarks[index++];
        await refreshFrameDecision(app);
      }
    }
    await Promise.all(Array.from({length:Math.min(4,bookmarks.length)},()=>worker()));
  }

  function cleanBookmark(raw,group){
    if(!GROUPS[group]||!raw||typeof raw!=='object')return null;
    const id=typeof raw.id==='string'?raw.id.trim():'';
    const label=typeof raw.label==='string'?raw.label.trim():'';
    const href=normalizeBookmarkUrl(raw.href);
    if(!/^[a-z0-9][a-z0-9-]{0,39}$/.test(id)||!label||label.length>48||!href)return null;
    const frameHref=new URL(`/tailnet-frame/?bookmark=${encodeURIComponent(`${group}:${id}`)}`,location.origin).href;
    const browserHref=new URL(`/tailnet-frame/?browser=${encodeURIComponent(`${group}:${id}`)}`,location.origin).href;
    return {id,label,href,frameHref,browserHref,group,icon:GROUPS[group].icon};
  }

  function bookmarkToken(app){
    return app&&GROUPS[app.group]?`${app.group}:${app.id}`:'';
  }

  function nextBookmarkGeneration(){
    bookmarkActivationGeneration+=1;
    return String(bookmarkActivationGeneration);
  }

  function bookmarkFrameHref(app,generation){
    const url=new URL(app.frameHref,location.origin);
    url.searchParams.set('generation',generation);
    return url.href;
  }

  function browserReservationHref(app,generation){
    const url=new URL(app.browserHref,location.origin);
    url.searchParams.set('generation',generation);
    return url.href;
  }

  function isCurrentBookmarkDecision(data,app){
    const token=bookmarkToken(app);
    return Boolean(
      token&&
      data.token===token&&
      activeId===app.id&&
      activeBookmarkNavigation&&
      activeBookmarkNavigation.token===token&&
      activeBookmarkNavigation.generation===data.generation
    );
  }

  function emptySavedGroups(){return {company:[],public:[]};}

  function readSavedGroups(){
    const result=emptySavedGroups();
    try{
      const payload=JSON.parse(localStorage.getItem(BOOKMARK_STORAGE_KEY)||'null');
      if(!payload||payload.version!==1)return result;
      Object.keys(GROUPS).forEach(group=>{
        const seen=new Set();
        const entries=Array.isArray(payload[group])?payload[group]:[];
        entries.slice(0,MAX_BOOKMARKS_PER_GROUP).forEach(raw=>{
          const app=cleanBookmark(raw,group);
          if(!app||seen.has(app.id)||result[group].some(item=>item.href===app.href))return;
          seen.add(app.id);
          result[group].push(app);
        });
      });
    }catch(_){}
    return result;
  }

  function writeSavedGroups(){
    try{
      localStorage.setItem(BOOKMARK_STORAGE_KEY,JSON.stringify({version:1,company:savedGroups.company,public:savedGroups.public}));
      return true;
    }catch(_){return false;}
  }

  function closeSessionsOverlay(){
    if(typeof window.closeMobileSidebar==='function')window.closeMobileSidebar();
  }

  function isPhoneWidth(){
    try{return window.matchMedia('(max-width:640px)').matches;}catch(_){return window.innerWidth<=640;}
  }

  function isWizardHomeDesktop(){
    try{return window.matchMedia('(min-width:901px)').matches;}catch(_){return window.innerWidth>=901;}
  }

  function markSelected(id){
    const externalLinks=document.querySelectorAll('.tailnet-app-rail [data-tailnet-app-id]');
    const hermesSelected=!id;
    if(home){
      home.classList.toggle('active',hermesSelected);
      if(hermesSelected)home.setAttribute('aria-current','page');
      else home.removeAttribute('aria-current');
    }
    externalLinks.forEach(link=>{
      const selected=link.dataset.tailnetAppId===id;
      link.classList.toggle('active',selected);
      if(selected)link.setAttribute('aria-current','page');
      else link.removeAttribute('aria-current');
    });
  }

  function activateHermes({remember=true,openMobileMenu=false}={}){
    closeReservedTabsExcept();
    hideTooltip();
    closeBookmarkMenu();
    activeId='';
    activeBookmarkNavigation=null;
    const showWizardHome=isWizardHomeDesktop();
    root.setAttribute('data-tailnet-view',showWizardHome?'wizard-home':'hermes');
    if(frame)frame.hidden=true;
    if(managerPanel)managerPanel.hidden=true;
    if(wizardHome)wizardHome.hidden=!showWizardHome;
    if(workspace){
      workspace.hidden=!showWizardHome;
      workspace.setAttribute('aria-label',showWizardHome?'Wizard Canvas':'Selected Tailnet app');
    }
    markSelected('');
    if(openMobileMenu&&isPhoneWidth()&&typeof window.toggleMobileSidebar==='function')window.toggleMobileSidebar();
    else closeSessionsOverlay();
    if(remember){
      try{sessionStorage.removeItem(STORAGE_KEY);}catch(_){}
    }
    document.dispatchEvent(new CustomEvent('hermesui:tailnet-app-selected',{detail:{id:'hermes-ui'}}));
  }

  function activateApp(app,{bookmarkGeneration=''}={}){
    if(!workspace||!frame)return;
    const token=bookmarkToken(app);
    closeReservedTabsExcept(token);
    hideTooltip();
    closeBookmarkMenu();
    const wasBrowserFallback=frame.dataset.browserFallback==='true';
    let targetFrameHref=app.frameHref;
    let frameKey=app.id===privateMarketplace.id
      ?'app:private-marketplace:aiwizards-v2'
      :`app:${app.id}`;
    if(token){
      let generation=bookmarkGeneration;
      if(
        !generation&&
        activeId===app.id&&
        activeBookmarkNavigation&&
        activeBookmarkNavigation.token===token&&
        !wasBrowserFallback
      )generation=activeBookmarkNavigation.generation;
      if(!generation)generation=nextBookmarkGeneration();
      activeBookmarkNavigation={token,generation};
      targetFrameHref=bookmarkFrameHref(app,generation);
      frameKey=`bookmark:${token}:${generation}`;
    }else activeBookmarkNavigation=null;
    activeId=app.id;
    delete frame.dataset.browserFallback;
    if(frame.dataset.tailnetFrameKey!==frameKey||wasBrowserFallback){
      frame.dataset.tailnetAppId=app.id;
      frame.dataset.tailnetFrameKey=frameKey;
      frame.title=app.label;
      frame.src=targetFrameHref;
    }
    workspace.setAttribute('aria-label',app.label);
    if(wizardHome)wizardHome.hidden=true;
    if(frame)frame.hidden=false;
    workspace.hidden=false;
    root.setAttribute('data-tailnet-view','external');
    markSelected(app.id);
    closeSessionsOverlay();
    try{sessionStorage.setItem(STORAGE_KEY,app.id);}catch(_){}
    document.dispatchEvent(new CustomEvent('hermesui:tailnet-app-selected',{detail:{id:app.id,label:app.label}}));
  }

  function openBrowserTab(href){
    try{return window.open(href,'_blank','noopener,noreferrer');}catch(_){return null;}
  }

  function reserveBrowserTab(app,generation){
    const token=bookmarkToken(app);
    closeReservedTab(reservedBrowserTabs.get(token));
    reservedBrowserTabs.delete(token);
    try{
      const reserved=window.open(browserReservationHref(app,generation),'_blank');
      if(reserved){
        reserved.opener=null;
        reservedBrowserTabs.set(token,{tab:reserved,generation});
      }
      return reserved;
    }catch(_){return null;}
  }

  function closeReservedTab(reserved){
    if(!reserved)return;
    const tab=reserved.tab||reserved;
    try{if(!tab.closed)tab.close();}catch(_){}
  }

  function takeReservedTab(app,generation=''){
    const token=bookmarkToken(app);
    const entry=reservedBrowserTabs.get(token)||null;
    if(!entry||(generation&&entry.generation!==generation))return null;
    reservedBrowserTabs.delete(token);
    return entry.tab;
  }

  function closeReservedTabsExcept(token=''){
    reservedBrowserTabs.forEach((reserved,key)=>{
      if(key===token)return;
      closeReservedTab(reserved);
      reservedBrowserTabs.delete(key);
    });
  }

  function activateBrowserFallback(app,{open=true,reserved=null,reopen=false}={}){
    if(!workspace||!frame||!app.browserHref)return;
    closeReservedTabsExcept();
    hideTooltip();
    closeBookmarkMenu();
    activeId=app.id;
    activeBookmarkNavigation=null;
    const alreadyShowing=frame.dataset.tailnetAppId===app.id&&frame.dataset.browserFallback==='true';
    if(open&&(!alreadyShowing||reopen)){
      let usedReserved=false;
      if(reserved){
        try{
          if(!reserved.closed){
            reserved.location.replace(app.href);
            usedReserved=true;
          }
        }catch(_){}
      }
      if(!usedReserved)openBrowserTab(app.href);
    }
    frame.dataset.tailnetAppId=app.id;
    frame.dataset.tailnetFrameKey=`browser:${bookmarkToken(app)}`;
    frame.dataset.browserFallback='true';
    frame.title=`${app.label} — browser fallback`;
    if(!alreadyShowing)frame.src=app.browserHref;
    workspace.setAttribute('aria-label',`${app.label} opened in browser`);
    if(wizardHome)wizardHome.hidden=true;
    if(frame)frame.hidden=false;
    workspace.hidden=false;
    root.setAttribute('data-tailnet-view','external');
    markSelected(app.id);
    closeSessionsOverlay();
    try{sessionStorage.setItem(STORAGE_KEY,app.id);}catch(_){}
    document.dispatchEvent(new CustomEvent('hermesui:tailnet-app-selected',{detail:{
      id:app.id,
      label:app.label,
      mode:'browser'
    }}));
  }

  function activateBookmark(app){
    const decision=freshFrameDecision(app.href);
    if(decision&&decision.mode==='browser'){
      const reserved=takeReservedTab(app);
      activateBrowserFallback(app,{reserved,reopen:true});
      return;
    }
    if(activeId===app.id&&frame.dataset.browserFallback!=='true'){
      activateApp(app);
      return;
    }
    const generation=nextBookmarkGeneration();
    reserveBrowserTab(app,generation);
    activateApp(app,{bookmarkGeneration:generation});
  }


  function appIcon(name){
    const icon=document.createElement('span');
    icon.className='tailnet-app-icon';
    icon.setAttribute('aria-hidden','true');
    icon.innerHTML=ICONS[name]||ICONS.link;
    return icon;
  }


  function renderBookmark(container,app,group){
    const link=document.createElement('button');
    link.className='rail-btn tailnet-app-link has-tooltip';
    link.type='button';
    link.dataset.tailnetAppId=app.id;
    link.dataset.bookmarkGroup=group;
    link.dataset.bookmarkId=app.id;
    link.dataset.tooltip=app.label;
    link.setAttribute('aria-label',app.label);
    link.setAttribute('aria-haspopup','menu');
    link.addEventListener('click',event=>{
      if(suppressBookmarkClick===app.id){
        suppressBookmarkClick='';
        event.preventDefault();
        return;
      }
      activateBookmark(app);
    });
    link.addEventListener('pointerenter',()=>void refreshFrameDecision(app));
    link.addEventListener('focus',()=>void refreshFrameDecision(app));
    bindBookmarkActions(link);
    link.appendChild(appIcon(GROUPS[group].icon));
    container.appendChild(link);
  }

  function containerForGroup(group){return group==='company'?companyLinks:publicLinks;}
  function buttonForGroup(group){return group==='company'?companyAdd:publicAdd;}

  function renderSavedGroup(group){
    const container=containerForGroup(group);
    if(!container)return;
    container.replaceChildren();
    savedGroups[group].forEach(app=>{
      appsById.set(app.id,app);
      renderBookmark(container,app,group);
    });
    markSelected(activeId);
  }

  function suggestedLabel(href){
    try{
      const host=new URL(href).hostname.replace(/^www\./i,'');
      return host.split('.')[0].replace(/[-_]+/g,' ').replace(/\b\w/g,char=>char.toUpperCase()).slice(0,48)||host.slice(0,48);
    }catch(_){return '';}
  }

  function newBookmarkId(group){
    return `${group}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2,7)}`.slice(0,40);
  }

  function notify(message){
    if(typeof window.showToast==='function')window.showToast(message);
  }

  function ensureTooltip(){
    if(tooltip)return tooltip;
    tooltip=document.createElement('div');
    tooltip.className='tailnet-rail-tooltip';
    tooltip.setAttribute('role','tooltip');
    tooltip.hidden=true;
    document.body.appendChild(tooltip);
    return tooltip;
  }

  function hideTooltip(){
    if(tooltip)tooltip.hidden=true;
  }

  function showTooltip(target){
    const label=target&&target.dataset?String(target.dataset.tooltip||'').trim():'';
    if(!label)return;
    const node=ensureTooltip();
    node.textContent=label;
    node.hidden=false;
    const rect=target.getBoundingClientRect();
    const width=node.offsetWidth;
    const height=node.offsetHeight;
    node.style.left=`${Math.max(8,Math.min(window.innerWidth-width-8,rect.right+8))}px`;
    node.style.top=`${Math.max(8,Math.min(window.innerHeight-height-8,rect.top+(rect.height-height)/2))}px`;
  }

  function closeBookmarkMenu({restoreFocus=false}={}){
    const target=menuBookmark&&menuBookmark.button;
    if(bookmarkMenu)bookmarkMenu.hidden=true;
    menuBookmark=null;
    if(restoreFocus&&target&&target.isConnected)target.focus();
  }

  function bookmarkFor(group,id){
    return GROUPS[group]&&savedGroups[group]?savedGroups[group].find(app=>app.id===id)||null:null;
  }

  async function renameBookmark(){
    const current=menuBookmark;
    closeBookmarkMenu();
    if(!current)return;
    const app=bookmarkFor(current.group,current.id);
    if(!app)return;
    const rawLabel=await promptValue({
      title:'Rename',
      message:'Choose the short name shown in the app selector.',
      value:app.label,
      selectAll:true,
      placeholder:'App name',
      confirmLabel:'Rename'
    });
    if(rawLabel==null)return;
    const replacement=cleanBookmark({...app,label:String(rawLabel).trim()},current.group);
    if(!replacement){
      notify('Enter a name between 1 and 48 characters.');
      return;
    }
    const index=savedGroups[current.group].findIndex(item=>item.id===current.id);
    if(index<0)return;
    const previous=savedGroups[current.group][index];
    savedGroups[current.group][index]=replacement;
    if(!writeSavedGroups()){
      savedGroups[current.group][index]=previous;
      notify('Browser storage is unavailable, so the app was not renamed.');
      return;
    }
    appsById.set(replacement.id,replacement);
    renderSavedGroup(current.group);
    if(activeId===replacement.id){
      frame.title=replacement.label;
      workspace.setAttribute('aria-label',replacement.label);
    }
    notify(`${replacement.label} renamed.`);
    document.dispatchEvent(new CustomEvent('hermesui:app-bookmarks-changed',{detail:{group:current.group,count:savedGroups[current.group].length}}));
  }

  function deleteBookmark(){
    const current=menuBookmark;
    closeBookmarkMenu();
    if(!current)return;
    const app=bookmarkFor(current.group,current.id);
    if(!app)return;
    const previous=savedGroups[current.group].slice();
    savedGroups[current.group]=savedGroups[current.group].filter(item=>item.id!==current.id);
    if(!writeSavedGroups()){
      savedGroups[current.group]=previous;
      notify('Browser storage is unavailable, so the app was not deleted.');
      return;
    }
    appsById.delete(current.id);
    if(activeId===current.id)activateHermes();
    renderSavedGroup(current.group);
    notify(`${app.label} deleted.`);
    document.dispatchEvent(new CustomEvent('hermesui:app-bookmarks-changed',{detail:{group:current.group,count:savedGroups[current.group].length}}));
  }

  function ensureBookmarkMenu(){
    if(bookmarkMenu)return bookmarkMenu;
    bookmarkMenu=document.createElement('div');
    bookmarkMenu.className='tailnet-bookmark-menu';
    bookmarkMenu.setAttribute('role','menu');
    bookmarkMenu.setAttribute('aria-label','Bookmark actions');
    bookmarkMenu.hidden=true;
    const rename=document.createElement('button');
    rename.type='button';
    rename.setAttribute('role','menuitem');
    rename.textContent='Rename';
    rename.addEventListener('click',()=>void renameBookmark());
    const remove=document.createElement('button');
    remove.type='button';
    remove.setAttribute('role','menuitem');
    remove.className='danger';
    remove.textContent='Delete';
    remove.addEventListener('click',deleteBookmark);
    bookmarkMenu.append(rename,remove);
    document.body.appendChild(bookmarkMenu);
    return bookmarkMenu;
  }

  function openBookmarkMenu(button,clientX,clientY){
    const group=button.dataset.bookmarkGroup||'';
    const id=button.dataset.bookmarkId||'';
    if(!bookmarkFor(group,id))return;
    hideTooltip();
    const menu=ensureBookmarkMenu();
    menuBookmark={group,id,button};
    menu.hidden=false;
    const rect=button.getBoundingClientRect();
    const x=Number.isFinite(clientX)?clientX:rect.right+8;
    const y=Number.isFinite(clientY)?clientY:rect.top;
    const width=menu.offsetWidth;
    const height=menu.offsetHeight;
    menu.style.left=`${Math.max(8,Math.min(window.innerWidth-width-8,x))}px`;
    menu.style.top=`${Math.max(8,Math.min(window.innerHeight-height-8,y))}px`;
    const first=menu.querySelector('button');
    if(first)first.focus();
  }

  function suppressBookmarkActivation(id){
    suppressBookmarkClick=id;
    setTimeout(()=>{
      if(suppressBookmarkClick===id)suppressBookmarkClick='';
    },900);
  }

  function cancelLongPress(){
    if(!longPress)return;
    clearTimeout(longPress.timer);
    longPress=null;
  }

  function bindBookmarkActions(button){
    button.addEventListener('contextmenu',event=>{
      event.preventDefault();
      cancelLongPress();
      openBookmarkMenu(button,event.clientX,event.clientY);
    });
    button.addEventListener('pointerdown',event=>{
      if(event.pointerType==='mouse'||event.button!==0)return;
      cancelLongPress();
      const startX=event.clientX;
      const startY=event.clientY;
      longPress={
        pointerId:event.pointerId,
        startX,
        startY,
        timer:setTimeout(()=>{
          suppressBookmarkActivation(button.dataset.bookmarkId||'');
          openBookmarkMenu(button,startX,startY);
          longPress=null;
          try{if(navigator.vibrate)navigator.vibrate(20);}catch(_){}
        },550)
      };
    });
    button.addEventListener('pointermove',event=>{
      if(!longPress||event.pointerId!==longPress.pointerId)return;
      if(Math.hypot(event.clientX-longPress.startX,event.clientY-longPress.startY)>10)cancelLongPress();
    });
    button.addEventListener('pointerup',cancelLongPress);
    button.addEventListener('pointercancel',cancelLongPress);
  }

  function bindOverlayInteractions(){
    window.addEventListener('message',event=>{
      if(event.origin!==location.origin||event.source!==frame.contentWindow)return;
      const data=event.data;
      if(
        !data||
        data.type!=='hermesui:bookmark-frame-decision'||
        typeof data.token!=='string'||
        typeof data.generation!=='string'
      )return;
      if(data.mode!=='inline'&&data.mode!=='browser'&&data.mode!=='unknown')return;
      const split=data.token.indexOf(':');
      if(split<1)return;
      const group=data.token.slice(0,split);
      const id=data.token.slice(split+1);
      const app=bookmarkFor(group,id);
      if(!app)return;
      if(!isCurrentBookmarkDecision(data,app))return;
      const reserved=takeReservedTab(app,data.generation);
      if(data.mode==='inline'||data.mode==='browser'){
        frameDecisions[app.href]={
          mode:data.mode,
          reason:typeof data.reason==='string'?data.reason:'',
          checkedAt:Date.now()
        };
        writeFrameDecisions();
      }
      if(activeId!==app.id){
        closeReservedTab(reserved);
        return;
      }
      if(data.mode==='browser')activateBrowserFallback(app,{reserved});
      else closeReservedTab(reserved);
    });
    document.addEventListener('pointerover',event=>{
      const target=event.target instanceof Element?event.target.closest('.tailnet-app-rail .has-tooltip[data-tooltip]'):null;
      if(target)showTooltip(target);
    });
    document.addEventListener('pointerout',event=>{
      const target=event.target instanceof Element?event.target.closest('.tailnet-app-rail .has-tooltip[data-tooltip]'):null;
      if(!target)return;
      const related=event.relatedTarget instanceof Element?event.relatedTarget.closest('.tailnet-app-rail .has-tooltip[data-tooltip]'):null;
      if(related!==target)hideTooltip();
    });
    document.addEventListener('focusin',event=>{
      const target=event.target instanceof Element?event.target.closest('.tailnet-app-rail .has-tooltip[data-tooltip]'):null;
      if(target)showTooltip(target);
    });
    document.addEventListener('focusout',event=>{
      if(event.target instanceof Element&&event.target.closest('.tailnet-app-rail .has-tooltip[data-tooltip]'))hideTooltip();
    });
    document.addEventListener('pointerdown',event=>{
      if(bookmarkMenu&&!bookmarkMenu.hidden&&event.target instanceof Node&&!bookmarkMenu.contains(event.target))closeBookmarkMenu();
    });
    document.addEventListener('keydown',event=>{
      if(event.key==='Escape'&&bookmarkMenu&&!bookmarkMenu.hidden){
        event.preventDefault();
        closeBookmarkMenu({restoreFocus:true});
      }
    });
    const rail=document.querySelector('.tailnet-app-rail');
    if(rail)rail.addEventListener('scroll',hideTooltip,true);
    window.addEventListener('resize',()=>{
      hideTooltip();
      closeBookmarkMenu();
    });
    window.addEventListener('blur',hideTooltip);
  }

  async function promptValue(options){
    if(typeof window.showPromptDialog==='function')return window.showPromptDialog(options);
    return window.prompt(options.message||options.title||'',options.value||'');
  }

  async function addSavedApp(group){
    const definition=GROUPS[group];
    const button=buttonForGroup(group);
    if(!definition||!button)return;
    if(savedGroups[group].length>=MAX_BOOKMARKS_PER_GROUP){
      notify(`This group already has ${MAX_BOOKMARKS_PER_GROUP} items.`);
      return;
    }
    button.disabled=true;
    try{
      const rawHref=await promptValue({
        title:`Add ${definition.label}`,
        message:'Enter the website address. HTTPS is required.',
        placeholder:'https://example.com',
        inputType:'url',
        confirmLabel:'Next'
      });
      if(rawHref==null)return;
      const href=normalizeBookmarkUrl(rawHref);
      if(!href){
        notify('That address must be a safe HTTPS URL.');
        return;
      }
      if(savedGroups[group].some(app=>app.href===href)){
        notify('That address is already in this group.');
        return;
      }
      const rawLabel=await promptValue({
        title:`Name this ${definition.label}`,
        message:'Choose the short name shown in the app selector.',
        value:suggestedLabel(href),
        selectAll:true,
        placeholder:'App name',
        confirmLabel:'Add'
      });
      if(rawLabel==null)return;
      const app=cleanBookmark({id:newBookmarkId(group),label:String(rawLabel).trim(),href},group);
      if(!app){
        notify('Enter a name between 1 and 48 characters.');
        return;
      }
      savedGroups[group].push(app);
      if(!writeSavedGroups()){
        savedGroups[group].pop();
        notify('Browser storage is unavailable, so the app was not added.');
        return;
      }
      renderSavedGroup(group);
      notify(`${app.label} added to ${definition.plural}.`);
      void refreshFrameDecision(app,{force:true});
      document.dispatchEvent(new CustomEvent('hermesui:app-bookmarks-changed',{detail:{group,count:savedGroups[group].length}}));
    }finally{
      button.disabled=false;
    }
  }

  async function loadApps(){
    if(!links||!home||!workspace||!frame||!companyLinks||!publicLinks||!privateAdd||!companyAdd||!publicAdd)return;
    root.setAttribute('data-tailnet-view','hermes');
    bindOverlayInteractions();
    home.addEventListener('click',event=>{
      event.preventDefault();
      activateHermes({openMobileMenu:true});
    });
    appsById.set(privateMarketplace.id,privateMarketplace);
    privateAdd.addEventListener('click',()=>activateApp(privateMarketplace));
    companyAdd.addEventListener('click',()=>void addSavedApp('company'));
    publicAdd.addEventListener('click',()=>void addSavedApp('public'));
    document.addEventListener('hermesui:tailnet-app-selected',event=>{
      const id=event&&event.detail&&event.detail.id;
      if(!id||id==='hermes-ui')return;
      activeId=id;
      if(wizardHome)wizardHome.hidden=true;
    });
    savedGroups=readSavedGroups();
    renderSavedGroup('company');
    renderSavedGroup('public');
    void refreshSavedFrameDecisions();
    let remembered='';
    try{remembered=sessionStorage.getItem(STORAGE_KEY)||'';}catch(_){}
    if(remembered&&appsById.has(remembered))activateApp(appsById.get(remembered));
    else activateHermes({remember:false});
    const desktopHomeMedia=window.matchMedia('(min-width:901px)');
    const syncHomeAcrossBreakpoint=()=>{if(!activeId)activateHermes({remember:false});};
    if(typeof desktopHomeMedia.addEventListener==='function')desktopHomeMedia.addEventListener('change',syncHomeAcrossBreakpoint);
    else if(typeof desktopHomeMedia.addListener==='function')desktopHomeMedia.addListener(syncHomeAcrossBreakpoint);
    root.dataset.tailnetAppsReady='true';
    document.dispatchEvent(new CustomEvent('hermesui:tailnet-apps-ready',{detail:{
      count:savedGroups.company.length+savedGroups.public.length+2,
      privateCount:0,
      companyCount:savedGroups.company.length,
      publicCount:savedGroups.public.length,
      activeId:activeId||'hermes-ui'
    }}));
  }

  loadApps();
})();
