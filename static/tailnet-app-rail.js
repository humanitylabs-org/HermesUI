(function(){
  'use strict';

  const CONFIG_PATH='static/tailnet-apps.json';
  const MAX_APPS=20;
  const ICONS={
    pipeline:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="4" width="18" height="16" rx="2"/><path d="M8 4v16M16 4v16M3 10h18"/></svg>',
    apps:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/></svg>',
    draw:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L8 18l-4 1 1-4z"/></svg>',
    browser:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18"/></svg>',
    terminal:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="4" width="18" height="16" rx="2"/><path d="m7 9 3 3-3 3M13 15h4"/></svg>',
    monitor:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="2.5" y="3.5" width="19" height="13" rx="2"/><path d="M8 20h8M12 16.5V20"/></svg>',
    link:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M10 13a5 5 0 0 0 7.5.5l2-2a5 5 0 0 0-7-7l-1.1 1.1"/><path d="M14 11a5 5 0 0 0-7.5-.5l-2 2a5 5 0 0 0 7 7l1.1-1.1"/></svg>'
  };

  function cleanApp(raw){
    if(!raw||typeof raw!=='object'||raw.enabled===false)return null;
    const id=typeof raw.id==='string'?raw.id.trim():'';
    const label=typeof raw.label==='string'?raw.label.trim():'';
    if(!/^[a-z0-9][a-z0-9-]{0,39}$/.test(id)||!label||label.length>48)return null;
    let url;
    try{url=new URL(raw.href,document.baseURI||location.href);}catch(_){return null;}
    if(url.protocol!=='https:'&&url.origin!==location.origin)return null;
    return {id,label,href:url.href,icon:ICONS[raw.icon]?raw.icon:'link'};
  }

  function renderApp(container,app){
    const link=document.createElement('a');
    link.className='rail-btn tailnet-app-link has-tooltip';
    link.href=app.href;
    link.target='_blank';
    link.rel='noopener noreferrer';
    link.dataset.tailnetAppId=app.id;
    link.dataset.tooltip=app.label+' · opens in a new tab';
    link.setAttribute('aria-label',app.label+' (opens in a new tab)');
    const icon=document.createElement('span');
    icon.className='tailnet-app-icon';
    icon.setAttribute('aria-hidden','true');
    icon.innerHTML=ICONS[app.icon];
    link.appendChild(icon);
    container.appendChild(link);
  }

  async function loadApps(){
    const container=document.getElementById('tailnetAppLinks');
    if(!container)return;
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
          renderApp(container,app);
          rendered+=1;
        });
      }
    }catch(_){}
    document.dispatchEvent(new CustomEvent('hermesui:tailnet-apps-ready',{detail:{count:rendered+1}}));
  }

  loadApps();
})();