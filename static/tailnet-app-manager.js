(function(){
  'use strict';

  const MANAGER_ID='private-app-manager';
  const STATUS_PATH='/apps/api/status';
  const PRIVATE_APPS_PATH='/apps/api/private-apps';
  const STORAGE_KEY='hermesui.tailnet-app';
  const BLOCKED_PATHS=new Set(['/','/apps','/hermesUI','/frame-check','/tailnet-frame','/hermes-sidepanel']);
  const GENERIC_ICON='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/></svg>';

  const root=document.documentElement;
  const workspace=document.getElementById('tailnetAppWorkspace');
  const frame=document.getElementById('tailnetAppFrame');
  const panel=document.getElementById('tailnetAppManager');
  const managerButton=document.getElementById('tailnetPrivateManager');
  const refreshButton=document.getElementById('tailnetAppManagerRefresh');
  const originLink=document.getElementById('tailnetAppManagerOrigin');
  const notice=document.getElementById('tailnetAppManagerNotice');
  const list=document.getElementById('tailnetAppManagerList');
  const hiddenPanel=document.getElementById('tailnetAppManagerHidden');
  const hiddenCount=document.getElementById('tailnetAppManagerHiddenCount');
  const hiddenList=document.getElementById('tailnetAppManagerHiddenList');
  const privateLinks=document.getElementById('tailnetAppLinks');
  if(!workspace||!frame||!panel||!managerButton||!refreshButton||!originLink||!notice||!list||!hiddenPanel||!hiddenCount||!hiddenList||!privateLinks)return;

  const nodeUrl=new URL('/',location.origin);
  originLink.href=nodeUrl.href;
  originLink.textContent=nodeUrl.href;

  let approvedApps=[];
  let statusPayload=null;
  let lastStatusAt=0;
  let busy=false;

  function notify(message){
    if(typeof window.showToast==='function')window.showToast(message);
  }

  function setNotice(message,{error=false}={}){
    notice.textContent=message;
    notice.classList.toggle('is-error',error);
  }

  function markSelected(id){
    document.querySelectorAll('.tailnet-app-rail [data-tailnet-app-id]').forEach(node=>{
      const selected=node.dataset.tailnetAppId===id;
      node.classList.toggle('active',selected);
      if(selected)node.setAttribute('aria-current','page');
      else node.removeAttribute('aria-current');
    });
    const home=document.getElementById('tailnetAppHome');
    if(home){
      home.classList.toggle('active',!id);
      if(!id)home.setAttribute('aria-current','page');
      else home.removeAttribute('aria-current');
    }
  }

  function cleanApprovedApp(raw){
    if(!raw||typeof raw!=='object')return null;
    const id=typeof raw.id==='string'?raw.id.trim():'';
    const label=typeof raw.label==='string'?raw.label.trim():'';
    const sourceKey=typeof raw.sourceKey==='string'?raw.sourceKey.trim():'';
    const rawHref=typeof raw.href==='string'?raw.href.trim():'';
    const rawFrameHref=typeof raw.frameHref==='string'?raw.frameHref.trim():'';
    if(!/^[a-z0-9][a-z0-9-]{0,39}$/.test(id)||!label||label.length>48||!sourceKey||sourceKey.length>500||!rawHref||!rawFrameHref)return null;
    let href;
    let frameHref;
    try{
      href=new URL(rawHref,location.origin);
      frameHref=new URL(rawFrameHref,location.origin);
    }catch(_){return null;}
    if(
      href.origin!==location.origin
      || frameHref.origin!==location.origin
      || href.username
      || href.password
      || frameHref.username
      || frameHref.password
    )return null;
    return {id,label,sourceKey,href:href.href,frameHref:frameHref.href,icon:typeof raw.icon==='string'?raw.icon:'apps'};
  }

  function openPrivateApp(app){
    if(!app)return;
    panel.hidden=true;
    frame.hidden=false;
    frame.dataset.tailnetAppId=app.id;
    frame.dataset.tailnetFrameKey=`app:${app.id}`;
    delete frame.dataset.browserFallback;
    frame.title=app.label;
    if(frame.src!==app.frameHref)frame.src=app.frameHref;
    workspace.setAttribute('aria-label',app.label);
    workspace.hidden=false;
    root.setAttribute('data-tailnet-view','external');
    markSelected(app.id);
    try{sessionStorage.setItem(STORAGE_KEY,app.id);}catch(_){}
    document.dispatchEvent(new CustomEvent('hermesui:tailnet-app-selected',{detail:{id:app.id,label:app.label,mode:'inline'}}));
  }

  function renderApprovedApps(){
    privateLinks.querySelectorAll('[data-private-dynamic="true"]').forEach(node=>node.remove());
    const occupiedIds=new Set(
      Array.from(privateLinks.querySelectorAll('[data-tailnet-app-id]:not([data-private-dynamic="true"])'))
        .map(node=>node.dataset.tailnetAppId)
        .filter(Boolean)
    );
    const occupiedSourceKeys=new Set(
      Array.from(privateLinks.querySelectorAll('[data-tailnet-app-source-key]:not([data-private-dynamic="true"])'))
        .map(node=>node.dataset.tailnetAppSourceKey)
        .filter(Boolean)
    );
    approvedApps.forEach(app=>{
      if(occupiedIds.has(app.id)||occupiedSourceKeys.has(app.sourceKey))return;
      const button=document.createElement('button');
      button.className='rail-btn tailnet-app-link has-tooltip';
      button.type='button';
      button.dataset.tailnetAppId=app.id;
      button.dataset.tailnetAppSourceKey=app.sourceKey;
      button.dataset.privateDynamic='true';
      button.dataset.tooltip=app.label;
      button.setAttribute('aria-label',app.label);
      const icon=document.createElement('span');
      icon.className='tailnet-app-icon';
      icon.setAttribute('aria-hidden','true');
      icon.innerHTML=GENERIC_ICON;
      button.appendChild(icon);
      button.addEventListener('click',()=>openPrivateApp(app));
      privateLinks.appendChild(button);
    });
  }

  async function loadApprovedApps(){
    try{
      const response=await fetch(new URL(PRIVATE_APPS_PATH,location.origin),{cache:'no-store',credentials:'same-origin'});
      if(!response.ok)throw new Error(`HTTP ${response.status}`);
      const payload=await response.json();
      approvedApps=(Array.isArray(payload&&payload.apps)?payload.apps:[]).map(cleanApprovedApp).filter(Boolean);
      renderApprovedApps();
      if(statusPayload)renderStatus();
      const remembered=(()=>{try{return sessionStorage.getItem(STORAGE_KEY)||'';}catch(_){return '';}})();
      const rememberedApp=approvedApps.find(app=>app.id===remembered);
      if(rememberedApp)openPrivateApp(rememberedApp);
      return true;
    }catch(_){
      approvedApps=[];
      renderApprovedApps();
      if(statusPayload)renderStatus();
      return false;
    }
  }

  function activateManager(){
    frame.hidden=true;
    panel.hidden=false;
    workspace.setAttribute('aria-label','Manage private apps');
    workspace.hidden=false;
    root.setAttribute('data-tailnet-view','external');
    markSelected(MANAGER_ID);
    try{sessionStorage.setItem(STORAGE_KEY,MANAGER_ID);}catch(_){}
    document.dispatchEvent(new CustomEvent('hermesui:tailnet-app-selected',{detail:{id:MANAGER_ID,label:'Detected',mode:'native'}}));
    void loadStatus();
  }

  function parsedAppUrl(app){
    try{return new URL(app&&app.publicUrl||'');}catch(_){return null;}
  }

  function appIsCurrentNode(app){
    const url=parsedAppUrl(app);
    return Boolean(url&&url.origin===location.origin);
  }

  function appIsEligible(app){
    const url=parsedAppUrl(app);
    if(!url||url.origin!==location.origin)return false;
    const path=String(app&&app.path||url.pathname).replace(/\/$/,'')||'/';
    return !BLOCKED_PATHS.has(path);
  }

  function pinnedApps(){
    const nodes=Array.from(privateLinks.querySelectorAll('[data-tailnet-app-id]:not([data-private-dynamic="true"])'));
    return {
      ids:new Set(nodes.map(node=>node.dataset.tailnetAppId).filter(id=>id&&id!=='apps-manager')),
      sourceKeys:new Set(nodes.map(node=>node.dataset.tailnetAppSourceKey).filter(Boolean))
    };
  }

  function approvedKeys(){return new Set(approvedApps.map(app=>app.sourceKey));}

  function managedHiddenRoutes(){
    const routes=statusPayload&&statusPayload.serve&&statusPayload.serve.hiddenRoutes;
    if(!Array.isArray(routes))return [];
    const seen=new Set();
    return routes.filter(route=>{
      const path=route&&typeof route.path==='string'?route.path.trim():'';
      if(!path||seen.has(path))return false;
      seen.add(path);
      return true;
    });
  }

  function renderHiddenRoutes(){
    const routes=managedHiddenRoutes();
    hiddenCount.textContent=String(routes.length);
    hiddenPanel.hidden=!routes.length;
    hiddenList.replaceChildren();
    routes.forEach(route=>{
      const row=document.createElement('div');
      row.className='tailnet-hidden-route';
      const copy=document.createElement('div');
      copy.className='tailnet-hidden-route-copy';
      const name=document.createElement('strong');
      name.textContent=String(route.name||route.path||'Internal route');
      const description=document.createElement('span');
      description.textContent=String(route.description||'Internal Tailnet route');
      const path=document.createElement('code');
      path.textContent=String(route.path||'');
      copy.append(name,description);
      row.append(copy,path);
      hiddenList.appendChild(row);
    });
  }

  function managedApps(){
    if(!statusPayload||!Array.isArray(statusPayload.apps))return [];
    const seen=new Set();
    return statusPayload.apps.filter(app=>{
      if(!app||!app.actionKey||seen.has(app.actionKey)||!appIsCurrentNode(app))return false;
      seen.add(app.actionKey);
      const path=String(app.path||'').replace(/\/$/,'')||'/';
      if(BLOCKED_PATHS.has(path))return false;
      return appIsCurrentNode(app);
    }).sort((left,right)=>String(left.name||left.path).localeCompare(String(right.name||right.path)));
  }

  function button(label,handler,{primary=false,active=false,disabled=false,title=''}={}){
    const node=document.createElement('button');
    node.type='button';
    node.className=`btn ${primary?'primary':'secondary'}${active?' private-active':''}`;
    node.textContent=label;
    if(title){node.title=title;node.setAttribute('aria-label',title);}
    node.disabled=disabled||busy;
    node.addEventListener('click',handler);
    return node;
  }

  async function postJson(path,payload){
    const response=await fetch(new URL(path,location.origin),{
      method:'POST',
      credentials:'same-origin',
      cache:'no-store',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify(payload)
    });
    let body={};
    try{body=await response.json();}catch(_){}
    if(!response.ok||body.ok===false)throw new Error(body.error||`HTTP ${response.status}`);
    return body;
  }

  async function changePrivateApp(app,action){
    if(busy)return;
    busy=true;
    renderStatus();
    try{
      await postJson(PRIVATE_APPS_PATH,{action,appId:app.actionKey});
      await loadApprovedApps();
      setNotice(`${managedApps().length} app${managedApps().length===1?'':'s'}`);
      notify(action==='approve'?'Added to PRIVATE.':'Removed from PRIVATE.');
    }catch(error){
      setNotice(error.message||'The PRIVATE list could not be changed.',{error:true});
    }finally{
      busy=false;
      renderStatus();
    }
  }

  async function runAction(app,action,extra={}){
    const labels={restart:'restart',update:'update'};
    const verb=labels[action]||action;
    if(!window.confirm(`Confirm ${verb} for ${app.name||app.path}?`))return;
    if(busy)return;
    busy=true;
    renderStatus();
    try{
      await postJson('/apps/api/action',{appId:app.actionKey,action,...extra});
      setNotice(`${verb} requested`);
      notify(`${app.name||app.path}: ${verb} accepted.`);
      await loadStatus({force:true});
    }catch(error){
      setNotice(error.message||`${verb} failed.`,{error:true});
    }finally{
      busy=false;
      renderStatus();
    }
  }

  function renderStatus(){
    const apps=managedApps();
    const pinned=pinnedApps();
    const approved=approvedKeys();
    renderHiddenRoutes();
    list.replaceChildren();
    if(!apps.length){
      const empty=document.createElement('div');
      empty.className='tailnet-managed-app-empty';
      empty.textContent=statusPayload?'No apps':'Loading…';
      list.appendChild(empty);
      return;
    }
    apps.forEach(app=>{
      const card=document.createElement('article');
      card.className='tailnet-managed-app';
      const top=document.createElement('div');
      top.className='tailnet-managed-app-top';
      const icon=document.createElement('span');
      icon.className='tailnet-managed-app-icon';
      icon.setAttribute('aria-hidden','true');
      icon.innerHTML=GENERIC_ICON;
      const copy=document.createElement('div');
      copy.className='tailnet-managed-app-copy';
      const name=document.createElement('strong');
      name.textContent=String(app.name||app.path||'Tailnet app');
      const route=document.createElement('code');
      route.textContent=String(app.path||parsedAppUrl(app)?.pathname||'');
      copy.append(name,route);
      const health=document.createElement('span');
      health.className=`tailnet-managed-app-health ${app.healthOk?'is-up':(app.healthCode?'is-down':'')}`.trim();
      health.title=app.healthOk?'Available':(app.healthCode?'Unavailable':'Status unknown');
      top.append(icon,copy,health);
      const isPinned=pinned.ids.has(app.id)||pinned.sourceKeys.has(app.actionKey);
      const isApproved=approved.has(app.actionKey);
      const actions=document.createElement('div');
      actions.className='tailnet-managed-app-actions';
      if(appIsEligible(app)){
        if(isPinned)actions.appendChild(button('Added',()=>{}, {active:true,disabled:true,title:`${app.name||app.path} is in PRIVATE`}));
        else if(isApproved)actions.appendChild(button('Remove',()=>void changePrivateApp(app,'remove'),{active:true,title:`Remove ${app.name||app.path} from PRIVATE`}));
        else actions.appendChild(button('Add',()=>void changePrivateApp(app,'approve'),{primary:true,title:`Add ${app.name||app.path} to PRIVATE`}));
      }
      if(app.canRestart)actions.appendChild(button('Restart',()=>void runAction(app,'restart'),{title:`Restart ${app.name||app.path} now`}));
      if(app.canUpdate)actions.appendChild(button('Update',()=>void runAction(app,'update'),{title:`Update ${app.name||app.path}`}));
      card.append(top,actions);
      list.appendChild(card);
    });
  }

  async function loadStatus({force=false}={}){
    if(busy)return;
    if(!force&&statusPayload&&Date.now()-lastStatusAt<30000){renderStatus();return;}
    refreshButton.disabled=true;
    setNotice('Loading…');
    if(!statusPayload)renderStatus();
    try{
      const endpoint=new URL(STATUS_PATH,location.origin);
      if(force)endpoint.searchParams.set('refresh','1');
      const response=await fetch(endpoint,{cache:'no-store',credentials:'same-origin'});
      if(!response.ok)throw new Error(`HTTP ${response.status}`);
      const payload=await response.json();
      if(!payload||payload.ok!==true||!Array.isArray(payload.apps))throw new Error('Invalid controller response');
      statusPayload=payload;
      lastStatusAt=Date.now();
      const apps=managedApps();
      setNotice(`${apps.length} app${apps.length===1?'':'s'}`);
      renderStatus();
    }catch(error){
      setNotice(`Unavailable: ${error.message||error}`,{error:true});
      statusPayload={ok:false,apps:[]};
      renderStatus();
    }finally{
      refreshButton.disabled=false;
    }
  }

  managerButton.addEventListener('click',activateManager);
  refreshButton.addEventListener('click',()=>void loadStatus({force:true}));
  document.addEventListener('hermesui:tailnet-app-selected',event=>{
    const id=event&&event.detail&&event.detail.id;
    if(id===MANAGER_ID)return;
    panel.hidden=true;
    if(id&&id!=='hermes-ui')frame.hidden=false;
  });
  let initialPrivateSyncStarted=false;
  function syncInitialPrivateApps(){
    if(initialPrivateSyncStarted)return;
    initialPrivateSyncStarted=true;
    void loadApprovedApps().then(()=>{
      let remembered='';
      try{remembered=sessionStorage.getItem(STORAGE_KEY)||'';}catch(_){}
      if(remembered===MANAGER_ID)activateManager();
    });
  }
  document.addEventListener('hermesui:tailnet-apps-ready',syncInitialPrivateApps);
  if(root.dataset.tailnetAppsReady==='true')syncInitialPrivateApps();
})();
