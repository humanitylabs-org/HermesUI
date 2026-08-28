(function(){
  'use strict';

  const MAX_BOOKMARKS_PER_GROUP=20;
  const STORAGE_KEY='hermesui.tailnet-app';
  const MOBILE_LAST_APP_STORAGE_KEY='hermesui.tailnet.last-app.v1';
  const BOOKMARK_STORAGE_KEY='hermesui.app-selector.bookmarks.v1';
  const BOOKMARK_API_PATH='/apps/api/bookmarks';
  const FRAME_DECISION_STORAGE_KEY='hermesui.app-selector.frame-decisions.v1';
  const FRAME_CHECK_PATH='/frame-check/';
  const FRAME_INLINE_DECISION_TTL_MS=6*60*60*1000;
  const FRAME_BROWSER_DECISION_TTL_MS=5*60*1000;
  const BROWSER_FALLBACK_DELAY_MS=3000;
  const NOTIFICATIONS_ID='cron-notifications';
  const NOTIFICATION_STATE_KEY='hermesui.cron-notifications.v1';
  const NOTIFICATION_ITEMS_CACHE_KEY='hermesui.cron-notification-items.v1';
  const THEME_STORAGE_KEY='hermes-theme';
  const MOBILE_RAIL_STORAGE_KEY='hermesui.mobile-rail.v1';
  const NOTIFICATION_OUTPUT_LIMIT=4;
  const NOTIFICATION_LIST_LIMIT=40;
  const SCHEDULED_JOB_LONG_PRESS_MS=450;
  const SCHEDULED_JOB_GROUPS=[
    {key:'running',label:'Running'},
    {key:'failed',label:'Failed'},
    {key:'active',label:'Active'},
    {key:'paused',label:'Paused'},
    {key:'disabled',label:'Disabled'},
    {key:'readonly',label:'Read-only'}
  ];
  const ACTIVE_FREQUENCY_GROUPS=[
    {key:'hourly',label:'Hourly & more often'},
    {key:'daily',label:'Daily'},
    {key:'weekly',label:'Weekly'},
    {key:'monthly',label:'Monthly'},
    {key:'yearly',label:'Yearly'},
    {key:'once',label:'One-time'},
    {key:'other',label:'Other schedules'}
  ];
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
  const wizardCanvasFrame=document.getElementById('wizardCanvasFrame');
  const managerPanel=document.getElementById('tailnetAppManager');
  const notificationsPanel=document.getElementById('tailnetNotifications');
  const notificationsButton=document.getElementById('tailnetNotificationsButton');
  const notificationsBadge=document.getElementById('tailnetNotificationsBadge');
  const notificationsStatus=document.getElementById('tailnetNotificationsStatus');
  const notificationsList=document.getElementById('tailnetNotificationsList');
  const scheduledList=document.getElementById('tailnetScheduledList');
  const notificationsReadAll=document.getElementById('tailnetNotificationsReadAll');
  const notificationActions=document.getElementById('tailnetNotificationActions');
  const scheduledActions=document.getElementById('tailnetScheduledActions');
  const scheduledNew=document.getElementById('tailnetScheduledNew');
  const scheduledRefresh=document.getElementById('tailnetScheduledRefresh');
  const cronEditDialog=document.getElementById('tailnetCronEditDialog');
  const cronEditMount=document.getElementById('tailnetCronEditMount');
  const cronEditTitle=document.getElementById('tailnetCronEditTitle');
  const cronEditClose=document.getElementById('tailnetCronEditClose');
  const cronEditCancel=document.getElementById('tailnetCronEditCancel');
  const cronEditSave=document.getElementById('tailnetCronEditSave');
  const notificationsModeButtons=Array.from(document.querySelectorAll('[data-notifications-mode]'));
  const notificationFilterButtons=Array.from(document.querySelectorAll('[data-notification-filter]'));
  const notificationThread=document.getElementById('tailnetNotificationThread');
  const notificationThreadBack=document.getElementById('tailnetNotificationThreadBack');
  const notificationThreadTitle=document.getElementById('tailnetNotificationThreadTitle');
  const notificationThreadContext=document.getElementById('tailnetNotificationThreadContext');
  const notificationThreadPinned=document.getElementById('tailnetNotificationThreadPinned');
  const notificationThreadMessages=document.getElementById('tailnetNotificationThreadMessages');
  const notificationThreadComposer=document.getElementById('tailnetNotificationThreadComposer');
  const notificationThreadInput=document.getElementById('tailnetNotificationThreadInput');
  const notificationThreadSend=document.getElementById('tailnetNotificationThreadSend');
  const notificationThreadStop=document.getElementById('tailnetNotificationThreadStop');
  const notificationThreadAttach=document.getElementById('tailnetNotificationThreadAttach');
  const notificationThreadFileInput=document.getElementById('tailnetNotificationThreadFileInput');
  const notificationThreadAttachTray=document.getElementById('tailnetNotificationThreadAttachTray');
  const notificationThreadPrompts=document.getElementById('tailnetNotificationThreadPrompts');
  const notificationThreadPromptsPopup=document.getElementById('tailnetNotificationThreadPromptsPopup');
  const notificationThreadModelChip=document.getElementById('tailnetNotificationThreadModelChip');
  const notificationThreadModelLabel=document.getElementById('tailnetNotificationThreadModelLabel');
  const notificationThreadModelSelect=document.getElementById('tailnetNotificationThreadModelSelect');
  const notificationThreadModelDropdown=document.getElementById('tailnetNotificationThreadModelDropdown');
  const notificationThreadStatus=document.getElementById('tailnetNotificationThreadStatus');
  const home=document.getElementById('tailnetAppHome');
  const appRail=document.getElementById('tailnetAppRail');
  const mobileRailHandle=document.getElementById('mobileRailHandle');
  const themeToggle=document.getElementById('tailnetThemeToggle');
  const mobileSessionsButton=document.getElementById('mobileSessionsButton');
  const mobileNotificationsButton=document.getElementById('mobileNotificationsButton');
  const mobileNotificationsBadge=document.getElementById('mobileNotificationsBadge');
  const mobileUtilitiesToggle=document.getElementById('mobileSessionUtilitiesToggle');
  const mobileUtilitiesMenu=document.getElementById('mobileSessionUtilitiesMenu');
  const mobileSessionViewUtility=document.getElementById('mobileSessionViewUtility');
  const mobileThemeUtility=document.getElementById('mobileThemeUtility');
  const mobileSettingsUtility=document.getElementById('mobileSettingsUtility');
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
  let lastMobileAppSnapshot={id:'',token:'',generation:'',browserFallback:false};
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
  let cachedNotifications=readNotificationItems();
  let notificationItems=cachedNotifications.items;
  let notificationWatermarks=cachedNotifications.watermarks;
  let notificationsLoading=false;
  let notificationFilter='unread';
  let notificationsMode='notifications';
  let scheduledJobs=[];
  let scheduledRunning={};
  let scheduledLoading=false;
  let scheduledEditorState=null;
  let scheduledJobLongPress=null;
  let notificationThreadItem=null;
  let notificationThreadSession=null;
  let notificationThreadBaseMessages=[];
  let notificationThreadSource=null;
  let notificationThreadStream=null;
  let notificationThreadStreamId='';
  let notificationThreadDraft='';
  let notificationThreadLiveMessages=[];
  let notificationThreadClarify=null;
  let notificationThreadFiles=[];
  let notificationThreadModel={model:'',model_provider:null};
  let notificationThreadModelExplicit=false;
  const notificationReplySessions=new Map();
  const CRON_REPLY_TITLE_PREFIX='[cron-reply:';

  function resolvedTheme(){
    return root.classList.contains('dark')?'dark':'light';
  }

  function sendThemeToWizardCanvas(){
    if(!wizardCanvasFrame||!wizardCanvasFrame.contentWindow)return;
    try{
      wizardCanvasFrame.contentWindow.postMessage(
        {type:'hermesui:theme',theme:resolvedTheme()},
        location.origin
      );
    }catch(_){}
  }

  function syncThemeToggle(){
    if(themeToggle){
      const dark=resolvedTheme()==='dark';
      const label=dark?'Switch to light mode':'Switch to dark mode';
      const tooltip=dark?'Light mode':'Dark mode';
      themeToggle.setAttribute('aria-label',label);
      themeToggle.dataset.tooltip=tooltip;
      themeToggle.setAttribute('aria-pressed',String(dark));
    }
    sendThemeToWizardCanvas();
  }

  function toggleShellTheme(){
    const next=resolvedTheme()==='dark'?'light':'dark';
    try{
      if(typeof window._pickTheme==='function')window._pickTheme(next);
      else{
        localStorage.setItem(THEME_STORAGE_KEY,next);
        root.classList.toggle('dark',next==='dark');
      }
    }catch(_){root.classList.toggle('dark',next==='dark');}
    syncThemeToggle();
  }

  function mobileUtilityIsOpen(){
    return !!(mobileUtilitiesMenu&&!mobileUtilitiesMenu.hidden);
  }

  function syncMobileUtilities(){
    if(mobileSessionViewUtility){
      const enabled=root.dataset.sessionView==='dashboard';
      mobileSessionViewUtility.setAttribute('aria-checked',String(enabled));
      const note=mobileSessionViewUtility.querySelector('.mobile-session-utility-note');
      if(note)note.textContent=enabled?'Experimental · On':'Experimental';
      mobileSessionViewUtility.setAttribute('aria-label',enabled?'High Signal mode, experimental, on':'High Signal mode, experimental, off');
    }
    if(mobileThemeUtility){
      const enabled=resolvedTheme()==='dark';
      mobileThemeUtility.setAttribute('aria-checked',String(enabled));
      const note=mobileThemeUtility.querySelector('.mobile-session-utility-note');
      if(note)note.textContent=enabled?'Dark':'Light';
      mobileThemeUtility.setAttribute('aria-label',enabled?'Appearance: dark. Switch to light mode.':'Appearance: light. Switch to dark mode.');
    }
  }

  function syncMobilePrimaryMenu(){
    if(mobileSessionsButton){
      const selected=isPhoneWidth()&&root.dataset.mobileSessionView==='sessions';
      if(selected)mobileSessionsButton.setAttribute('aria-current','page');
      else mobileSessionsButton.removeAttribute('aria-current');
    }
    if(mobileNotificationsButton){
      const selected=isPhoneWidth()&&activeId===NOTIFICATIONS_ID;
      if(selected)mobileNotificationsButton.setAttribute('aria-current','page');
      else mobileNotificationsButton.removeAttribute('aria-current');
    }
  }

  function setMobileUtilitiesOpen(open,{restoreFocus=false}={}){
    if(!mobileUtilitiesToggle||!mobileUtilitiesMenu)return;
    const next=!!open&&window.matchMedia('(max-width:640px)').matches;
    mobileUtilitiesMenu.hidden=!next;
    mobileUtilitiesToggle.setAttribute('aria-expanded',String(next));
    if(next){
      syncMobileUtilities();
      requestAnimationFrame(()=>{
        const first=mobileUtilitiesMenu.querySelector('[role^="menuitem"]');
        if(first&&mobileUtilityIsOpen())first.focus({preventScroll:true});
      });
    }else if(restoreFocus&&mobileUtilitiesToggle.isConnected){
      mobileUtilitiesToggle.focus({preventScroll:true});
    }
  }

  function activateMobileUtility(source){
    if(source&&typeof source.click==='function')source.click();
    requestAnimationFrame(syncMobileUtilities);
  }

  function bindMobileUtilities(){
    if(!mobileUtilitiesToggle||!mobileUtilitiesMenu)return;
    mobileUtilitiesToggle.addEventListener('click',()=>setMobileUtilitiesOpen(!mobileUtilityIsOpen()));
    if(mobileSessionViewUtility)mobileSessionViewUtility.addEventListener('click',()=>activateMobileUtility(document.getElementById('sessionViewToggle')));
    if(mobileThemeUtility)mobileThemeUtility.addEventListener('click',()=>activateMobileUtility(themeToggle));
    if(mobileSettingsUtility)mobileSettingsUtility.addEventListener('click',()=>{
      setMobileUtilitiesOpen(false);
      activateMobileUtility(document.getElementById('chatSettingsToggle'));
    });
    mobileUtilitiesMenu.addEventListener('keydown',event=>{
      const items=Array.from(mobileUtilitiesMenu.querySelectorAll('[role^="menuitem"]'));
      const index=items.indexOf(document.activeElement);
      let next=-1;
      if(event.key==='ArrowDown')next=index<items.length-1?index+1:0;
      else if(event.key==='ArrowUp')next=index>0?index-1:items.length-1;
      else if(event.key==='Home')next=0;
      else if(event.key==='End')next=items.length-1;
      if(next>=0){event.preventDefault();items[next].focus();}
    });
    document.addEventListener('pointerdown',event=>{
      if(!mobileUtilityIsOpen())return;
      if(event.target instanceof Node&&(mobileUtilitiesMenu.contains(event.target)||mobileUtilitiesToggle.contains(event.target)))return;
      setMobileUtilitiesOpen(false);
    });
    document.addEventListener('focusin',event=>{
      if(!mobileUtilityIsOpen())return;
      if(event.target instanceof Node&&(mobileUtilitiesMenu.contains(event.target)||mobileUtilitiesToggle.contains(event.target)))return;
      setMobileUtilitiesOpen(false);
    });
    document.addEventListener('keydown',event=>{
      if(event.key!=='Escape'||!mobileUtilityIsOpen())return;
      event.preventDefault();
      setMobileUtilitiesOpen(false,{restoreFocus:true});
    });
    window.addEventListener('resize',()=>{
      if(window.innerWidth>640)setMobileUtilitiesOpen(false);
    },{passive:true});
    syncMobileUtilities();
  }

  function bindMobilePrimaryMenu(){
    if(mobileSessionsButton)mobileSessionsButton.addEventListener('click',()=>{
      setMobileUtilitiesOpen(false);
      activateHermes();
      if(typeof window.openMobileSessionPage==='function')window.openMobileSessionPage();
      syncMobilePrimaryMenu();
    });
    if(mobileNotificationsButton)mobileNotificationsButton.addEventListener('click',()=>{
      setMobileUtilitiesOpen(false);
      activateNotifications();
    });
    syncMobilePrimaryMenu();
  }

  function mobileRailIsCollapsed(){
    return root.dataset.mobileRail==='collapsed';
  }

  function syncMobileRail(){
    if(!appRail||!mobileRailHandle)return;
    const collapsed=isPhoneWidth()&&mobileRailIsCollapsed();
    appRail.inert=collapsed;
    if(collapsed)appRail.setAttribute('aria-hidden','true');
    else appRail.removeAttribute('aria-hidden');
    mobileRailHandle.setAttribute('aria-expanded',String(!collapsed));
    mobileRailHandle.setAttribute('aria-label',collapsed?'Show apps':'Hide apps');
    mobileRailHandle.title=collapsed?'Show apps':'Hide apps';
  }

  function setMobileRailCollapsed(collapsed,{persist=true,focusApps=false}={}){
    if(!isPhoneWidth())return;
    const next=!!collapsed;
    root.dataset.mobileRail=next?'collapsed':'expanded';
    if(persist){
      try{localStorage.setItem(MOBILE_RAIL_STORAGE_KEY,next?'collapsed':'expanded');}catch(_){}
    }
    if(next&&appRail&&appRail.contains(document.activeElement)&&mobileRailHandle){
      mobileRailHandle.focus({preventScroll:true});
    }
    syncMobileRail();
    if(!next&&focusApps){
      requestAnimationFrame(()=>{
        const first=appRail&&appRail.querySelector('#tailnetAppLinks .rail-btn:not([hidden]),#tailnetPrivateManager:not([hidden]),#tailnetPrivateAdd:not([hidden])');
        if(first&&isPhoneWidth()&&!mobileRailIsCollapsed())first.focus({preventScroll:true});
      });
    }
    document.dispatchEvent(new CustomEvent('hermesui:mobile-rail-changed',{detail:{collapsed:next}}));
  }

  function bindMobileRail(){
    if(!appRail||!mobileRailHandle)return;
    mobileRailHandle.addEventListener('click',()=>setMobileRailCollapsed(!mobileRailIsCollapsed(),{focusApps:mobileRailIsCollapsed()}));
    window.addEventListener('resize',syncMobileRail,{passive:true});
    syncMobileRail();
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
      if(raw&&(raw.version===1||raw.version===2)&&Number.isFinite(Number(raw.readThrough))&&raw.readJobs&&typeof raw.readJobs==='object'){
        const readJobs={};
        Object.entries(raw.readJobs).slice(-80).forEach(([id,value])=>{
          const timestamp=Number(value);
          if(id&&Number.isFinite(timestamp)&&timestamp>0)readJobs[id]=timestamp;
        });
        const readItems={};
        if(raw.readItems&&typeof raw.readItems==='object'){
          Object.entries(raw.readItems).slice(-200).forEach(([key,value])=>{
            const timestamp=Number(value);
            if(key&&Number.isFinite(timestamp)&&timestamp>0)readItems[key]=timestamp;
          });
        }
        return {version:2,readThrough:Number(raw.readThrough),readJobs,readItems};
      }
    }catch(_){}
    const initial={version:2,readThrough:Date.now()/1000,readJobs:{},readItems:{}};
    try{localStorage.setItem(NOTIFICATION_STATE_KEY,JSON.stringify(initial));}catch(_){}
    return initial;
  }

  function writeNotificationState(){
    try{
      const jobEntries=Object.entries(notificationState.readJobs)
        .sort(([,left],[,right])=>Number(right)-Number(left))
        .slice(0,80);
      const itemEntries=Object.entries(notificationState.readItems)
        .sort(([,left],[,right])=>Number(right)-Number(left))
        .slice(0,200);
      notificationState.version=2;
      notificationState.readJobs=Object.fromEntries(jobEntries);
      notificationState.readItems=Object.fromEntries(itemEntries);
      localStorage.setItem(NOTIFICATION_STATE_KEY,JSON.stringify(notificationState));
    }catch(_){}
  }

  function readNotificationItems(){
    const items=new Map();
    const watermarks={};
    try{
      const raw=JSON.parse(sessionStorage.getItem(NOTIFICATION_ITEMS_CACHE_KEY)||'null');
      const rows=raw&&raw.version===1&&Array.isArray(raw.items)?raw.items:[];
      rows.slice(0,NOTIFICATION_LIST_LIMIT).forEach(item=>{
        const key=String(item&&item.key||'');
        const jobId=String(item&&item.jobId||'');
        const modified=Number(item&&item.modified);
        const response=String(item&&item.response||'').slice(0,8000);
        if(!key||!jobId||!Number.isFinite(modified)||!response)return;
        items.set(key,{
          key,jobId,
          name:String(item.name||jobId).slice(0,120),
          filename:String(item.filename||'').slice(0,240),
          modified,
          status:item.status==='error'?'error':'ok',
          response,
          sourceSessionId:String(item.sourceSessionId||''),
          contextMode:item.contextMode==='full'?'full':'output'
        });
      });
      if(raw&&raw.watermarks&&typeof raw.watermarks==='object'){
        Object.entries(raw.watermarks).slice(-100).forEach(([jobId,value])=>{
          const stamp=Number(value);
          if(jobId&&Number.isFinite(stamp)&&stamp>0)watermarks[jobId]=stamp;
        });
      }
    }catch(_){}
    return {items,watermarks};
  }

  function writeNotificationItems(){
    try{
      const items=Array.from(notificationItems.values())
        .sort((left,right)=>right.modified-left.modified)
        .slice(0,NOTIFICATION_LIST_LIMIT);
      const watermarks={};
      Object.entries(notificationWatermarks)
        .sort(([,left],[,right])=>Number(right)-Number(left))
        .slice(0,100)
        .forEach(([jobId,value])=>{
          if(Number.isFinite(Number(value)))watermarks[jobId]=Number(value);
        });
      sessionStorage.setItem(NOTIFICATION_ITEMS_CACHE_KEY,JSON.stringify({version:1,items,watermarks}));
    }catch(_){}
  }

  function notificationReadCutoff(jobId){
    return Math.max(Number(notificationState.readThrough)||0,Number(notificationState.readJobs[jobId])||0);
  }

  function notificationIsUnread(item){
    if(item.modified<=notificationReadCutoff(item.jobId))return false;
    return (Number(notificationState.readItems[item.key])||0)<item.modified;
  }

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
    const unread=Math.max(0,Number(count)||0);
    const label=unread>0?`Notifications, ${unread} unread`:'Notifications';
    [[notificationsButton,notificationsBadge],[mobileNotificationsButton,mobileNotificationsBadge]].forEach(([button,badge])=>{
      if(!button||!badge)return;
      badge.textContent=unread>9?'9+':String(unread);
      badge.hidden=unread===0;
      button.classList.toggle('has-unread',unread>0);
      button.setAttribute('aria-label',label);
    });
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
    const silentSentinel=body
      .replace(/^[-*_`#>\[\]()\s]+|[-*_`#>\[\]()\s]+$/g,'')
      .replace(/\s+/g,' ')
      .toLowerCase();
    if(silentSentinel==='silent'||silentSentinel==='no reply'||silentSentinel==='no_reply')return '';
    return body.slice(0,8000);
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
    notificationState.readItems[item.key]=Math.max(Number(notificationState.readItems[item.key])||0,item.modified);
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
    notificationState.readItems={};
    writeNotificationState();
    renderCronNotifications();
  }

  function stableNotificationToken(value){
    const source=String(value||'');
    let left=0x811c9dc5;
    let right=0x9e3779b9;
    for(let index=0;index<source.length;index+=1){
      const code=source.charCodeAt(index);
      left=Math.imul(left^code,0x01000193)>>>0;
      right=Math.imul(right^(code+index),0x85ebca6b)>>>0;
    }
    return left.toString(16).padStart(8,'0')+right.toString(16).padStart(8,'0');
  }

  function notificationReplyMarker(item){
    return `${CRON_REPLY_TITLE_PREFIX}${stableNotificationToken(item&&item.key)}]`;
  }

  function notificationReplyTitle(item){
    const marker=notificationReplyMarker(item);
    return `${marker} ${String(item&&item.name||'Scheduled job')}`.slice(0,80);
  }

  function notificationPreview(value){
    return String(value||'')
      .replace(/[`*_>#\[\]]/g,' ')
      .replace(/\s+/g,' ')
      .trim()
      .slice(0,180);
  }

  function syncNotificationsModeControls(){
    const inThread=!!notificationThreadItem;
    if(notificationsPanel)notificationsPanel.dataset.notificationsMode=inThread?'thread':notificationsMode;
    notificationsModeButtons.forEach(button=>{
      const active=button.dataset.notificationsMode===notificationsMode&&!inThread;
      button.classList.toggle('is-active',active);
      button.setAttribute('aria-selected',String(active));
      button.tabIndex=active?0:-1;
    });
    if(notificationActions)notificationActions.hidden=inThread||notificationsMode!=='notifications';
    if(scheduledActions)scheduledActions.hidden=inThread||notificationsMode!=='scheduled';
    if(notificationsList)notificationsList.hidden=inThread||notificationsMode!=='notifications';
    if(scheduledList)scheduledList.hidden=inThread||notificationsMode!=='scheduled';
    if(notificationThread)notificationThread.hidden=!inThread;
  }

  function closeNotificationThread(){
    if(notificationThreadStream){
      notificationThreadStream.close();
      notificationThreadStream=null;
    }
    notificationThreadStreamId='';
    notificationThreadDraft='';
    notificationThreadLiveMessages=[];
    notificationThreadClarify=null;
    notificationThreadItem=null;
    notificationThreadSession=null;
    notificationThreadBaseMessages=[];
    notificationThreadSource=null;
    notificationThreadFiles=[];
    notificationThreadModel={model:'',model_provider:null};
    notificationThreadModelExplicit=false;
    if(notificationThreadInput){notificationThreadInput.value='';notificationThreadInput.style.height='';}
    if(notificationThreadFileInput)notificationThreadFileInput.value='';
    renderNotificationThreadFiles();
    closeNotificationThreadPrompts();
    closeNotificationThreadModelDropdown();
    if(notificationThreadStatus){notificationThreadStatus.textContent='';notificationThreadStatus.style.display='none';}
    syncNotificationsModeControls();
    if(notificationsStatus){
      const items=Array.from(notificationItems.values()).slice(0,NOTIFICATION_LIST_LIMIT);
      notificationsStatus.hidden=false;
      notificationsStatus.textContent=notificationStatusText(items.filter(notificationIsUnread).length,items.length);
    }
  }

  function setNotificationsMode(value){
    if(notificationThreadItem)closeNotificationThread();
    notificationsMode=value==='scheduled'?'scheduled':'notifications';
    syncNotificationsModeControls();
    if(notificationsMode==='scheduled')void loadScheduledJobs();
    else renderCronNotifications();
  }

  function cronJobsFromPayload(payload,{includeReadOnly=false}={}){
    return Array.isArray(payload&&payload.jobs)
      ?payload.jobs.filter(job=>job&&job.id&&(includeReadOnly||!job.read_only))
      :[];
  }

  async function fetchCronNotificationJobs(){
    const payload=await api('/api/crons');
    return cronJobsFromPayload(payload).filter(job=>job.toast_notifications!==false);
  }

  async function fetchLatestCronSessions(){
    try{
      const payload=await api('/api/crons/recent?since=0');
      const entries=Array.isArray(payload&&payload.completions)?payload.completions:[];
      return new Map(entries.map(entry=>[String(entry.job_id||''),entry]));
    }catch(_){return new Map();}
  }

  function cronNotificationWatermark(job,latestSessions){
    const lastRun=Date.parse(job&&job.last_run_at||'')/1000;
    const recent=latestSessions.get(String(job&&job.id||''));
    const completed=Number(recent&&recent.completed_at)||0;
    return Math.max(Number.isFinite(lastRun)?lastRun:0,completed);
  }

  async function fetchCronNotificationOutputs(job,latestSessions=new Map()){
    const payload=await api(`/api/crons/output?job_id=${encodeURIComponent(job.id)}&limit=${NOTIFICATION_OUTPUT_LIMIT}`);
    const outputs=Array.isArray(payload&&payload.outputs)?payload.outputs:[];
    const fallback=Date.parse(job.last_run_at||'')/1000;
    const latest=latestSessions.get(String(job.id))||null;
    const items=outputs.map((output,index)=>{
      const filename=String(output.filename||'');
      const modified=parseCronFilenameTimestamp(filename,fallback,index);
      const completedAt=Number(latest&&latest.completed_at)||0;
      const exactLatest=index===0&&latest&&latest.session_id&&!job.no_agent
        &&Number(latest.message_count)>0&&Number(latest.message_count)<=12&&(
        !completedAt||!modified||Math.abs(modified-completedAt)<300
      );
      return {
        key:`${job.id}:${filename||modified}`,
        jobId:String(job.id),
        name:String(job.name||job.id),
        filename,
        modified,
        status:index===0?String(job.last_status||'ok'):'ok',
        response:cronResponseText(output.content),
        sourceSessionId:exactLatest?String(latest.session_id):'',
        contextMode:exactLatest?'full':'output'
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
        response:`Run failed\n${String(job.last_error).slice(0,8000)}`,
        sourceSessionId:'',
        contextMode:'output'
      });
    }
    return items;
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
    syncNotificationsModeControls();
    if(notificationsReadAll)notificationsReadAll.disabled=unreadCount===0;
    if(notificationsMode!=='notifications')return;
    notificationsList.replaceChildren();
    notificationsStatus.hidden=false;
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
      const role=document.createElement('span');
      role.className='msg-role assistant tailnet-notification-role';
      const icon=document.createElement('span');
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
      response.textContent=notificationPreview(item.response)||(item.status==='error'?'Failed run':'Scheduled-job response');
      button.append(role,response);
      const rich=document.createElement('div');
      rich.id=richId;
      rich.className='tailnet-notification-rich';
      rich.hidden=true;
      const richBody=document.createElement('div');
      richBody.className='tailnet-notification-rich-body msg-body';
      const reply=document.createElement('button');
      reply.type='button';
      reply.className='tailnet-notification-reply';
      reply.textContent='Reply';
      reply.addEventListener('click',event=>{
        event.stopPropagation();
        void openNotificationThread(item);
      });
      rich.append(richBody,reply);
      button.addEventListener('click',()=>{
        const open=article.classList.toggle('is-open');
        button.setAttribute('aria-expanded',String(open));
        button.setAttribute('aria-label',`${open?'Close':'Open'} notification from ${item.name}`);
        rich.hidden=!open;
        if(open)hydrateNotificationRich(richBody,item);
        if(open&&notificationIsUnread(item)){
          markNotificationRead(item);
          article.classList.remove('is-unread');
        }
        if(!open&&notificationFilter==='unread'&&!notificationIsUnread(item))renderCronNotifications();
      });
      article.append(button,rich);
      notificationsList.appendChild(article);
    });
  }

  async function loadCronNotifications({jobIds=null,fullRefresh=false}={}){
    if(notificationsLoading)return;
    notificationsLoading=true;
    if(notificationsStatus&&!notificationItems.size)notificationsStatus.textContent='Loading…';
    try{
      const [jobs,latestSessions]=await Promise.all([fetchCronNotificationJobs(),fetchLatestCronSessions()]);
      const ids=jobIds?new Set(jobIds.map(String)):null;
      const liveIds=new Set(jobs.map(job=>String(job.id)));
      Array.from(notificationItems.entries()).forEach(([key,item])=>{
        if(!liveIds.has(item.jobId))notificationItems.delete(key);
      });
      Object.keys(notificationWatermarks).forEach(jobId=>{
        if(!liveIds.has(jobId))delete notificationWatermarks[jobId];
      });
      const selected=ids
        ?jobs.filter(job=>ids.has(String(job.id)))
        :fullRefresh
          ?jobs
          :jobs.filter(job=>cronNotificationWatermark(job,latestSessions)>Number(notificationWatermarks[String(job.id)]||0));
      const batches=await mapWithConcurrency(selected,4,job=>fetchCronNotificationOutputs(job,latestSessions));
      selected.forEach(job=>{
        const prefix=`${job.id}:`;
        Array.from(notificationItems.keys()).forEach(key=>{if(key.startsWith(prefix))notificationItems.delete(key);});
        notificationWatermarks[String(job.id)]=cronNotificationWatermark(job,latestSessions)||Date.now()/1000;
      });
      batches.flat().forEach(item=>notificationItems.set(item.key,item));
      writeNotificationItems();
    }catch(_){
      if(notificationsStatus)notificationsStatus.textContent='Notifications are unavailable right now.';
    }finally{
      notificationsLoading=false;
      renderCronNotifications();
    }
  }

  function scheduleNotificationRefresh(){
    if(!notificationItems.size)return;
    setTimeout(()=>{
      const refresh=()=>{if(!document.hidden)void loadCronNotifications();};
      if(typeof requestIdleCallback==='function')requestIdleCallback(refresh,{timeout:4000});
      else refresh();
    },1500);
  }

  function scheduledStatusMeta(job){
    if(scheduledRunning&&Object.prototype.hasOwnProperty.call(scheduledRunning,String(job.id))){
      return {key:'running',label:'Running',className:'is-running'};
    }
    if(job.paused||job.state==='paused')return {key:'paused',label:'Paused',className:'is-paused'};
    if(job.disabled||job.state==='disabled')return {key:'disabled',label:'Disabled',className:'is-disabled'};
    if(String(job.last_status||'').toLowerCase()==='error')return {key:'failed',label:'Failed',className:'is-error'};
    if(job.read_only)return {key:'readonly',label:'Read-only',className:'is-readonly'};
    return {key:'active',label:'Active',className:'is-active'};
  }

  function scheduledJobTime(job,fields,{fallback=Number.POSITIVE_INFINITY}={}){
    for(const field of fields){
      const value=job&&job[field];
      const stamp=typeof value==='number'?value*1000:Date.parse(value||'');
      if(Number.isFinite(stamp))return stamp;
    }
    return fallback;
  }

  function scheduledJobSort(job,groupKey){
    if(groupKey==='active'||groupKey==='paused'){
      return {stamp:scheduledJobTime(job,['next_run_at']),direction:1};
    }
    return {stamp:scheduledJobTime(job,['last_run_at','updated_at','created_at'],{fallback:Number.NEGATIVE_INFINITY}),direction:-1};
  }

  function scheduledJobsByGroup(){
    const grouped=new Map(SCHEDULED_JOB_GROUPS.map(group=>[group.key,[]]));
    scheduledJobs.forEach(job=>{
      const status=scheduledStatusMeta(job);
      if(!grouped.has(status.key))grouped.set(status.key,[]);
      grouped.get(status.key).push(job);
    });
    grouped.forEach((jobs,groupKey)=>jobs.sort((left,right)=>{
      const leftSort=scheduledJobSort(left,groupKey);
      const rightSort=scheduledJobSort(right,groupKey);
      const leftMissing=!Number.isFinite(leftSort.stamp);
      const rightMissing=!Number.isFinite(rightSort.stamp);
      if(leftMissing&&rightMissing)return String(left.name||left.id).localeCompare(String(right.name||right.id));
      if(leftMissing!==rightMissing)return leftMissing?1:-1;
      const byTime=(leftSort.stamp-rightSort.stamp)*leftSort.direction;
      return byTime!==0?byTime:String(left.name||left.id).localeCompare(String(right.name||right.id));
    }));
    return grouped;
  }

  function scheduledActiveFrequencyKey(job){
    const schedule=job&&job.schedule&&typeof job.schedule==='object'?job.schedule:{};
    const kind=String(schedule.kind||'').toLowerCase();
    const repeatTimes=Number(job&&job.repeat&&job.repeat.times);
    if(kind==='once'||kind==='timestamp'||repeatTimes===1)return 'once';
    if(kind==='interval'){
      const minutes=Number(schedule.minutes);
      if(!Number.isFinite(minutes)||minutes<=0)return 'other';
      if(minutes<1440)return 'hourly';
      if(minutes<10080)return 'daily';
      if(minutes<40320)return 'weekly';
      if(minutes<525600)return 'monthly';
      return 'yearly';
    }
    const raw=String(schedule.expr||schedule.expression||job.schedule_display||'').trim();
    const macroFrequency={
      '@hourly':'hourly',
      '@daily':'daily',
      '@midnight':'daily',
      '@weekly':'weekly',
      '@monthly':'monthly',
      '@yearly':'yearly',
      '@annually':'yearly'
    }[raw.toLowerCase()];
    if(macroFrequency)return macroFrequency;
    const fields=raw.split(/\s+/);
    if(kind!=='cron'&&fields.length!==5&&fields.length!==6)return 'other';
    const cron=fields.length===6?fields.slice(1):fields;
    if(cron.length!==5)return 'other';
    const [,hour,monthDay,month,weekday]=cron;
    const wildcard=value=>value==='*'||value==='?';
    if(!wildcard(month))return 'yearly';
    if(!wildcard(monthDay))return 'monthly';
    if(!wildcard(weekday)){
      const normalized=weekday.toUpperCase();
      return normalized==='1-5'||normalized==='MON-FRI'?'daily':'weekly';
    }
    if(!/^\d{1,2}$/.test(hour))return 'hourly';
    return 'daily';
  }

  function scheduledActiveJobsByFrequency(jobs){
    const grouped=new Map(ACTIVE_FREQUENCY_GROUPS.map(group=>[group.key,[]]));
    jobs.forEach(job=>grouped.get(scheduledActiveFrequencyKey(job)).push(job));
    return grouped;
  }

  function scheduledRelativeText(groupKey,relative,future){
    if(groupKey==='active')return relative.text;
    if(groupKey==='failed')return `failed ${relative.text}`;
    if(groupKey==='paused'&&relative.state==='late')return `was due ${relative.text.slice(5)} ago`;
    return `${future?'Next':'Last'} ${relative.text}`;
  }

  function scheduledRelativeMeta(job,groupKey){
    const future=groupKey==='active'||groupKey==='paused';
    const value=future?job.next_run_at:job.last_run_at;
    const relative=typeof cronRelativeTimeMeta==='function'
      ?cronRelativeTimeMeta(value,future?'next':'last')
      :{text:future?'Not scheduled':'Never run',absolute:'',stamp:null,state:'unknown'};
    const active=groupKey==='active';
    const text=relative.stamp==null
      ?(active?'next run pending':relative.text)
      :scheduledRelativeText(groupKey,relative,future);
    return {
      text,
      absolute:relative.absolute||'',
      value:value==null?'':String(value),
      kind:future?'next':'last',
      state:relative.state||'unknown'
    };
  }

  function refreshScheduledRelativeTimes(){
    if(!scheduledList)return;
    scheduledList.querySelectorAll('[data-scheduled-time-kind]').forEach(node=>{
      const kind=node.dataset.scheduledTimeKind;
      const value=node.dataset.scheduledTimeValue;
      const row=node.closest('.tailnet-scheduled-job');
      const groupKey=row&&row.dataset.jobStatusGroup||'';
      const relative=typeof cronRelativeTimeMeta==='function'
        ?cronRelativeTimeMeta(value,kind)
        :{text:kind==='next'?'Not scheduled':'Never run',absolute:'',stamp:null,state:'unknown'};
      node.textContent=relative.stamp==null
        ?(groupKey==='active'?'next run pending':relative.text)
        :scheduledRelativeText(groupKey,relative,kind==='next');
      node.title=relative.absolute||'';
      node.dataset.scheduledTimeState=relative.state||'unknown';
      if(row){
        row.classList.toggle('is-timing-late',relative.state==='late');
        row.classList.toggle('is-timing-due',relative.state==='due');
      }
      if(row&&row.hasAttribute('aria-label')){
        row.setAttribute('aria-label',`${row.dataset.jobName}. ${row.dataset.jobGroup}. ${node.textContent}. Press Enter, right-click, or hold for actions.`);
      }
    });
  }

  function scheduledJobButton(label,action,{danger=false}={}){
    const button=document.createElement('button');
    button.type='button';
    button.className=`tailnet-scheduled-action${danger?' is-danger':''}`;
    button.textContent=label;
    button.dataset.jobAction=action;
    button.setAttribute('role','menuitem');
    return button;
  }

  function closeScheduledJobMenus({except=null,restoreFocus=false}={}){
    if(!scheduledList)return;
    scheduledList.querySelectorAll('.tailnet-scheduled-job-menu:not([hidden])').forEach(menu=>{
      if(menu===except)return;
      menu.hidden=true;
      menu.style.left='';
      menu.style.top='';
      const row=menu.closest('.tailnet-scheduled-job');
      if(row){
        row.setAttribute('aria-expanded','false');
        row.classList.remove('is-menu-open');
        if(restoreFocus)row.focus({preventScroll:true});
      }
    });
  }

  function cancelScheduledJobLongPress(){
    if(!scheduledJobLongPress)return;
    clearTimeout(scheduledJobLongPress.timer);
    if(scheduledJobLongPress.row)scheduledJobLongPress.row.classList.remove('is-pressing');
    scheduledJobLongPress=null;
  }

  function openScheduledJobMenu(row,menu,{clientX,clientY,focusFirst=false}={}){
    if(!row||!menu)return;
    closeScheduledJobMenus({except:menu});
    menu.hidden=false;
    row.setAttribute('aria-expanded','true');
    row.classList.add('is-menu-open');
    const mobile=window.matchMedia&&window.matchMedia('(max-width:640px)').matches;
    if(!mobile){
      const rect=row.getBoundingClientRect();
      const width=menu.offsetWidth;
      const height=menu.offsetHeight;
      const anchorX=Number.isFinite(clientX)?clientX:rect.right;
      const anchorY=Number.isFinite(clientY)?clientY:rect.top+rect.height/2;
      menu.style.left=`${Math.max(8,Math.min(window.innerWidth-width-8,anchorX))}px`;
      menu.style.top=`${Math.max(8,Math.min(window.innerHeight-height-8,anchorY))}px`;
    }
    if(focusFirst){
      requestAnimationFrame(()=>menu.querySelector('[role="menuitem"]')?.focus({preventScroll:true}));
    }
  }

  function bindScheduledJobActions(row,menu,job){
    row.addEventListener('contextmenu',event=>{
      event.preventDefault();
      cancelScheduledJobLongPress();
      openScheduledJobMenu(row,menu,{clientX:event.clientX,clientY:event.clientY,focusFirst:true});
    });
    row.addEventListener('pointerdown',event=>{
      if(event.pointerType==='mouse'||event.button!==0)return;
      cancelScheduledJobLongPress();
      const startX=event.clientX;
      const startY=event.clientY;
      row.classList.add('is-pressing');
      scheduledJobLongPress={
        row,
        pointerId:event.pointerId,
        startX,
        startY,
        timer:setTimeout(()=>{
          row.classList.remove('is-pressing');
          scheduledJobLongPress=null;
          if(navigator.vibrate)navigator.vibrate(10);
          openScheduledJobMenu(row,menu,{clientX:startX,clientY:startY,focusFirst:true});
        },SCHEDULED_JOB_LONG_PRESS_MS)
      };
    });
    row.addEventListener('pointermove',event=>{
      if(!scheduledJobLongPress||scheduledJobLongPress.pointerId!==event.pointerId)return;
      if(Math.hypot(event.clientX-scheduledJobLongPress.startX,event.clientY-scheduledJobLongPress.startY)>10)cancelScheduledJobLongPress();
    });
    ['pointerup','pointercancel','lostpointercapture'].forEach(type=>row.addEventListener(type,cancelScheduledJobLongPress));
    row.addEventListener('keydown',event=>{
      if(event.key==='ContextMenu'||(event.shiftKey&&event.key==='F10')||event.key==='Enter'||event.key===' '){
        event.preventDefault();
        openScheduledJobMenu(row,menu,{focusFirst:true});
      }
    });
    menu.addEventListener('click',event=>{
      const button=event.target.closest('[data-job-action]');
      if(!button)return;
      event.stopPropagation();
      menu.hidden=true;
      row.setAttribute('aria-expanded','false');
      row.classList.remove('is-menu-open');
      void runScheduledJobAction(job,button.dataset.jobAction,row,row);
    });
  }

  function renderScheduledJobs(){
    if(!scheduledList||!notificationsStatus)return;
    scheduledList.replaceChildren();
    syncNotificationsModeControls();
    notificationsStatus.hidden=false;
    if(scheduledLoading&&!scheduledJobs.length){
      notificationsStatus.textContent='Loading scheduled jobs…';
      return;
    }
    if(notificationsStatus)notificationsStatus.textContent=scheduledJobs.length
      ?`${scheduledJobs.length} job${scheduledJobs.length===1?'':'s'} · ${window.matchMedia('(max-width:640px)').matches?'Hold':'Right-click or hold'} for actions`
      :'No scheduled jobs.';
    const grouped=scheduledJobsByGroup();
    let menuIndex=0;
    const appendJobRow=(rows,job,groupMeta,frequencyMeta=null,{nextUp=false}={})=>{
      const row=document.createElement('article');
      row.className=`tailnet-scheduled-job${nextUp?' is-next-up':''}`;
      row.dataset.jobId=String(job.id||'');
      row.dataset.jobStatusGroup=groupMeta.key;
      const main=document.createElement('div');
      main.className='tailnet-scheduled-job-main';
      const top=document.createElement('div');
      top.className='tailnet-scheduled-job-top';
      const name=document.createElement('strong');
      name.textContent=String(job.name||job.id);
      top.append(name);
      const detail=document.createElement('div');
      detail.className='tailnet-scheduled-job-detail';
      const next=document.createElement('span');
      const timing=scheduledRelativeMeta(job,groupMeta.key);
      next.textContent=timing.text;
      next.title=timing.absolute;
      next.dataset.scheduledTimeKind=timing.kind;
      next.dataset.scheduledTimeValue=timing.value;
      next.dataset.scheduledTimeState=timing.state;
      row.classList.toggle('is-timing-late',timing.state==='late');
      row.classList.toggle('is-timing-due',timing.state==='due');
      detail.append(next);
      main.append(top,detail);
      const accessibleGroup=frequencyMeta?`${groupMeta.label}, ${frequencyMeta.label}`:groupMeta.label;
      row.dataset.jobName=String(job.name||job.id);
      row.dataset.jobGroup=accessibleGroup;
      if(frequencyMeta)row.dataset.jobFrequency=frequencyMeta.key;
      if(!job.read_only){
        const menuId=`tailnet-scheduled-job-menu-${menuIndex++}`;
        row.tabIndex=0;
        row.setAttribute('aria-label',`${job.name||job.id}. ${accessibleGroup}. ${next.textContent||'No run time available'}. Press Enter, right-click, or hold for actions.`);
        row.setAttribute('aria-haspopup','menu');
        row.setAttribute('aria-expanded','false');
        row.setAttribute('aria-controls',menuId);
        const menu=document.createElement('div');
        menu.className='tailnet-scheduled-job-menu';
        menu.id=menuId;
        menu.setAttribute('role','menu');
        menu.hidden=true;
        menu.append(scheduledJobButton('Edit','edit'));
        menu.append(scheduledJobButton('Run now','run'));
        menu.append(scheduledJobButton(job.paused||job.state==='paused'?'Resume':'Pause',job.paused||job.state==='paused'?'resume':'pause'));
        menu.append(scheduledJobButton('Delete','delete',{danger:true}));
        row.append(main,menu);
        bindScheduledJobActions(row,menu,job);
      }else{
        row.append(main);
      }
      rows.appendChild(row);
    };
    const activeJobs=grouped.get('active')||[];
    const nextUpJobs=activeJobs.filter(job=>Number.isFinite(scheduledJobTime(job,['next_run_at']))).slice(0,6);
    if(nextUpJobs.length){
      const nextUp=document.createElement('nav');
      nextUp.className='tailnet-scheduled-next-up';
      nextUp.setAttribute('aria-label','Next up');
      const nextUpLabel=document.createElement('strong');
      nextUpLabel.className='tailnet-scheduled-next-up-label';
      nextUpLabel.textContent='Next up';
      const nextUpCards=document.createElement('div');
      nextUpCards.className='tailnet-scheduled-next-up-cards';
      const activeMeta=SCHEDULED_JOB_GROUPS.find(group=>group.key==='active');
      nextUpJobs.forEach(job=>{
        const frequencyKey=scheduledActiveFrequencyKey(job);
        const frequencyMeta=ACTIVE_FREQUENCY_GROUPS.find(group=>group.key===frequencyKey)||ACTIVE_FREQUENCY_GROUPS.at(-1);
        appendJobRow(nextUpCards,job,activeMeta,frequencyMeta,{nextUp:true});
      });
      nextUp.append(nextUpLabel,nextUpCards);
      scheduledList.appendChild(nextUp);
    }
    SCHEDULED_JOB_GROUPS.forEach(groupMeta=>{
      const jobs=grouped.get(groupMeta.key)||[];
      if(!jobs.length)return;
      const group=document.createElement('section');
      group.className=`tailnet-scheduled-group is-${groupMeta.key}`;
      group.dataset.scheduledGroup=groupMeta.key;
      const heading=document.createElement('h3');
      heading.className='tailnet-scheduled-group-head';
      const headingLabel=document.createElement('strong');
      headingLabel.textContent=groupMeta.label;
      const count=document.createElement('span');
      count.className='tailnet-scheduled-group-count';
      count.textContent=`· ${jobs.length}`;
      heading.append(headingLabel,count);
      const rows=document.createElement('div');
      rows.className='tailnet-scheduled-group-rows';
      if(groupMeta.key==='active'){
        const frequencyGroups=scheduledActiveJobsByFrequency(jobs);
        ACTIVE_FREQUENCY_GROUPS.forEach(frequencyMeta=>{
          const frequencyJobs=frequencyGroups.get(frequencyMeta.key)||[];
          if(!frequencyJobs.length)return;
          const frequency=document.createElement('section');
          frequency.className=`tailnet-scheduled-frequency is-${frequencyMeta.key}`;
          frequency.dataset.scheduledFrequency=frequencyMeta.key;
          const frequencyHeading=document.createElement('h4');
          frequencyHeading.className='tailnet-scheduled-frequency-head';
          const frequencyLabel=document.createElement('strong');
          frequencyLabel.textContent=frequencyMeta.label;
          const frequencyCount=document.createElement('span');
          frequencyCount.className='tailnet-scheduled-frequency-count';
          frequencyCount.textContent=String(frequencyJobs.length);
          frequencyHeading.append(frequencyLabel,frequencyCount);
          const frequencyRows=document.createElement('div');
          frequencyRows.className='tailnet-scheduled-frequency-rows';
          frequencyJobs.forEach(job=>appendJobRow(frequencyRows,job,groupMeta,frequencyMeta));
          frequency.append(frequencyHeading,frequencyRows);
          rows.appendChild(frequency);
        });
      }else{
        jobs.forEach(job=>appendJobRow(rows,job,groupMeta));
      }
      group.append(heading,rows);
      scheduledList.appendChild(group);
    });
  }

  async function loadScheduledJobs(){
    if(scheduledLoading)return;
    scheduledLoading=true;
    if(notificationsMode==='scheduled')renderScheduledJobs();
    try{
      const [jobsPayload,statusPayload]=await Promise.all([
        api('/api/crons?all_profiles=1'),
        api('/api/crons/status').catch(()=>({running:{}}))
      ]);
      scheduledJobs=cronJobsFromPayload(jobsPayload,{includeReadOnly:true});
      scheduledRunning=statusPayload&&statusPayload.running&&typeof statusPayload.running==='object'?statusPayload.running:{};
    }catch(_){
      scheduledJobs=[];
      if(notificationsStatus)notificationsStatus.textContent='Scheduled jobs are unavailable right now.';
    }finally{
      scheduledLoading=false;
      if(notificationsMode==='scheduled')renderScheduledJobs();
    }
  }

  function openScheduledJobEditor(job,trigger){
    if(!job||job.read_only||!cronEditDialog||!cronEditMount||typeof openCronEdit!=='function')return;
    const body=document.getElementById('taskDetailBody');
    if(!body||scheduledEditorState)return;
    closeScheduledJobMenus();
    scheduledEditorState={
      body,
      parent:body.parentNode,
      nextSibling:body.nextSibling,
      jobId:String(job.id||''),
      scrollTop:notificationsPanel?notificationsPanel.scrollTop:0,
      trigger,
      saved:false
    };
    body.classList.add('is-cron-modal-body');
    cronEditMount.appendChild(body);
    if(cronEditTitle)cronEditTitle.textContent=String(job.name||job.id||'Edit job');
    if(cronEditSave){
      cronEditSave.disabled=false;
      cronEditSave.textContent='Save changes';
    }
    openCronEdit(job);
    cronEditDialog.showModal();
    requestAnimationFrame(()=>{
      body.scrollTop=0;
      const first=document.getElementById('cronFormName')||body.querySelector('input,select,textarea,button');
      if(first)first.focus({preventScroll:true});
    });
  }

  function cancelScheduledJobEditor(){
    if(!cronEditDialog||!cronEditDialog.open)return;
    if(typeof cancelCronForm==='function')cancelCronForm();
    else cronEditDialog.close();
  }

  async function finishScheduledJobEditor(){
    const state=scheduledEditorState;
    if(!state)return;
    scheduledEditorState=null;
    const {body,parent,nextSibling,jobId,scrollTop,saved,trigger}=state;
    body.classList.remove('is-cron-modal-body');
    if(parent){
      if(nextSibling&&nextSibling.parentNode===parent)parent.insertBefore(body,nextSibling);
      else parent.appendChild(body);
    }
    if(saved)await loadScheduledJobs();
    requestAnimationFrame(()=>{
      if(notificationsPanel)notificationsPanel.scrollTop=scrollTop;
      const replacement=scheduledList&&scheduledList.querySelector(`.tailnet-scheduled-job[data-job-id="${typeof CSS!=='undefined'&&CSS.escape?CSS.escape(jobId):jobId}"]`);
      const focusTarget=replacement||(trigger&&trigger.isConnected?trigger:null);
      if(focusTarget)focusTarget.focus({preventScroll:true});
    });
  }

  async function runScheduledJobAction(job,action,row,trigger){
    if(!job||job.read_only)return;
    if(action==='edit'){
      openScheduledJobEditor(job,trigger);
      return;
    }
    if(action==='delete'){
      const confirmed=typeof showConfirmDialog==='function'
        ?await showConfirmDialog({title:'Delete scheduled job?',message:`Delete “${job.name||job.id}”? Its notification history and reply threads will stay available.`,confirmLabel:'Delete',danger:true,focusCancel:true})
        :false;
      if(!confirmed)return;
    }
    row.classList.add('is-busy');
    row.querySelectorAll('button').forEach(button=>{button.disabled=true;});
    try{
      const path={run:'/api/crons/run',pause:'/api/crons/pause',resume:'/api/crons/resume',delete:'/api/crons/delete'}[action];
      if(!path)return;
      await api(path,{method:'POST',body:JSON.stringify({job_id:job.id})});
      if(typeof showToast==='function')showToast(action==='delete'?'Scheduled job deleted':action==='run'?'Scheduled job started':action==='pause'?'Scheduled job paused':'Scheduled job resumed');
      await loadScheduledJobs();
    }catch(error){
      if(typeof showToast==='function')showToast(`Scheduled job action failed: ${error.message||error}`,4000);
    }finally{
      row.classList.remove('is-busy');
      row.querySelectorAll('button').forEach(button=>{button.disabled=false;});
    }
  }

  function knownReplySessions(){
    const rows=[];
    notificationReplySessions.forEach(session=>rows.push(session));
    try{
      if(typeof _containedCronReplySessions!=='undefined'&&Array.isArray(_containedCronReplySessions))rows.push(..._containedCronReplySessions);
      if(typeof _allSessions!=='undefined'&&Array.isArray(_allSessions))rows.push(..._allSessions);
    }catch(_){}
    const deduped=new Map();
    rows.forEach(session=>{if(session&&session.session_id)deduped.set(session.session_id,session);});
    return Array.from(deduped.values());
  }

  async function findReplySession(item){
    const marker=notificationReplyMarker(item);
    const local=knownReplySessions().find(session=>String(session.title||'').startsWith(marker));
    if(local)return local;
    try{
      const payload=await api('/api/sessions');
      const rows=Array.isArray(payload&&payload.sessions)?payload.sessions:[];
      const match=rows.find(session=>String(session.title||'').startsWith(marker));
      if(match)return match;
    }catch(_){}
    return null;
  }

  async function createReplySession(item){
    const title=notificationReplyTitle(item);
    let created=null;
    let contextMode='output';
    if(item.sourceSessionId){
      try{
        const branched=await api('/api/session/branch',{
          method:'POST',
          body:JSON.stringify({session_id:item.sourceSessionId,title})
        });
        if(branched&&branched.session_id){
          created={session_id:branched.session_id,title,parent_session_id:branched.parent_session_id||item.sourceSessionId};
          contextMode='full';
        }
      }catch(_){}
    }
    if(!created){
      const body={worktree:false,project_id:null};
      try{
        if(typeof S!=='undefined'&&S.activeProfile)body.profile=S.activeProfile;
        if(typeof S!=='undefined'&&S.session&&S.session.workspace)body.workspace=S.session.workspace;
      }catch(_){}
      const payload=await api('/api/session/new',{method:'POST',body:JSON.stringify(body)});
      created=payload&&payload.session?payload.session:null;
      if(!created||!created.session_id)throw new Error('Could not create reply thread');
    }
    await api('/api/session/rename',{
      method:'POST',
      body:JSON.stringify({session_id:created.session_id,title})
    });
    try{
      await api('/api/session/move',{
        method:'POST',
        body:JSON.stringify({session_id:created.session_id,project_id:null})
      });
    }catch(_){}
    created={...created,title,contextMode};
    notificationReplySessions.set(item.key,created);
    return created;
  }

  async function resolveReplySession(item){
    const existing=await findReplySession(item);
    if(existing){
      notificationReplySessions.set(item.key,existing);
      return existing;
    }
    return createReplySession(item);
  }

  function threadMessageText(message){
    const content=message&&message.content;
    if(typeof content==='string')return content;
    if(Array.isArray(content))return content.map(part=>typeof part==='string'?part:String(part&&part.text||'')).join('\n');
    return String(content||'');
  }

  function stripNotificationContext(value){
    const source=String(value||'');
    const marker='[End notification context]';
    const index=source.indexOf(marker);
    return index>=0?source.slice(index+marker.length).trim():source;
  }

  function commonThreadPrefix(messages,parentMessages){
    const limit=Math.min(messages.length,parentMessages.length);
    let count=0;
    while(count<limit){
      const left=messages[count]||{};
      const right=parentMessages[count]||{};
      if(left.role!==right.role||threadMessageText(left)!==threadMessageText(right))break;
      count+=1;
    }
    return count;
  }

  function projectNotificationThreadStreamEvent(state,eventName,payload){
    const next={
      draft:String(state&&state.draft||''),
      liveMessages:Array.isArray(state&&state.liveMessages)?[...state.liveMessages]:[],
      clarify:state&&state.clarify||null,
      status:String(state&&state.status||'Working…')
    };
    const data=payload&&typeof payload==='object'?payload:{};
    if(eventName==='token'){
      next.draft+=String(data.text||'');
      next.status='Working…';
    }else if(eventName==='interim_assistant'){
      const text=String(data.text||'').trim();
      if(text&&!data.already_streamed&&next.liveMessages[next.liveMessages.length-1]!==text)next.liveMessages.push(text);
      next.status='Working…';
    }else if(eventName==='clarify'){
      const rawChoices=Array.isArray(data.choices_offered)?data.choices_offered:(Array.isArray(data.choices)?data.choices:[]);
      next.clarify={
        question:String(data.question||data.description||'Clarification needed'),
        choices:rawChoices.map(String),
        clarify_id:String(data.clarify_id||''),
        responding:false
      };
      next.status='Needs your input';
    }else if(eventName==='reasoning'){
      next.status='Thinking…';
    }else if(['tool','tool_start','tool_complete'].includes(eventName)){
      next.status='Working…';
    }
    return next;
  }

  function appendNotificationThreadMessage(role,text,{live=false,showLabel=true}={}){
    const row=document.createElement('article');
    row.className=`tailnet-notification-thread-message is-${role}${live?' is-live':''}`;
    if(showLabel){
      const label=document.createElement('span');
      label.textContent=role==='user'?'You':'Wizard';
      row.appendChild(label);
    }
    const body=document.createElement('div');
    body.className='msg-body';
    try{body.innerHTML=typeof renderMd==='function'?renderMd(text):text;}catch(_){body.textContent=text;}
    row.appendChild(body);
    notificationThreadMessages.appendChild(row);
    return {row,body};
  }

  function renderThreadMessages(){
    if(!notificationThreadMessages)return;
    notificationThreadMessages.replaceChildren();
    const allMessages=Array.isArray(notificationThreadSession&&notificationThreadSession.messages)?notificationThreadSession.messages:[];
    const messages=allMessages.slice(notificationThreadBaseMessages.length).filter(message=>message&&['user','assistant'].includes(message.role));
    let assistantLabelShown=false;
    const appendMessage=(role,text,options={})=>{
      if(!options.allowEmpty&&!String(text||'').trim())return null;
      const showLabel=role!=='assistant'||!assistantLabelShown;
      if(role==='assistant')assistantLabelShown=true;
      return appendNotificationThreadMessage(role,text,{...options,showLabel});
    };
    if(!messages.length&&!notificationThreadLiveMessages.length&&!notificationThreadDraft&&!notificationThreadClarify){
      const empty=document.createElement('p');
      empty.className='tailnet-notification-thread-empty';
      empty.textContent='Reply here without leaving Notifications.';
      notificationThreadMessages.appendChild(empty);
    }
    messages.forEach(message=>{
      const text=message.role==='user'?stripNotificationContext(threadMessageText(message)):threadMessageText(message);
      appendMessage(message.role,text);
    });
    notificationThreadLiveMessages.forEach(text=>appendMessage('assistant',text,{live:true}));
    if(notificationThreadDraft)appendMessage('assistant',notificationThreadDraft,{live:true});
    if(notificationThreadClarify){
      const pending=notificationThreadClarify;
      const responding=!!pending.responding;
      const {body}=appendMessage('assistant','',{live:true,allowEmpty:true});
      body.classList.add('tailnet-notification-thread-clarify');
      const question=document.createElement('div');
      question.className='clarify-question';
      question.textContent=pending.question||'Clarification needed';
      const choices=document.createElement('div');
      choices.className='clarify-choices';
      const offered=Array.isArray(pending.choices)?pending.choices:[];
      offered.forEach((choice,index)=>{
        const button=document.createElement('button');
        button.type='button';
        button.className='clarify-choice';
        button.disabled=responding;
        const badge=document.createElement('span');
        badge.className='clarify-choice-badge';
        badge.textContent=String(index+1);
        const label=document.createElement('span');
        label.className='clarify-choice-text';
        label.textContent=choice;
        button.append(badge,label);
        button.addEventListener('click',()=>void respondNotificationThreadClarify(choice));
        choices.appendChild(button);
      });
      const other=document.createElement('button');
      other.type='button';
      other.className='clarify-choice other';
      other.disabled=responding;
      const otherBadge=document.createElement('span');
      otherBadge.className='clarify-choice-badge';
      otherBadge.textContent='•';
      const otherText=document.createElement('span');
      otherText.className='clarify-choice-text';
      otherText.textContent='Other';
      other.append(otherBadge,otherText);
      choices.appendChild(other);
      const response=document.createElement('div');
      response.className='clarify-response';
      const input=document.createElement('input');
      input.className='clarify-input';
      input.type='text';
      input.autocomplete='off';
      input.placeholder='Type your response…';
      input.disabled=responding;
      const submit=document.createElement('button');
      submit.type='button';
      submit.className='clarify-submit';
      submit.textContent=responding?'Responding…':'Send';
      submit.disabled=responding;
      const send=()=>void respondNotificationThreadClarify(input.value);
      other.addEventListener('click',()=>input.focus());
      submit.addEventListener('click',send);
      input.addEventListener('keydown',event=>{
        if(event.key==='Enter'){
          event.preventDefault();
          send();
        }
      });
      response.append(input,submit);
      body.replaceChildren(question,choices,response);
    }
    notificationThreadMessages.scrollTop=notificationThreadMessages.scrollHeight;
    if(typeof requestAnimationFrame==='function')requestAnimationFrame(()=>{
      if(typeof postProcessRenderedMessages==='function')postProcessRenderedMessages(notificationThreadMessages);
    });
  }

  function threadModelLabel(){
    const model=String(notificationThreadModel.model||'');
    if(!model)return 'Default';
    try{return typeof getModelLabel==='function'?getModelLabel(model):model.split('/').pop();}catch(_){return model.split('/').pop();}
  }

  function syncNotificationThreadModel(){
    if(notificationThreadModelLabel)notificationThreadModelLabel.textContent=threadModelLabel();
    if(notificationThreadModelChip){
      notificationThreadModelChip.title=`Reply thread model: ${threadModelLabel()} · does not change the main chat`;
      notificationThreadModelChip.setAttribute('aria-label',`Reply thread model: ${threadModelLabel()}; does not change the main chat`);
    }
  }

  async function hydrateNotificationThreadModels(session=null){
    try{
      if(typeof window._ensureModelDropdownReady==='function')await window._ensureModelDropdownReady();
    }catch(_){}
    const source=document.getElementById('modelSelect');
    if(source&&notificationThreadModelSelect){
      notificationThreadModelSelect.replaceChildren(...Array.from(source.children).map(child=>child.cloneNode(true)));
    }
    const model=String(
      notificationThreadModelExplicit&&notificationThreadModel.model
        ?notificationThreadModel.model
        :(session&&session.model)||notificationThreadModel.model||(source&&source.value)||window._defaultModel||''
    );
    const provider=notificationThreadModelExplicit
      ?notificationThreadModel.model_provider
      :(session&&session.model_provider)||notificationThreadModel.model_provider||null;
    notificationThreadModel={model,model_provider:provider};
    if(notificationThreadModelSelect&&model){
      if(typeof _ensureModelOptionInDropdown==='function')_ensureModelOptionInDropdown(model,notificationThreadModelSelect,provider);
      else notificationThreadModelSelect.value=model;
    }
    syncNotificationThreadModel();
  }

  function closeNotificationThreadModelDropdown(){
    if(notificationThreadModelDropdown)notificationThreadModelDropdown.classList.remove('open');
    if(notificationThreadModelChip){
      notificationThreadModelChip.classList.remove('active');
      notificationThreadModelChip.setAttribute('aria-expanded','false');
    }
  }

  async function selectNotificationThreadModel(value,provider){
    const model=String(value||'');
    const modelProvider=String(provider||'').trim()||null;
    if(notificationThreadModelSelect){
      if(typeof _ensureModelOptionInDropdown==='function')_ensureModelOptionInDropdown(model,notificationThreadModelSelect,modelProvider);
      else notificationThreadModelSelect.value=model;
    }
    notificationThreadModel={model,model_provider:modelProvider};
    notificationThreadModelExplicit=true;
    syncNotificationThreadModel();
    closeNotificationThreadModelDropdown();
    if(notificationThreadSession&&notificationThreadSession.session_id){
      try{
        const payload=await api('/api/session/update',{
          method:'POST',
          body:JSON.stringify({session_id:notificationThreadSession.session_id,model,model_provider:modelProvider})
        });
        if(payload&&payload.session)notificationThreadSession={...notificationThreadSession,...payload.session};
      }catch(error){
        if(typeof showToast==='function')showToast(`Model update failed: ${error.message||error}`,3500);
      }
    }
  }

  async function toggleNotificationThreadModelDropdown(){
    if(!notificationThreadModelDropdown||!notificationThreadModelChip||!notificationThreadModelSelect)return;
    if(notificationThreadModelDropdown.classList.contains('open')){
      closeNotificationThreadModelDropdown();
      return;
    }
    closeNotificationThreadPrompts();
    await hydrateNotificationThreadModels(notificationThreadSession);
    if(typeof renderModelDropdown==='function'){
      renderModelDropdown({
        dropdownId:'tailnetNotificationThreadModelDropdown',
        selectId:'tailnetNotificationThreadModelSelect',
        selectModel:selectNotificationThreadModel,
        closeDropdown:closeNotificationThreadModelDropdown,
        forceOpenKey:'notification-thread',
        autoFocusSearch:!isPhoneWidth(),
        scopeNoteText:'Applies only to this notification reply thread.'
      });
    }
    notificationThreadModelDropdown.classList.add('open');
    notificationThreadModelChip.classList.add('active');
    notificationThreadModelChip.setAttribute('aria-expanded','true');
  }

  function renderNotificationThreadFiles(){
    if(!notificationThreadAttachTray)return;
    notificationThreadAttachTray.replaceChildren();
    notificationThreadAttachTray.hidden=!notificationThreadFiles.length;
    notificationThreadFiles.forEach((file,index)=>{
      const chip=document.createElement('span');
      chip.className='attach-chip';
      const label=document.createElement('span');
      label.className='attach-name';
      label.textContent=file.name;
      const remove=document.createElement('button');
      remove.type='button';
      remove.className='attach-remove';
      remove.setAttribute('aria-label',`Remove ${file.name}`);
      remove.textContent='×';
      remove.addEventListener('click',()=>{
        notificationThreadFiles.splice(index,1);
        renderNotificationThreadFiles();
        updateNotificationThreadSend();
      });
      chip.append(label,remove);
      notificationThreadAttachTray.appendChild(chip);
    });
  }

  function closeNotificationThreadPrompts(){
    if(notificationThreadPromptsPopup)notificationThreadPromptsPopup.hidden=true;
    if(notificationThreadPrompts)notificationThreadPrompts.setAttribute('aria-expanded','false');
  }

  async function toggleNotificationThreadPrompts(){
    if(!notificationThreadPromptsPopup||!notificationThreadPrompts)return;
    if(!notificationThreadPromptsPopup.hidden){closeNotificationThreadPrompts();return;}
    closeNotificationThreadModelDropdown();
    notificationThreadPromptsPopup.hidden=false;
    notificationThreadPrompts.setAttribute('aria-expanded','true');
    notificationThreadPromptsPopup.innerHTML='<div class="saved-prompts-loading">Loading…</div>';
    let prompts=[];
    try{
      const data=await api('/api/prompts');
      prompts=Array.isArray(data&&data.prompts)?data.prompts:[];
    }catch(_){}
    notificationThreadPromptsPopup.replaceChildren();
    if(!prompts.length){
      const empty=document.createElement('div');
      empty.className='saved-prompts-empty';
      empty.textContent='No saved prompts yet.';
      notificationThreadPromptsPopup.appendChild(empty);
      return;
    }
    prompts.forEach(prompt=>{
      const row=document.createElement('button');
      row.type='button';
      row.className='saved-prompt-row tailnet-notification-thread-prompt';
      row.setAttribute('role','menuitem');
      row.textContent=prompt.label||prompt.text;
      row.title=prompt.text;
      row.addEventListener('click',()=>{
        if(notificationThreadInput){
          const prefix=notificationThreadInput.value.trim()?notificationThreadInput.value.replace(/\s*$/,'\n\n'):'';
          notificationThreadInput.value=prefix+String(prompt.text||'');
          autoResizeNotificationThreadInput();
          updateNotificationThreadSend();
          notificationThreadInput.focus();
        }
        closeNotificationThreadPrompts();
      });
      notificationThreadPromptsPopup.appendChild(row);
    });
  }

  function autoResizeNotificationThreadInput(){
    if(!notificationThreadInput)return;
    notificationThreadInput.style.height='auto';
    notificationThreadInput.style.height=`${Math.min(160,Math.max(24,notificationThreadInput.scrollHeight))}px`;
  }

  function updateNotificationThreadSend(){
    if(!notificationThreadSend)return;
    const hasContent=!!String(notificationThreadInput&&notificationThreadInput.value||'').trim()||notificationThreadFiles.length>0;
    notificationThreadSend.disabled=!!notificationThreadStreamId||!hasContent;
  }

  function setThreadBusy(busy,status=''){
    if(notificationThreadInput)notificationThreadInput.disabled=!!busy;
    if(notificationThreadSend)notificationThreadSend.hidden=!!busy;
    if(notificationThreadStop)notificationThreadStop.hidden=!busy;
    [notificationThreadAttach,notificationThreadPrompts,notificationThreadModelChip].forEach(control=>{if(control)control.disabled=!!busy;});
    if(notificationThreadStatus){
      notificationThreadStatus.textContent=status;
      notificationThreadStatus.style.display=status?'':'none';
    }
    updateNotificationThreadSend();
  }

  async function loadReplySessionTranscript(sessionId,{attach=true}={}){
    const payload=await api(`/api/session?session_id=${encodeURIComponent(sessionId)}&messages=1&resolve_model=0&msg_limit=1000`,{timeoutMs:120000});
    const session=payload&&payload.session?payload.session:payload;
    if(!session||!session.session_id)throw new Error('Reply thread is unavailable');
    notificationThreadSession=session;
    await hydrateNotificationThreadModels(session);
    notificationThreadBaseMessages=[];
    notificationThreadSource=null;
    if(session.parent_session_id){
      try{
        const parentPayload=await api(`/api/session?session_id=${encodeURIComponent(session.parent_session_id)}&messages=1&resolve_model=0&msg_limit=1000`,{timeoutMs:120000});
        const parent=parentPayload&&parentPayload.session?parentPayload.session:parentPayload;
        const parentMessages=Array.isArray(parent&&parent.messages)?parent.messages:[];
        const messages=Array.isArray(session.messages)?session.messages:[];
        const count=commonThreadPrefix(messages,parentMessages);
        notificationThreadBaseMessages=messages.slice(0,count);
        notificationThreadSource=parent;
      }catch(_){}
    }
    renderThreadMessages();
    const fullContext=!!session.parent_session_id;
    if(notificationThreadContext)notificationThreadContext.textContent=fullContext?'Full run context':'Notification output context';
    const activeStream=String(session.active_stream_id||'');
    setThreadBusy(!!activeStream,activeStream?'Working…':'');
    if(attach&&activeStream)attachNotificationThreadStream(activeStream);
    return session;
  }

  async function openNotificationThread(item){
    notificationThreadItem=item;
    notificationThreadSession=null;
    notificationThreadBaseMessages=[];
    notificationThreadSource=null;
    notificationThreadDraft='';
    notificationThreadLiveMessages=[];
    notificationThreadClarify=null;
    notificationThreadFiles=[];
    notificationThreadModel={model:'',model_provider:null};
    notificationThreadModelExplicit=false;
    notificationsMode='notifications';
    syncNotificationsModeControls();
    if(notificationsPanel)notificationsPanel.scrollTop=0;
    if(notificationThreadBack)notificationThreadBack.focus({preventScroll:true});
    if(notificationsStatus)notificationsStatus.hidden=true;
    if(notificationThreadTitle)notificationThreadTitle.textContent=item.name;
    if(notificationThreadContext)notificationThreadContext.textContent=item.sourceSessionId?'Full run context available':'Notification output context';
    if(notificationThreadPinned){
      notificationThreadPinned.dataset.richReady='';
      notificationThreadPinned.replaceChildren();
      hydrateNotificationRich(notificationThreadPinned,item);
    }
    if(notificationIsUnread(item))markNotificationRead(item);
    renderNotificationThreadFiles();
    void hydrateNotificationThreadModels();
    renderThreadMessages();
    setThreadBusy(false,'');
    try{
      const session=await findReplySession(item);
      if(session)await loadReplySessionTranscript(session.session_id);
    }catch(error){
      if(notificationThreadContext)notificationThreadContext.textContent=item.sourceSessionId?'Full run context available':'Notification output context';
      setThreadBusy(false,'');
    }
  }

  function applyNotificationThreadStreamEvent(eventName,event){
    let payload={};
    try{payload=JSON.parse(event&&event.data||'{}');}catch(_){}
    const next=projectNotificationThreadStreamEvent({
      draft:notificationThreadDraft,
      liveMessages:notificationThreadLiveMessages,
      clarify:notificationThreadClarify,
      status:String(notificationThreadStatus&&notificationThreadStatus.textContent||'Working…')
    },eventName,payload);
    notificationThreadDraft=next.draft;
    notificationThreadLiveMessages=next.liveMessages;
    notificationThreadClarify=next.clarify;
    renderThreadMessages();
    setThreadBusy(true,next.status);
  }

  async function respondNotificationThreadClarify(response){
    const pending=notificationThreadClarify;
    const sid=String(notificationThreadSession&&notificationThreadSession.session_id||'');
    const value=String(response||'').trim();
    if(!pending||!sid||!value||pending.responding)return;
    const clarifyId=String(pending.clarify_id||'');
    notificationThreadClarify={...pending,responding:true};
    renderThreadMessages();
    setThreadBusy(true,'Responding…');
    try{
      const result=await api('/api/clarify/respond',{
        method:'POST',
        body:JSON.stringify({session_id:sid,response:value,clarify_id:clarifyId})
      });
      if(!result||!result.ok)throw new Error(result&&result.error||'Clarification response was not accepted');
      if(notificationThreadClarify&&String(notificationThreadClarify.clarify_id||'')===clarifyId){
        notificationThreadClarify=null;
        if(notificationThreadSession&&notificationThreadSession.session_id===sid){
          notificationThreadSession.messages=Array.isArray(notificationThreadSession.messages)?notificationThreadSession.messages:[];
          notificationThreadSession.messages.push({role:'user',content:value,_clarify_response:true});
        }
        renderThreadMessages();
        setThreadBusy(true,'Working…');
      }
    }catch(error){
      const same=notificationThreadClarify&&String(notificationThreadClarify.clarify_id||'')===clarifyId;
      if(error&&error.status===409&&same){
        notificationThreadClarify=null;
        renderThreadMessages();
        setThreadBusy(true,'Working…');
        if(typeof showToast==='function')showToast('Clarification expired; the thread has been refreshed.',4000);
        void loadReplySessionTranscript(sid,{attach:false}).catch(()=>{});
        return;
      }
      if(same)notificationThreadClarify={...notificationThreadClarify,responding:false};
      renderThreadMessages();
      setThreadBusy(true,'Needs your input');
      if(typeof showToast==='function')showToast(`Clarification failed: ${error.message||error}`,4000);
    }
  }

  function attachNotificationThreadStream(streamId){
    const id=String(streamId||'');
    if(!id)return;
    if(notificationThreadStream&&notificationThreadStreamId===id)return;
    if(notificationThreadStream)notificationThreadStream.close();
    notificationThreadStreamId=id;
    notificationThreadDraft='';
    notificationThreadLiveMessages=[];
    notificationThreadClarify=null;
    setThreadBusy(true,'Working…');
    const source=new EventSource(new URL(`api/chat/stream?stream_id=${encodeURIComponent(id)}`,document.baseURI||location.href).href,{withCredentials:true});
    notificationThreadStream=source;
    let terminal=false;
    const seenEventIds=new Set();
    const listen=(eventName,handler)=>{
      source.addEventListener(eventName,event=>{
        const eventId=String(event&&event.lastEventId||'');
        if(eventId&&seenEventIds.has(eventId))return;
        if(eventId)seenEventIds.add(eventId);
        handler(event);
      });
    };
    const settle=async label=>{
      if(terminal)return;
      terminal=true;
      source.close();
      if(notificationThreadStream===source)notificationThreadStream=null;
      notificationThreadStreamId='';
      notificationThreadDraft='';
      notificationThreadLiveMessages=[];
      notificationThreadClarify=null;
      if(notificationThreadSession&&notificationThreadItem){
        try{await loadReplySessionTranscript(notificationThreadSession.session_id,{attach:false});}
        catch(_){setThreadBusy(false,label||'Reply saved');}
      }
    };
    ['token','interim_assistant','reasoning','tool','tool_start','tool_complete','clarify'].forEach(eventName=>{
      listen(eventName,event=>applyNotificationThreadStreamEvent(eventName,event));
    });
    source.addEventListener('done',()=>{void settle('Reply saved');});
    source.addEventListener('cancel',()=>{void settle('Stopped');});
    source.addEventListener('stream_end',()=>{void settle('Reply saved');});
    source.addEventListener('error',event=>{
      if(event&&event.data){
        try{
          const payload=JSON.parse(event.data);
          if(typeof showToast==='function')showToast(payload.error||'Reply failed',4000);
        }catch(_){}
        void settle('Reply failed');
      }else if(!terminal){
        setThreadBusy(true,'Reconnecting…');
      }
    });
  }

  function notificationContextMessage(item,reply){
    return `[Notification context]\nJob: ${item.name}\nRun: ${new Date(item.modified*1000).toLocaleString()}\nOutput:\n${item.response}\n[End notification context]\n\n${reply}`;
  }

  async function sendNotificationThreadReply(event){
    if(event)event.preventDefault();
    if(!notificationThreadItem||notificationThreadStreamId)return;
    const reply=String(notificationThreadInput&&notificationThreadInput.value||'').trim();
    const filesSnapshot=[...notificationThreadFiles];
    if(!reply&&!filesSnapshot.length)return;
    try{
      if(!notificationThreadSession){
        setThreadBusy(true,notificationThreadItem.sourceSessionId?'Preparing full context…':'Preparing output context…');
        const resolved=await resolveReplySession(notificationThreadItem);
        await loadReplySessionTranscript(resolved.session_id,{attach:false});
      }
      let uploaded=[];
      if(filesSnapshot.length){
        setThreadBusy(true,'Uploading…');
        if(typeof uploadPendingFiles!=='function')throw new Error('File upload is unavailable');
        uploaded=await uploadPendingFiles({clearPending:false,sessionId:notificationThreadSession.session_id,files:filesSnapshot});
      }
      const uploadedPaths=uploaded.map(file=>file&&file.path?file.path:(file&&file.name?file.name:(file&&file.filename?file.filename:file)));
      let messageText=reply;
      if(uploadedPaths.length&&!messageText)messageText=`I've uploaded ${uploadedPaths.length} file(s): ${uploadedPaths.join(', ')}`;
      else if(uploadedPaths.length)messageText=`${messageText}\n\n[Attached files: ${uploadedPaths.join(', ')}]`;
      const visibleMessages=(notificationThreadSession.messages||[]).slice(notificationThreadBaseMessages.length);
      const firstFallbackTurn=!notificationThreadSession.parent_session_id&&!visibleMessages.some(message=>message&&message.role==='user');
      const wireMessage=firstFallbackTurn?notificationContextMessage(notificationThreadItem,messageText):messageText;
      notificationThreadSession.messages=Array.isArray(notificationThreadSession.messages)?notificationThreadSession.messages:[];
      notificationThreadSession.messages.push({role:'user',content:wireMessage});
      renderThreadMessages();
      setThreadBusy(true,'Starting…');
      const body={
        session_id:notificationThreadSession.session_id,
        message:wireMessage,
        model:notificationThreadModel.model||notificationThreadSession.model||undefined,
        model_provider:notificationThreadModel.model_provider||notificationThreadSession.model_provider||undefined,
        explicit_model_pick:notificationThreadModelExplicit||undefined,
        attachments:uploaded.length?uploaded:undefined,
        profile:notificationThreadSession.profile||undefined,
        source:'webui'
      };
      const payload=await api('/api/chat/start',{method:'POST',body:JSON.stringify(body),timeoutMs:120000});
      if(!payload||!payload.stream_id)throw new Error(payload&&payload.error||'Reply did not start');
      if(notificationThreadInput){notificationThreadInput.value='';notificationThreadInput.style.height='';}
      notificationThreadFiles=[];
      if(notificationThreadFileInput)notificationThreadFileInput.value='';
      renderNotificationThreadFiles();
      attachNotificationThreadStream(payload.stream_id);
    }catch(error){
      setThreadBusy(false,'');
      if(typeof showToast==='function')showToast(`Reply failed: ${error.message||error}`,4000);
      if(notificationThreadSession)void loadReplySessionTranscript(notificationThreadSession.session_id,{attach:false}).catch(()=>{});
    }
  }

  async function stopNotificationThreadReply(){
    if(!notificationThreadStreamId)return;
    try{
      await api(`/api/chat/cancel?stream_id=${encodeURIComponent(notificationThreadStreamId)}`);
      setThreadBusy(true,'Stopping…');
    }catch(error){
      if(typeof showToast==='function')showToast(`Stop failed: ${error.message||error}`,4000);
    }
  }

  function activateNotifications(){
    if(!workspace||!notificationsPanel)return;
    setMobileUtilitiesOpen(false);
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
    if(notificationThreadItem)closeNotificationThread();
    notificationsMode='notifications';
    syncNotificationsModeControls();
    setNotificationFilter('unread');
    void loadCronNotifications({fullRefresh:!notificationItems.size});
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
    const externalLinks=document.querySelectorAll('.tailnet-app-rail [data-tailnet-app-id],.mobile-primary-menu [data-tailnet-app-id]');
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
    syncMobilePrimaryMenu();
  }

  function activateHermes({remember=true}={}){
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
    setMobileUtilitiesOpen(false);
    closeSessionsOverlay();
    if(remember){
      try{sessionStorage.removeItem(STORAGE_KEY);}catch(_){}
    }
    document.dispatchEvent(new CustomEvent('hermesui:tailnet-app-selected',{detail:{id:'hermes-ui'}}));
  }

  function rememberMobileTailnetApp(app,{token='',generation='',browserFallback=false}={}){
    const id=String(app&&app.id||'');
    if(!id||id===NOTIFICATIONS_ID)return;
    lastMobileAppSnapshot={id,token:String(token||''),generation:String(generation||''),browserFallback:!!browserFallback};
    try{sessionStorage.setItem(MOBILE_LAST_APP_STORAGE_KEY,id);}catch(_){}
  }

  function activateApp(app,{bookmarkGeneration=''}={}){
    if(!workspace||!frame)return;
    setMobileUtilitiesOpen(false);
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
    rememberMobileTailnetApp(app,{
      token,
      generation:activeBookmarkNavigation&&activeBookmarkNavigation.generation||'',
      browserFallback:false
    });
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
    rememberMobileTailnetApp(app,{token:bookmarkToken(app),browserFallback:true});
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

  function readLastMobileTailnetAppId(){
    if(lastMobileAppSnapshot.id)return lastMobileAppSnapshot.id;
    try{return sessionStorage.getItem(MOBILE_LAST_APP_STORAGE_KEY)||'';}catch(_){return '';}
  }

  function restoreLastMobileTailnetApp(){
    if(!isPhoneWidth())return false;
    const id=readLastMobileTailnetAppId();
    if(!id||id===NOTIFICATIONS_ID)return false;
    const app=appsById.get(id);
    if(app){
      if(lastMobileAppSnapshot.id===id&&lastMobileAppSnapshot.browserFallback){
        activateBrowserFallback(app,{open:false});
      }else{
        const bookmarkGeneration=lastMobileAppSnapshot.id===id?lastMobileAppSnapshot.generation:'';
        activateApp(app,{bookmarkGeneration});
      }
      return true;
    }
    if(typeof window.hermesTailnetManagerRestoreApp==='function'){
      return window.hermesTailnetManagerRestoreApp(id)===true;
    }
    return false;
  }

  function openMobileSessionsFromTailnet(){
    if(!isPhoneWidth()||root.dataset.tailnetView!=='external')return false;
    if(activeId===NOTIFICATIONS_ID&&notificationThreadItem){
      closeNotificationThread();
      return false;
    }
    activateHermes({remember:false});
    if(typeof window.openMobileSessionPage==='function')window.openMobileSessionPage();
    return true;
  }

  function closeMobileUtilitiesForLayerGesture(){
    if(!mobileUtilityIsOpen())return false;
    setMobileUtilitiesOpen(false);
    return true;
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
    const placeLeft=rect.left>window.innerWidth/2;
    const desiredLeft=placeLeft?rect.left-width-8:rect.right+8;
    node.style.left=`${Math.max(8,Math.min(window.innerWidth-width-8,desiredLeft))}px`;
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
    const width=menu.offsetWidth;
    const height=menu.offsetHeight;
    const anchorX=Number.isFinite(clientX)?clientX:(rect.left>window.innerWidth/2?rect.left:rect.right);
    const x=anchorX>window.innerWidth/2?Math.min(rect.left,anchorX)-width-8:Math.max(rect.right,anchorX)+8;
    const y=Number.isFinite(clientY)?clientY:rect.top;
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
    if(!links||!home||!workspace||!frame||!privateAdd||!notificationsButton||!notificationsPanel)return;
    root.setAttribute('data-tailnet-view','hermes');
    bindOverlayInteractions();
    home.addEventListener('click',event=>{
      event.preventDefault();
      activateHermes();
    });
    notificationsButton.addEventListener('click',activateNotifications);
    bindMobilePrimaryMenu();
    bindMobileRail();
    if(themeToggle)themeToggle.addEventListener('click',toggleShellTheme);
    bindMobileUtilities();
    if(wizardCanvasFrame)wizardCanvasFrame.addEventListener('load',sendThemeToWizardCanvas);
    new MutationObserver(syncThemeToggle).observe(root,{attributes:true,attributeFilter:['class','data-skin']});
    new MutationObserver(syncMobileUtilities).observe(root,{attributes:true,attributeFilter:['class','data-session-view']});
    new MutationObserver(syncMobilePrimaryMenu).observe(root,{attributes:true,attributeFilter:['data-tailnet-view','data-mobile-session-view']});
    window.addEventListener('resize',syncMobilePrimaryMenu,{passive:true});
    syncThemeToggle();
    syncMobilePrimaryMenu();
    if(notificationsReadAll)notificationsReadAll.addEventListener('click',markAllNotificationsRead);
    notificationFilterButtons.forEach(button=>button.addEventListener('click',()=>setNotificationFilter(button.dataset.notificationFilter)));
    notificationsModeButtons.forEach(button=>button.addEventListener('click',()=>setNotificationsMode(button.dataset.notificationsMode)));
    if(scheduledRefresh)scheduledRefresh.addEventListener('click',()=>void loadScheduledJobs());
    window.setInterval(()=>{if(!document.hidden&&notificationsMode==='scheduled')refreshScheduledRelativeTimes();},30000);
    document.addEventListener('visibilitychange',()=>{if(!document.hidden&&notificationsMode==='scheduled')refreshScheduledRelativeTimes();});
    if(scheduledNew)scheduledNew.addEventListener('click',async()=>{
      activateHermes({remember:false});
      if(typeof switchPanel==='function')await switchPanel('tasks');
      if(typeof openCronCreate==='function')openCronCreate();
    });
    document.addEventListener('pointerdown',event=>{
      if(!(event.target instanceof Element)||!event.target.closest('.tailnet-scheduled-job-menu'))closeScheduledJobMenus();
      if(!(event.target instanceof Element)||(!event.target.closest('#tailnetNotificationThreadPromptsPopup')&&!event.target.closest('#tailnetNotificationThreadPrompts')))closeNotificationThreadPrompts();
      if(!(event.target instanceof Element)||(!event.target.closest('#tailnetNotificationThreadModelDropdown')&&!event.target.closest('#tailnetNotificationThreadModelChip')))closeNotificationThreadModelDropdown();
    });
    document.addEventListener('keydown',event=>{
      if(event.key==='Escape'&&scheduledList&&scheduledList.querySelector('.tailnet-scheduled-job-menu:not([hidden])')){
        event.preventDefault();
        closeScheduledJobMenus({restoreFocus:true});
      }
    });
    if(cronEditDialog){
      if(cronEditClose)cronEditClose.addEventListener('click',cancelScheduledJobEditor);
      if(cronEditCancel)cronEditCancel.addEventListener('click',cancelScheduledJobEditor);
      if(cronEditSave)cronEditSave.addEventListener('click',async()=>{
        if(typeof saveCronForm!=='function')return;
        cronEditSave.disabled=true;
        cronEditSave.textContent='Saving…';
        try{await saveCronForm();}
        finally{
          cronEditSave.disabled=false;
          cronEditSave.textContent='Save changes';
        }
      });
      cronEditDialog.addEventListener('cancel',event=>{
        event.preventDefault();
        cancelScheduledJobEditor();
      });
      cronEditDialog.addEventListener('click',event=>{
        if(event.target===cronEditDialog)cancelScheduledJobEditor();
      });
      cronEditDialog.addEventListener('close',()=>void finishScheduledJobEditor());
      document.addEventListener('hermesui:cron-form-cancelled',()=>{
        if(cronEditDialog.open)cronEditDialog.close();
      });
      document.addEventListener('hermesui:cron-form-saved',event=>{
        if(!cronEditDialog.open||!scheduledEditorState)return;
        scheduledEditorState.saved=true;
        scheduledEditorState.jobId=String(event&&event.detail&&event.detail.jobId||scheduledEditorState.jobId);
        cronEditDialog.close();
      });
    }
    if(notificationThreadBack)notificationThreadBack.addEventListener('click',closeNotificationThread);
    if(notificationThreadComposer)notificationThreadComposer.addEventListener('submit',sendNotificationThreadReply);
    if(notificationThreadStop)notificationThreadStop.addEventListener('click',()=>void stopNotificationThreadReply());
    if(notificationThreadInput){
      notificationThreadInput.addEventListener('input',()=>{
        autoResizeNotificationThreadInput();
        updateNotificationThreadSend();
      });
      notificationThreadInput.addEventListener('keydown',event=>{
        if(event.key==='Enter'&&!event.shiftKey&&!event.isComposing){
          event.preventDefault();
          if(!notificationThreadSend||!notificationThreadSend.disabled)void sendNotificationThreadReply(event);
        }
      });
    }
    if(notificationThreadAttach&&notificationThreadFileInput){
      notificationThreadAttach.addEventListener('click',()=>notificationThreadFileInput.click());
      notificationThreadFileInput.addEventListener('change',()=>{
        notificationThreadFiles.push(...Array.from(notificationThreadFileInput.files||[]));
        notificationThreadFileInput.value='';
        renderNotificationThreadFiles();
        updateNotificationThreadSend();
      });
    }
    if(notificationThreadPrompts)notificationThreadPrompts.addEventListener('click',()=>void toggleNotificationThreadPrompts());
    if(notificationThreadModelChip)notificationThreadModelChip.addEventListener('click',()=>void toggleNotificationThreadModelDropdown());
    appsById.set(privateMarketplace.id,privateMarketplace);
    privateAdd.addEventListener('click',()=>activateApp(privateMarketplace));
    document.addEventListener('hermesui:tailnet-app-selected',event=>{
      const id=event&&event.detail&&event.detail.id;
      if(id&&id!==NOTIFICATIONS_ID&&notificationThreadItem)closeNotificationThread();
      if(!id||id==='hermes-ui')return;
      activeId=id;
      if(wizardHome)wizardHome.hidden=true;
      if(notificationsPanel&&id!==NOTIFICATIONS_ID)notificationsPanel.hidden=true;
    });
    document.addEventListener('hermesui:cron-completions',event=>{
      const completions=event&&event.detail&&Array.isArray(event.detail.completions)?event.detail.completions:[];
      const jobIds=Array.from(new Set(completions.map(item=>String(item&&item.job_id||'')).filter(Boolean)));
      if(jobIds.length)void loadCronNotifications({jobIds});
    });
    let remembered='';
    try{remembered=sessionStorage.getItem(STORAGE_KEY)||'';}catch(_){}
    if(remembered&&appsById.has(remembered))activateApp(appsById.get(remembered));
    else activateHermes({remember:false});
    renderCronNotifications();
    scheduleNotificationRefresh();
    const desktopHomeMedia=window.matchMedia('(min-width:901px)');
    const syncHomeAcrossBreakpoint=()=>{if(!activeId)activateHermes({remember:false});};
    if(typeof desktopHomeMedia.addEventListener==='function')desktopHomeMedia.addEventListener('change',syncHomeAcrossBreakpoint);
    else if(typeof desktopHomeMedia.addListener==='function')desktopHomeMedia.addListener(syncHomeAcrossBreakpoint);
    root.dataset.tailnetAppsReady='true';
    document.dispatchEvent(new CustomEvent('hermesui:tailnet-apps-ready',{detail:{
      count:2,
      privateCount:0,
      companyCount:0,
      publicCount:0,
      scope:'private-only',
      activeId:activeId||'hermes-ui'
    }}));
  }

  window.hermesMobileTailnetNavigation={
    restoreLastApp:restoreLastMobileTailnetApp,
    openSessions:openMobileSessionsFromTailnet,
    closeUtilities:closeMobileUtilitiesForLayerGesture,
    hasLastApp:()=>Boolean(readLastMobileTailnetAppId())
  };

  loadApps();
})();
