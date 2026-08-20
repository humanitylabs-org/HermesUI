(function(){
  'use strict';

  const CONFIG_PATH='static/tailnet-apps.json';
  const MAX_APPS=20;
  const MAX_BOOKMARKS_PER_GROUP=20;
  const STORAGE_KEY='hermesui.tailnet-app';
  const BOOKMARK_STORAGE_KEY='hermesui.app-selector.bookmarks.v1';
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
    href:'https://humanitylabs.org/',
    frameHref:new URL('/tailnet-frame/?app=private-marketplace',location.origin).href,
    icon:'apps'
  };
  const appsById=new Map();
  let savedGroups={company:[],public:[]};
  let activeId='';

  function cleanApp(raw){
    if(!raw||typeof raw!=='object'||raw.enabled===false)return null;
    const id=typeof raw.id==='string'?raw.id.trim():'';
    const label=typeof raw.label==='string'?raw.label.trim():'';
    const href=typeof raw.href==='string'?raw.href.trim():'';
    const frameHref=typeof raw.frameHref==='string'?raw.frameHref.trim():'';
    if(!/^[a-z0-9][a-z0-9-]{0,39}$/.test(id)||!label||label.length>48)return null;
    if(!href||!frameHref)return null;
    let url;
    let frameUrl;
    try{
      url=new URL(href,document.baseURI||location.href);
      frameUrl=new URL(frameHref,location.origin);
    }catch(_){return null;}
    if(url.protocol!=='https:'&&url.origin!==location.origin)return null;
    if(frameUrl.origin!==location.origin)return null;
    return {id,label,href:url.href,frameHref:frameUrl.href,icon:ICONS[raw.icon]?raw.icon:'link'};
  }

  function normalizeBookmarkUrl(raw){
    let value=typeof raw==='string'?raw.trim():'';
    if(!value)return '';
    if(!URL_SCHEME_RE.test(value))value=`https://${value}`;
    let url;
    try{url=new URL(value);}catch(_){return '';}
    if(url.protocol!=='https:'||url.username||url.password)return '';
    return url.href;
  }

  function cleanBookmark(raw,group){
    if(!GROUPS[group]||!raw||typeof raw!=='object')return null;
    const id=typeof raw.id==='string'?raw.id.trim():'';
    const label=typeof raw.label==='string'?raw.label.trim():'';
    const href=normalizeBookmarkUrl(raw.href);
    if(!/^[a-z0-9][a-z0-9-]{0,39}$/.test(id)||!label||label.length>48||!href)return null;
    const frameHref=new URL(`/tailnet-frame/?bookmark=${encodeURIComponent(`${group}:${id}`)}`,location.origin).href;
    return {id,label,href,frameHref,icon:GROUPS[group].icon};
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

  function activateHermes({remember=true}={}){
    activeId='';
    root.setAttribute('data-tailnet-view','hermes');
    if(workspace)workspace.hidden=true;
    markSelected('');
    closeSessionsOverlay();
    if(remember){
      try{sessionStorage.removeItem(STORAGE_KEY);}catch(_){}
    }
    document.dispatchEvent(new CustomEvent('hermesui:tailnet-app-selected',{detail:{id:'hermes-ui'}}));
  }

  function activateApp(app){
    if(!workspace||!frame)return;
    activeId=app.id;
    if(frame.dataset.tailnetAppId!==app.id){
      frame.dataset.tailnetAppId=app.id;
      frame.title=app.label;
      frame.src=app.frameHref;
    }
    workspace.setAttribute('aria-label',app.label);
    workspace.hidden=false;
    root.setAttribute('data-tailnet-view','external');
    markSelected(app.id);
    closeSessionsOverlay();
    try{sessionStorage.setItem(STORAGE_KEY,app.id);}catch(_){}
    document.dispatchEvent(new CustomEvent('hermesui:tailnet-app-selected',{detail:{id:app.id,label:app.label}}));
  }


  function appIcon(name){
    const icon=document.createElement('span');
    icon.className='tailnet-app-icon';
    icon.setAttribute('aria-hidden','true');
    icon.innerHTML=ICONS[name]||ICONS.link;
    return icon;
  }

  function renderApp(container,app){
    const link=document.createElement('button');
    link.className='rail-btn tailnet-app-link has-tooltip';
    link.type='button';
    link.dataset.tailnetAppId=app.id;
    link.dataset.tooltip=app.label;
    link.setAttribute('aria-label',app.label);
    link.addEventListener('click',()=>activateApp(app));
    link.appendChild(appIcon(app.icon));
    container.appendChild(link);
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
    link.addEventListener('click',()=>activateApp(app));
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
      document.dispatchEvent(new CustomEvent('hermesui:app-bookmarks-changed',{detail:{group,count:savedGroups[group].length}}));
    }finally{
      button.disabled=false;
    }
  }

  async function loadApps(){
    if(!links||!home||!workspace||!frame||!companyLinks||!publicLinks||!privateAdd||!companyAdd||!publicAdd)return;
    root.setAttribute('data-tailnet-view','hermes');
    home.addEventListener('click',event=>{
      event.preventDefault();
      activateHermes();
    });
    appsById.set(privateMarketplace.id,privateMarketplace);
    privateAdd.addEventListener('click',()=>activateApp(privateMarketplace));
    companyAdd.addEventListener('click',()=>void addSavedApp('company'));
    publicAdd.addEventListener('click',()=>void addSavedApp('public'));
    savedGroups=readSavedGroups();
    renderSavedGroup('company');
    renderSavedGroup('public');
    let rendered=0;
    const controller=typeof AbortController==='function'?new AbortController():null;
    const timeout=controller?setTimeout(()=>controller.abort(),2500):null;
    try{
      const options={cache:'no-store',credentials:'same-origin'};
      if(controller)options.signal=controller.signal;
      const response=await fetch(new URL(CONFIG_PATH,document.baseURI||location.href).href,options);
      if(response.ok){
        const payload=await response.json();
        const seen=new Set();
        const apps=Array.isArray(payload&&payload.apps)?payload.apps:[];
        apps.slice(0,MAX_APPS).forEach(raw=>{
          const app=cleanApp(raw);
          if(!app||seen.has(app.id))return;
          seen.add(app.id);
          appsById.set(app.id,app);
          renderApp(links,app);
          rendered+=1;
        });
      }
    }catch(_){}finally{if(timeout)clearTimeout(timeout);}
    let remembered='';
    try{remembered=sessionStorage.getItem(STORAGE_KEY)||'';}catch(_){}
    if(remembered&&appsById.has(remembered))activateApp(appsById.get(remembered));
    else activateHermes({remember:false});
    root.dataset.tailnetAppsReady='true';
    document.dispatchEvent(new CustomEvent('hermesui:tailnet-apps-ready',{detail:{
      count:rendered+savedGroups.company.length+savedGroups.public.length+2,
      privateCount:rendered,
      companyCount:savedGroups.company.length,
      publicCount:savedGroups.public.length,
      activeId:activeId||'hermes-ui'
    }}));
  }

  loadApps();
})();
