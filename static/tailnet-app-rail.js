(function(){
  'use strict';

  const CONFIG_PATH='static/tailnet-apps.json';
  const MAX_APPS=20;
  const STORAGE_KEY='hermesui.tailnet-app';
  const ICONS={
    pipeline:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="4" width="18" height="16" rx="2"/><path d="M8 4v16M16 4v16M3 10h18"/></svg>',
    apps:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/></svg>',
    draw:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L8 18l-4 1 1-4z"/></svg>',
    browser:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18"/></svg>',
    terminal:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="4" width="18" height="16" rx="2"/><path d="m7 9 3 3-3 3M13 15h4"/></svg>',
    monitor:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="2.5" y="3.5" width="19" height="13" rx="2"/><path d="M8 20h8M12 16.5V20"/></svg>',
    link:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M10 13a5 5 0 0 0 7.5.5l2-2a5 5 0 0 0-7-7l-1.1 1.1"/><path d="M14 11a5 5 0 0 0-7.5-.5l-2 2a5 5 0 0 0 7 7l1.1-1.1"/></svg>'
  };

  const root=document.documentElement;
  const workspace=document.getElementById('tailnetAppWorkspace');
  const frame=document.getElementById('tailnetAppFrame');
  const home=document.getElementById('tailnetAppHome');
  const links=document.getElementById('tailnetAppLinks');
  const appsById=new Map();
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

  function closeSessionsOverlay(){
    if(typeof window.closeMobileSidebar==='function')window.closeMobileSidebar();
  }

  function markSelected(id){
    const externalLinks=links?links.querySelectorAll('[data-tailnet-app-id]'):[];
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

  function shouldOpenDirectly(event){
    return event.button!==0||event.metaKey||event.ctrlKey||event.shiftKey||event.altKey;
  }

  function renderApp(container,app){
    const link=document.createElement('a');
    link.className='rail-btn tailnet-app-link has-tooltip';
    link.href=app.href;
    link.target='_blank';
    link.rel='noopener noreferrer';
    link.dataset.tailnetAppId=app.id;
    link.dataset.tooltip=app.label;
    link.setAttribute('aria-label',app.label);
    link.addEventListener('click',event=>{
      if(shouldOpenDirectly(event))return;
      event.preventDefault();
      activateApp(app);
    });
    const icon=document.createElement('span');
    icon.className='tailnet-app-icon';
    icon.setAttribute('aria-hidden','true');
    icon.innerHTML=ICONS[app.icon];
    link.appendChild(icon);
    container.appendChild(link);
  }

  async function loadApps(){
    if(!links||!home||!workspace||!frame)return;
    root.setAttribute('data-tailnet-view','hermes');
    home.addEventListener('click',event=>{
      if(shouldOpenDirectly(event))return;
      event.preventDefault();
      activateHermes();
    });
    let rendered=0;
    try{
      const response=await fetch(new URL(CONFIG_PATH,document.baseURI||location.href).href,{cache:'no-store',credentials:'same-origin'});
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
    }catch(_){}
    let remembered='';
    try{remembered=sessionStorage.getItem(STORAGE_KEY)||'';}catch(_){}
    if(remembered&&appsById.has(remembered))activateApp(appsById.get(remembered));
    else activateHermes({remember:false});
    document.dispatchEvent(new CustomEvent('hermesui:tailnet-apps-ready',{detail:{count:rendered+1,activeId:activeId||'hermes-ui'}}));
  }

  loadApps();
})();
