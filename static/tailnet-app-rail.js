(function(){
  'use strict';

  const MAX_BOOKMARKS_PER_GROUP=20;
  const STORAGE_KEY='hermesui.tailnet-app';
  const BOOKMARK_STORAGE_KEY='hermesui.app-selector.bookmarks.v1';
  const BOOKMARK_API_PATH='/apps/api/bookmarks';
  const FRAME_DECISION_STORAGE_KEY='hermesui.app-selector.frame-decisions.v1';
  const FRAME_CHECK_PATH='/frame-check/';
  const FRAME_INLINE_DECISION_TTL_MS=6*60*60*1000;
  const FRAME_BROWSER_DECISION_TTL_MS=5*60*1000;
  const BROWSER_FALLBACK_DELAY_MS=3000;
  const NOTIFICATIONS_ID='cron-notifications';
  const NOTIFICATION_STATE_KEY='hermesui.cron-notifications.v1';
  const NOTIFICATION_OUTPUT_LIMIT=4;
  const NOTIFICATION_LIST_LIMIT=40;
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
  const notificationsPanel=document.getElementById('tailnetNotifications');
  const notificationsButton=document.getElementById('tailnetNotificationsButton');
  const notificationsBadge=document.getElementById('tailnetNotificationsBadge');
  const notificationsStatus=document.getElementById('tailnetNotificationsStatus');
  const notificationsList=document.getElementById('tailnetNotificationsList');
  const notificationsReadAll=document.getElementById('tailnetNotificationsReadAll');
  const notificationFilterButtons=Array.from(document.querySelectorAll('[data-notification-filter]'));
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
  let browserFallbackTimer=null;
  let browserFallbackSequence=0;
  let bookmarkRevision=0;
  let bookmarkServerAvailable=false;
  let bookmarkSyncPromise=Promise.resolve();
  let notificationState=readNotificationState();
  let notificationItems=new Map();
  let notificationsLoading=false;
  let notificationFilter='unread';


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
    const frameHref=new URL(`/tailnet-frame/?bookmark=${encodeURIComponent(`${group}:${id}`)}&handoff=countdown-v3`,location.origin).href;
    const browserHref=new URL(`/tailnet-frame/?browser=${encodeURIComponent(`${group}:${id}`)}&handoff=countdown-v3`,location.origin).href;
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

  function cleanSavedGroupsPayload(payload){
    const result=emptySavedGroups();
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
    return result;
  }

  function readSavedGroups(){
    try{
      return cleanSavedGroupsPayload(JSON.parse(localStorage.getItem(BOOKMARK_STORAGE_KEY)||'null'));
    }catch(_){return emptySavedGroups();}
  }

  function serializedSavedGroups(groups=savedGroups){
    const serialize=app=>({id:app.id,label:app.label,href:app.href});
    return {
      company:groups.company.map(serialize),
      public:groups.public.map(serialize)
    };
  }

  function writeSavedGroups(groups=savedGroups){
    try{
      const serialized=serializedSavedGroups(groups);
      localStorage.setItem(BOOKMARK_STORAGE_KEY,JSON.stringify({version:1,...serialized}));
      return true;
    }catch(_){return false;}
  }

  function cloneSavedGroups(groups=savedGroups){
    const serialized=serializedSavedGroups(groups);
    return cleanSavedGroupsPayload({version:1,...serialized});
  }

  function savedBookmarkCount(groups=savedGroups){
    return groups.company.length+groups.public.length;
  }

  function installSavedGroups(groups,{cache=true}={}){
    const oldIds=[...savedGroups.company,...savedGroups.public].map(app=>app.id);
    const activeWasBookmark=oldIds.includes(activeId);
    oldIds.forEach(id=>appsById.delete(id));
    savedGroups=cloneSavedGroups(groups);
    if(cache)writeSavedGroups();
    renderSavedGroup('company');
    renderSavedGroup('public');
    if(activeWasBookmark&&!bookmarkFor('company',activeId)&&!bookmarkFor('public',activeId))activateHermes();
  }

  function parseBookmarkRecord(payload){
    if(
      !payload||payload.ok!==true||payload.version!==1||
      !Number.isSafeInteger(payload.revision)||payload.revision<0||
      typeof payload.initialized!=='boolean'||
      !payload.bookmarks||typeof payload.bookmarks!=='object'
    )throw new Error('invalid bookmark sync response');
    if(payload.initialized!==(payload.revision>0))throw new Error('inconsistent bookmark sync response');
    return {
      revision:payload.revision,
      initialized:payload.initialized,
      groups:cleanSavedGroupsPayload({version:1,...payload.bookmarks})
    };
  }

  async function fetchBookmarkRecord(){
    const response=await fetch(new URL(BOOKMARK_API_PATH,location.origin).href,{
      cache:'no-store',
      credentials:'same-origin'
    });
    if(!response.ok)throw new Error(`bookmark sync failed (${response.status})`);
    return parseBookmarkRecord(await response.json());
  }

  async function putBookmarkRecord(groups=savedGroups){
    const response=await fetch(new URL(BOOKMARK_API_PATH,location.origin).href,{
      method:'PUT',
      cache:'no-store',
      credentials:'same-origin',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({baseRevision:bookmarkRevision,bookmarks:serializedSavedGroups(groups)})
    });
    if(!response.ok){
      const error=new Error(`bookmark sync failed (${response.status})`);
      error.status=response.status;
      throw error;
    }
    return parseBookmarkRecord(await response.json());
  }

  async function hydrateSavedGroups(){
    try{
      let record=await fetchBookmarkRecord();
      bookmarkServerAvailable=true;
      bookmarkRevision=record.revision;
      if(!record.initialized&&savedBookmarkCount(savedGroups)>0){
        try{
          record=await putBookmarkRecord(savedGroups);
        }catch(error){
          if(error&&error.status===409)record=await fetchBookmarkRecord();
          else throw error;
        }
      }
      bookmarkRevision=record.revision;
      if(record.initialized)installSavedGroups(record.groups);
      return true;
    }catch(_){
      bookmarkServerAvailable=false;
      return false;
    }
  }

  async function ensureBookmarkSync(){
    await bookmarkSyncPromise;
    if(bookmarkServerAvailable)return true;
    bookmarkSyncPromise=hydrateSavedGroups();
    await bookmarkSyncPromise;
    if(bookmarkServerAvailable)return true;
    notify('Bookmark sync is unavailable. Try again when this Tailnet server is reachable.');
    return false;
  }

  async function commitSavedGroups(previous){
    writeSavedGroups();
    try{
      const record=await putBookmarkRecord(savedGroups);
      bookmarkRevision=record.revision;
      bookmarkServerAvailable=true;
      installSavedGroups(record.groups);
      return true;
    }catch(error){
      if(error&&error.status===409){
        try{
          const current=await fetchBookmarkRecord();
          bookmarkRevision=current.revision;
          bookmarkServerAvailable=true;
          installSavedGroups(current.groups);
        }catch(_){
          bookmarkServerAvailable=false;
          installSavedGroups(previous);
        }
        notify('Bookmarks changed on another device. Please try again.');
      }else{
        bookmarkServerAvailable=false;
        installSavedGroups(previous);
        notify('That change could not be synced. Please try again.');
      }
      return false;
    }
  }

  function readNotificationState(){
    try{
      const raw=JSON.parse(localStorage.getItem(NOTIFICATION_STATE_KEY)||'null');
      if(raw&&raw.version===1&&Number.isFinite(Number(raw.readThrough))&&raw.readJobs&&typeof raw.readJobs==='object'){
        const readJobs={};
        Object.entries(raw.readJobs).slice(-80).forEach(([id,value])=>{
          const timestamp=Number(value);
          if(id&&Number.isFinite(timestamp)&&timestamp>0)readJobs[id]=timestamp;
        });
        return {version:1,readThrough:Number(raw.readThrough),readJobs};
      }
    }catch(_){}
    const initial={version:1,readThrough:Date.now()/1000,readJobs:{}};
    try{localStorage.setItem(NOTIFICATION_STATE_KEY,JSON.stringify(initial));}catch(_){}
    return initial;
  }

  function writeNotificationState(){
    try{
      const entries=Object.entries(notificationState.readJobs)
        .sort(([,left],[,right])=>Number(right)-Number(left))
        .slice(0,80);
      notificationState.readJobs=Object.fromEntries(entries);
      localStorage.setItem(NOTIFICATION_STATE_KEY,JSON.stringify(notificationState));
    }catch(_){}
  }

  function notificationReadCutoff(jobId){
    return Math.max(Number(notificationState.readThrough)||0,Number(notificationState.readJobs[jobId])||0);
  }

  function notificationIsUnread(item){return item.modified>notificationReadCutoff(item.jobId);}

  function notificationStatusText(unreadCount,totalCount){
    if(notificationFilter==='unread')return unreadCount?`${unreadCount} unread`:'All caught up';
    return totalCount?`${totalCount} notification${totalCount===1?'':'s'}`:'No scheduled-job responses yet.';
  }

  function syncNotificationFilterControls(){
    notificationFilterButtons.forEach(button=>{
      const active=button.dataset.notificationFilter===notificationFilter;
      button.classList.toggle('is-active',active);
      button.setAttribute('aria-selected',String(active));
      button.tabIndex=active?0:-1;
    });
  }

  function setNotificationFilter(value){
    notificationFilter=value==='all'?'all':'unread';
    syncNotificationFilterControls();
    renderCronNotifications();
  }

  function setNotificationsBadge(count){
    if(!notificationsBadge||!notificationsButton)return;
    const unread=Math.max(0,Number(count)||0);
    notificationsBadge.textContent=unread>9?'9+':String(unread);
    notificationsBadge.hidden=unread===0;
    notificationsButton.classList.toggle('has-unread',unread>0);
    notificationsButton.setAttribute('aria-label',unread>0?`Notifications, ${unread} unread`:'Notifications');
  }

  function parseCronFilenameTimestamp(filename,fallback=0,index=0){
    const match=String(filename||'').match(/^(\d{4})-(\d{2})-(\d{2})_(\d{2})-(\d{2})-(\d{2})/);
    if(match){
      const parts=match.slice(1).map(Number);
      return Date.UTC(parts[0],parts[1]-1,parts[2],parts[3],parts[4],parts[5])/1000;
    }
    return Math.max(0,Number(fallback)||0)-index;
  }

  function cronResponseText(content){
    const source=String(content||'').replace(/\r\n?/g,'\n').trim();
    if(!source||/^\*\*Status:\*\*\s*silent\b/im.test(source))return '';
    const lines=source.split('\n');
    const responseIndex=lines.findIndex(line=>/^#{1,2}\s+Response\b/i.test(line.trim()));
    const dividerIndex=lines.findIndex(line=>/^---$/.test(line.trim()));
    const body=(responseIndex>=0
      ?lines.slice(responseIndex+1)
      :dividerIndex>=0
        ?lines.slice(dividerIndex+1)
        :lines).join('\n').trim();
    return body.slice(0,8000);
  }

  function cronJobsFromPayload(payload){
    return Array.isArray(payload&&payload.jobs)
      ?payload.jobs.filter(job=>job&&job.id&&!job.read_only)
      :[];
  }

  async function fetchCronNotificationJobs(){
    const payload=await api('/api/crons');
    return cronJobsFromPayload(payload);
  }

  async function fetchCronNotificationOutputs(job){
    const payload=await api(`/api/crons/output?job_id=${encodeURIComponent(job.id)}&limit=${NOTIFICATION_OUTPUT_LIMIT}`);
    const outputs=Array.isArray(payload&&payload.outputs)?payload.outputs:[];
    const fallback=Date.parse(job.last_run_at||'')/1000;
    const items=outputs.map((output,index)=>{
      const filename=String(output.filename||'');
      const modified=parseCronFilenameTimestamp(filename,fallback,index);
      return {
        key:`${job.id}:${filename||modified}`,
        jobId:String(job.id),
        name:String(job.name||job.id),
        filename,
        modified,
        status:index===0?String(job.last_status||'ok'):'ok',
        response:cronResponseText(output.content)
      };
    }).filter(item=>item.response);
    if(!items.length&&job.last_status==='error'&&job.last_error){
      const modified=Number.isFinite(fallback)?fallback:Date.now()/1000;
      items.push({
        key:`${job.id}:error:${modified}`,
        jobId:String(job.id),
        name:String(job.name||job.id),
        filename:'',
        modified,
        status:'error',
        response:`Run failed\n${String(job.last_error).slice(0,8000)}`
      });
    }
    return items;
  }

  async function mapWithConcurrency(items,limit,mapper){
    const results=new Array(items.length);
    let cursor=0;
    async function worker(){
      while(cursor<items.length){
        const index=cursor++;
        try{results[index]=await mapper(items[index],index);}catch(_){results[index]=[];}
      }
    }
    await Promise.all(Array.from({length:Math.min(limit,items.length)},()=>worker()));
    return results;
  }

  function relativeNotificationTime(timestamp){
    if(!Number.isFinite(timestamp)||timestamp<=0)return '';
    const seconds=Math.max(0,Math.round(Date.now()/1000-timestamp));
    if(seconds<60)return 'Just now';
    if(seconds<3600)return `${Math.floor(seconds/60)}m ago`;
    if(seconds<86400)return `${Math.floor(seconds/3600)}h ago`;
    if(seconds<604800)return `${Math.floor(seconds/86400)}d ago`;
    return new Date(timestamp*1000).toLocaleDateString(undefined,{month:'short',day:'numeric'});
  }

  function notificationPreviewText(content){
    return String(content||'')
      .replace(/^\s*MEDIA:\S+\s*$/gim,'')
      .replace(/!\[[^\]]*\]\([^)]*\)/g,'')
      .replace(/\[([^\]]+)\]\([^)]*\)/g,'$1')
      .replace(/^\s{0,3}#{1,6}\s+/gm,'')
      .replace(/[*_~`]+/g,'')
      .replace(/\n{2,}/g,'\n')
      .trim()
      .slice(0,480);
  }

  function hydrateNotificationRich(body,item){
    if(!body||body.dataset.richReady==='1')return;
    body.dataset.richReady='1';
    try{
      if(typeof renderMd==='function')body.innerHTML=renderMd(item.response);
      else body.textContent=item.response;
    }catch(_){body.textContent=item.response;}
    const enhance=()=>{
      if(typeof postProcessRenderedMessages==='function')postProcessRenderedMessages(body);
      else{
        if(typeof highlightCode==='function')highlightCode(body);
        if(typeof addCopyButtons==='function')addCopyButtons(body);
        if(typeof loadPdfInline==='function')loadPdfInline(body);
      }
    };
    if(typeof requestAnimationFrame==='function')requestAnimationFrame(enhance);
    else setTimeout(enhance,0);
  }

  function markNotificationRead(item){
    if(!item)return;
    notificationState.readJobs[item.jobId]=Math.max(Number(notificationState.readJobs[item.jobId])||0,item.modified);
    writeNotificationState();
    const visibleItems=Array.from(notificationItems.values())
      .sort((left,right)=>right.modified-left.modified)
      .slice(0,NOTIFICATION_LIST_LIMIT);
    const unreadCount=visibleItems.filter(notificationIsUnread).length;
    setNotificationsBadge(unreadCount);
    if(notificationsStatus)notificationsStatus.textContent=notificationStatusText(unreadCount,visibleItems.length);
    if(notificationsReadAll)notificationsReadAll.disabled=unreadCount===0;
  }

  function markAllNotificationsRead(){
    const newest=Math.max(Date.now()/1000,...Array.from(notificationItems.values()).map(item=>item.modified));
    notificationState.readThrough=newest;
    notificationState.readJobs={};
    writeNotificationState();
    renderCronNotifications();
  }

  function renderCronNotifications(){
    if(!notificationsList||!notificationsStatus)return;
    const items=Array.from(notificationItems.values())
      .sort((left,right)=>right.modified-left.modified)
      .slice(0,NOTIFICATION_LIST_LIMIT);
    const unreadCount=items.filter(notificationIsUnread).length;
    const visibleItems=notificationFilter==='unread'?items.filter(notificationIsUnread):items;
    setNotificationsBadge(unreadCount);
    syncNotificationFilterControls();
    if(notificationsReadAll)notificationsReadAll.disabled=unreadCount===0;
    notificationsList.replaceChildren();
    if(!items.length){
      notificationsStatus.textContent=notificationsLoading?'Loading…':'No scheduled-job responses yet.';
      return;
    }
    notificationsStatus.textContent=notificationStatusText(unreadCount,items.length);
    if(!visibleItems.length)return;
    visibleItems.forEach((item,index)=>{
      const unread=notificationIsUnread(item);
      const article=document.createElement('article');
      article.className=`tailnet-notification${unread?' is-unread':''}${item.status==='error'?' is-error':''}`;
      article.dataset.role='assistant';
      const role=document.createElement('div');
      role.className='msg-role assistant tailnet-notification-role';
      const icon=document.createElement('div');
      icon.className='role-icon assistant';
      icon.textContent='W';
      icon.setAttribute('aria-hidden','true');
      const name=document.createElement('span');
      name.className='msg-role-name';
      name.textContent=item.name;
      const meta=document.createElement('span');
      meta.className='msg-time tailnet-notification-meta';
      meta.textContent=relativeNotificationTime(item.modified);
      role.append(icon,name,meta);
      const button=document.createElement('button');
      button.type='button';
      button.className='tailnet-notification-toggle';
      button.setAttribute('aria-expanded','false');
      const richId=`tailnetNotificationBody${index}`;
      button.setAttribute('aria-controls',richId);
      button.setAttribute('aria-label',`Open notification from ${item.name}`);
      const response=document.createElement('span');
      response.className='tailnet-notification-response';
      response.textContent=notificationPreviewText(item.response)||'Attachment';
      button.appendChild(response);
      const rich=document.createElement('div');
      rich.id=richId;
      rich.className='tailnet-notification-rich msg-body';
      rich.hidden=true;
      button.addEventListener('click',()=>{
        const open=article.classList.toggle('is-open');
        button.setAttribute('aria-expanded',String(open));
        response.hidden=open;
        rich.hidden=!open;
        if(open)hydrateNotificationRich(rich,item);
        if(notificationIsUnread(item)){
          markNotificationRead(item);
          article.classList.remove('is-unread');
        }
        if(!open&&notificationFilter==='unread'&&!notificationIsUnread(item))renderCronNotifications();
      });
      article.append(role,button,rich);
      notificationsList.appendChild(article);
    });
  }

  async function refreshCronNotificationBadge(){
    try{
      const jobs=await fetchCronNotificationJobs();
      const unread=jobs.reduce((count,job)=>{
        const modified=Date.parse(job.last_run_at||'')/1000;
        return count+(Number.isFinite(modified)&&modified>notificationReadCutoff(String(job.id))?1:0);
      },0);
      if(!notificationItems.size)setNotificationsBadge(unread);
    }catch(_){}
  }

  async function loadCronNotifications({jobIds=null}={}){
    if(notificationsLoading)return;
    notificationsLoading=true;
    if(notificationsStatus&&!notificationItems.size)notificationsStatus.textContent='Loading…';
    try{
      const jobs=await fetchCronNotificationJobs();
      const ids=jobIds?new Set(jobIds.map(String)):null;
      const selected=ids?jobs.filter(job=>ids.has(String(job.id))):jobs;
      if(!ids)notificationItems.clear();
      const batches=await mapWithConcurrency(selected,4,fetchCronNotificationOutputs);
      selected.forEach(job=>{
        const prefix=`${job.id}:`;
        Array.from(notificationItems.keys()).forEach(key=>{if(key.startsWith(prefix))notificationItems.delete(key);});
      });
      batches.flat().forEach(item=>notificationItems.set(item.key,item));
    }catch(_){
      if(notificationsStatus)notificationsStatus.textContent='Notifications are unavailable right now.';
    }finally{
      notificationsLoading=false;
      renderCronNotifications();
    }
  }

  function activateNotifications(){
    if(!workspace||!notificationsPanel)return;
    cancelBrowserFallback();
    hideTooltip();
    closeBookmarkMenu();
    activeId=NOTIFICATIONS_ID;
    activeBookmarkNavigation=null;
    if(frame)frame.hidden=true;
    if(wizardHome)wizardHome.hidden=true;
    if(managerPanel)managerPanel.hidden=true;
    notificationsPanel.hidden=false;
    workspace.hidden=false;
    workspace.setAttribute('aria-label','Notifications');
    root.setAttribute('data-tailnet-view','external');
    markSelected(NOTIFICATIONS_ID);
    closeSessionsOverlay();
    document.dispatchEvent(new CustomEvent('hermesui:tailnet-app-selected',{detail:{id:NOTIFICATIONS_ID,label:'Notifications'}}));
    setNotificationFilter('unread');
    void loadCronNotifications();
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
    cancelBrowserFallback();
    hideTooltip();
    closeBookmarkMenu();
    activeId='';
    activeBookmarkNavigation=null;
    const showWizardHome=isWizardHomeDesktop();
    root.setAttribute('data-tailnet-view',showWizardHome?'wizard-home':'hermes');
    if(frame)frame.hidden=true;
    if(managerPanel)managerPanel.hidden=true;
    if(notificationsPanel)notificationsPanel.hidden=true;
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
    cancelBrowserFallback();
    const token=bookmarkToken(app);
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
    if(notificationsPanel)notificationsPanel.hidden=true;
    if(frame)frame.hidden=false;
    workspace.hidden=false;
    root.setAttribute('data-tailnet-view','external');
    markSelected(app.id);
    closeSessionsOverlay();
    try{sessionStorage.setItem(STORAGE_KEY,app.id);}catch(_){}
    document.dispatchEvent(new CustomEvent('hermesui:tailnet-app-selected',{detail:{id:app.id,label:app.label}}));
  }

  function cancelBrowserFallback(){
    browserFallbackSequence+=1;
    if(browserFallbackTimer!==null){
      clearTimeout(browserFallbackTimer);
      browserFallbackTimer=null;
    }
  }

  function openBrowserWindow(href){
    try{
      const availableWidth=Math.max(720,Number(screen.availWidth)||window.innerWidth||1180);
      const availableHeight=Math.max(640,Number(screen.availHeight)||window.innerHeight||820);
      const width=Math.min(1180,Math.max(720,availableWidth-96));
      const height=Math.min(820,Math.max(640,availableHeight-96));
      const left=Math.max(0,Math.round((availableWidth-width)/2));
      const top=Math.max(0,Math.round((availableHeight-height)/2));
      const features=`popup=yes,width=${width},height=${height},left=${left},top=${top},resizable=yes,scrollbars=yes`;
      const opened=window.open(href,'_blank',features);
      if(opened){
        try{opened.opener=null;}catch(_){}
        try{opened.focus();}catch(_){}
      }
      return opened;
    }catch(_){return null;}
  }

  function notifyBrowserFallbackResult(opened){
    try{
      frame.contentWindow.postMessage({
        type:'hermesui:bookmark-browser-result',
        opened:Boolean(opened)
      },location.origin);
    }catch(_){}
  }

  function scheduleBrowserFallback(app){
    cancelBrowserFallback();
    const sequence=browserFallbackSequence;
    browserFallbackTimer=window.setTimeout(()=>{
      browserFallbackTimer=null;
      if(
        sequence!==browserFallbackSequence||
        activeId!==app.id||
        frame.dataset.tailnetAppId!==app.id||
        frame.dataset.browserFallback!=='true'
      )return;
      notifyBrowserFallbackResult(openBrowserWindow(app.href));
    },BROWSER_FALLBACK_DELAY_MS);
  }

  function activateBrowserFallback(app,{open=true,reopen=false}={}){
    if(!workspace||!frame||!app.browserHref)return;
    hideTooltip();
    closeBookmarkMenu();
    activeId=app.id;
    activeBookmarkNavigation=null;
    const alreadyShowing=frame.dataset.tailnetAppId===app.id&&frame.dataset.browserFallback==='true';
    const shouldOpen=open&&(!alreadyShowing||reopen);
    cancelBrowserFallback();
    frame.dataset.tailnetAppId=app.id;
    frame.dataset.tailnetFrameKey=`browser:${bookmarkToken(app)}`;
    frame.dataset.browserFallback='true';
    frame.title=`${app.label} — browser fallback`;
    if(!alreadyShowing||reopen)frame.src=app.browserHref;
    workspace.setAttribute('aria-label',`${app.label} will open in browser`);
    if(wizardHome)wizardHome.hidden=true;
    if(notificationsPanel)notificationsPanel.hidden=true;
    if(frame)frame.hidden=false;
    workspace.hidden=false;
    root.setAttribute('data-tailnet-view','external');
    markSelected(app.id);
    closeSessionsOverlay();
    if(shouldOpen)scheduleBrowserFallback(app);
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
      activateBrowserFallback(app,{reopen:true});
      return;
    }
    if(activeId===app.id&&frame.dataset.browserFallback!=='true'){
      activateApp(app);
      return;
    }
    // Never pre-open a browser target: inline-capable links must remain in this shell.
    const generation=nextBookmarkGeneration();
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
    if(!await ensureBookmarkSync())return;
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
    const previous=cloneSavedGroups();
    savedGroups[current.group][index]=replacement;
    if(!await commitSavedGroups(previous))return;
    if(activeId===replacement.id){
      frame.title=replacement.label;
      workspace.setAttribute('aria-label',replacement.label);
    }
    notify(`${replacement.label} renamed.`);
    document.dispatchEvent(new CustomEvent('hermesui:app-bookmarks-changed',{detail:{group:current.group,count:savedGroups[current.group].length}}));
  }

  async function deleteBookmark(){
    const current=menuBookmark;
    closeBookmarkMenu();
    if(!current)return;
    if(!await ensureBookmarkSync())return;
    const app=bookmarkFor(current.group,current.id);
    if(!app)return;
    const previous=cloneSavedGroups();
    savedGroups[current.group]=savedGroups[current.group].filter(item=>item.id!==current.id);
    if(!await commitSavedGroups(previous))return;
    if(activeId===current.id)activateHermes();
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
    remove.addEventListener('click',()=>void deleteBookmark());
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
      if(data.mode==='inline'||data.mode==='browser'){
        frameDecisions[app.href]={
          mode:data.mode,
          reason:typeof data.reason==='string'?data.reason:'',
          checkedAt:Date.now()
        };
        writeFrameDecisions();
      }
      if(activeId!==app.id)return;
      if(data.mode==='browser')activateBrowserFallback(app);
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
      if(!await ensureBookmarkSync())return;
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
      const previous=cloneSavedGroups();
      savedGroups[group].push(app);
      if(!await commitSavedGroups(previous))return;
      notify(`${app.label} added to ${definition.plural}.`);
      void refreshFrameDecision(app,{force:true});
      document.dispatchEvent(new CustomEvent('hermesui:app-bookmarks-changed',{detail:{group,count:savedGroups[group].length}}));
    }finally{
      button.disabled=false;
    }
  }

  async function loadApps(){
    if(!links||!home||!workspace||!frame||!companyLinks||!publicLinks||!privateAdd||!companyAdd||!publicAdd||!notificationsButton||!notificationsPanel)return;
    root.setAttribute('data-tailnet-view','hermes');
    bindOverlayInteractions();
    home.addEventListener('click',event=>{
      event.preventDefault();
      activateHermes({openMobileMenu:true});
    });
    notificationsButton.addEventListener('click',activateNotifications);
    if(notificationsReadAll)notificationsReadAll.addEventListener('click',markAllNotificationsRead);
    notificationFilterButtons.forEach(button=>button.addEventListener('click',()=>setNotificationFilter(button.dataset.notificationFilter)));
    appsById.set(privateMarketplace.id,privateMarketplace);
    privateAdd.addEventListener('click',()=>activateApp(privateMarketplace));
    companyAdd.addEventListener('click',()=>void addSavedApp('company'));
    publicAdd.addEventListener('click',()=>void addSavedApp('public'));
    document.addEventListener('hermesui:tailnet-app-selected',event=>{
      const id=event&&event.detail&&event.detail.id;
      if(!id||id==='hermes-ui')return;
      activeId=id;
      if(wizardHome)wizardHome.hidden=true;
      if(notificationsPanel&&id!==NOTIFICATIONS_ID)notificationsPanel.hidden=true;
    });
    document.addEventListener('hermesui:cron-completions',event=>{
      const completions=event&&event.detail&&Array.isArray(event.detail.completions)?event.detail.completions:[];
      const jobIds=Array.from(new Set(completions.map(item=>String(item&&item.job_id||'')).filter(Boolean)));
      void refreshCronNotificationBadge();
      if(activeId===NOTIFICATIONS_ID&&jobIds.length)void loadCronNotifications({jobIds});
    });
    savedGroups=readSavedGroups();
    renderSavedGroup('company');
    renderSavedGroup('public');
    bookmarkSyncPromise=hydrateSavedGroups();
    void bookmarkSyncPromise.then(()=>refreshSavedFrameDecisions());
    let remembered='';
    try{remembered=sessionStorage.getItem(STORAGE_KEY)||'';}catch(_){}
    if(remembered&&appsById.has(remembered))activateApp(appsById.get(remembered));
    else activateHermes({remember:false});
    void refreshCronNotificationBadge();
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
