/* HermesUI: mobile, frontend-only session tabs and swipe navigation. */
(function(){
  'use strict';
  if(window.__sessionSwipeNavigationInstalled) return;
  window.__sessionSwipeNavigationInstalled=true;

  const PHONE_QUERY='(max-width: 640px)';
  const COARSE_QUERY='(pointer: coarse)';
  const LOCK_DISTANCE=10;
  const COMMIT_DISTANCE_RATIO=.28;
  const COMMIT_DISTANCE_MAX=128;
  const COMMIT_DISTANCE_MIN=84;
  const FLICK_MIN_DISTANCE=38;
  const FLICK_VELOCITY=.58;
  const EDGE_GUARD=22;
  const INTERACTIVE_SELECTOR='button,a,input,textarea,select,option,label,[contenteditable="true"],pre,code,.markdown-table-wrap,.session-view-switcher,.session-jump-btn,.scroll-to-bottom-btn';

  const byId=id=>document.getElementById(id);
  const state=()=>typeof S!=='undefined'&&S?S:{session:null};
  const media=query=>typeof window.matchMedia==='function'&&window.matchMedia(query).matches;
  const enabled=()=>media(PHONE_QUERY)&&media(COARSE_QUERY);
  const reducedMotion=()=>media('(prefers-reduced-motion: reduce)');
  const currentSid=()=>String(state().session&&state().session.session_id||'');
  const unique=values=>[...new Set((values||[]).filter(Boolean).map(String))];

  function visibleSessionIds(){
    if(typeof _sessionVisibleSidebarIds!=='undefined'&&Array.isArray(_sessionVisibleSidebarIds)){
      const ids=unique(_sessionVisibleSidebarIds);
      if(ids.length) return ids;
    }
    const list=byId('sessionList');
    if(!list) return [];
    return unique([...list.querySelectorAll('.session-item[data-sid],.session-child-session-fork[data-sid]')]
      .map(row=>row.dataset.sid));
  }

  function sidebarTitle(sid){
    const row=sidebarRow(sid);
    if(!row) return '';
    const label=row.querySelector('.session-title,.session-name,.session-item-title');
    return String(label&&label.textContent||row.getAttribute('aria-label')||'').trim();
  }

  function sidebarRow(sid){
    const list=byId('sessionList');
    if(!list) return null;
    return [...list.querySelectorAll('[data-sid]')]
      .find(item=>String(item.dataset.sid||'')===String(sid||''))||null;
  }

  function tabSessionState(sid){
    const row=sidebarRow(sid);
    if(!row) return {streaming:false,unread:false,attention:''};
    const streaming=row.classList.contains('streaming');
    const unread=!streaming&&row.classList.contains('unread');
    let attention='';
    if(row.classList.contains('attention-approval')) attention='approval';
    else if(row.classList.contains('attention-clarify')) attention='clarify';
    else if(row.classList.contains('needs-attention')) attention='generic';
    return {streaming,unread,attention};
  }

  function tabSessionStateKey(sid){
    const visual=tabSessionState(sid);
    return `${visual.streaming?'running':''}:${visual.unread?'unread':''}:${visual.attention}`;
  }

  function sessionForSid(sid){
    const id=String(sid||'');
    if(!id) return null;
    const active=state().session;
    if(active&&String(active.session_id||'')===id) return active;
    const row=typeof _allSessions!=='undefined'&&Array.isArray(_allSessions)
      ? _allSessions.find(session=>session&&String(session.session_id)===id)
      : null;
    return row||{session_id:id,title:sidebarTitle(id)||'Session'};
  }

  function adjacentSession(direction){
    const sid=currentSid();
    const ids=visibleSessionIds();
    const index=ids.indexOf(sid);
    if(!sid||index<0) return null;
    // The sidebar is newest-first: left advances to the next older row;
    // right returns to the previous newer row.
    const targetSid=ids[index+(direction<0?1:-1)];
    return targetSid?sessionForSid(targetSid):null;
  }

  function displayTitle(session){
    return String(session&&(session.display_title||session.title)||'Session').trim()||'Session';
  }

  function tabSessions(){
    const ids=visibleSessionIds();
    const sid=currentSid();
    if(!sid) return [];
    if(!ids.includes(sid)) ids.unshift(sid);
    return ids.map(sessionForSid).filter(Boolean);
  }

  let gesture=null;
  let switching=false;
  let contentLoadingDepth=0;
  let pane=null;
  let surface=null;
  let tabsViewport=null;
  let tabList=null;
  let tabSyncFrame=null;
  let tabCenterFrame=null;
  let tabsObserver=null;
  let pendingTabSync=false;
  let tabSignature='';
  let lastActiveSid=null;


  function setTabMetrics(){
    if(!tabsViewport) return;
    const width=tabsViewport.getBoundingClientRect().width||tabsViewport.clientWidth||0;
    if(!width) return;
    const tabWidth=Math.max(160,Math.min(240,width*.62));
    tabsViewport.style.setProperty('--mobile-session-tab-width',`${Math.round(tabWidth)}px`);
    tabsViewport.style.setProperty('--mobile-session-tab-gutter',`${Math.max(0,Math.round((width-tabWidth)/2))}px`);
    tabsViewport.style.setProperty('--mobile-session-end-gutter',`${Math.max(0,Math.round((width-40)/2))}px`);
  }

  function centerActiveTab(behavior='smooth'){
    if(!tabsViewport||!tabList) return;
    if(tabCenterFrame) cancelAnimationFrame(tabCenterFrame);
    tabCenterFrame=requestAnimationFrame(()=>{
      const place=()=>{
        const active=tabList.querySelector('.mobile-session-tab[aria-selected="true"]');
        if(!active) return;
        const viewportRect=tabsViewport.getBoundingClientRect();
        const activeRect=active.getBoundingClientRect();
        const left=Math.max(0,tabsViewport.scrollLeft+(activeRect.left-viewportRect.left)-(tabsViewport.clientWidth-activeRect.width)/2);
        if(behavior==='smooth'&&typeof tabsViewport.scrollTo==='function') tabsViewport.scrollTo({left,behavior});
        else tabsViewport.scrollLeft=left;
      };
      place();
      if(behavior==='auto'){
        tabCenterFrame=requestAnimationFrame(()=>{place();tabCenterFrame=null;});
      }else{
        tabCenterFrame=null;
      }
    });
  }

  function buildTab(session,activeSid){
    const sid=String(session&&session.session_id||'');
    const isCurrent=!!sid&&sid===activeSid;
    const label=displayTitle(session);
    const tab=document.createElement('button');
    tab.className='mobile-session-tab';
    tab.type='button';
    tab.setAttribute('role','tab');
    tab.setAttribute('aria-selected',isCurrent?'true':'false');
    const visual=tabSessionState(sid);
    const statusLabel=visual.attention==='approval'?'approval required'
      :visual.attention==='clarify'?'clarification required'
      :visual.attention?'attention required'
      :visual.streaming?'running'
      :visual.unread?'unread':'';
    tab.setAttribute('aria-label',(isCurrent?`Current session: ${label}`:`Open session: ${label}`)+(statusLabel?`, ${statusLabel}`:''));
    tab.tabIndex=isCurrent?0:-1;
    tab.title=label;
    tab.dataset.sid=sid;
    if(isCurrent) tab.setAttribute('aria-current','page');

    const title=document.createElement('span');
    title.className='mobile-session-tab-title';
    title.textContent=label;
    tab.appendChild(title);
    if(visual.streaming||visual.unread||visual.attention){
      tab.classList.add('has-session-state');
      const indicator=document.createElement('span');
      indicator.className='mobile-session-tab-state session-state-indicator'
        +(visual.streaming?' is-streaming':(visual.unread?' is-unread':''))
        +(visual.attention?` is-attention-${visual.attention}`:'');
      indicator.setAttribute('aria-hidden','true');
      tab.appendChild(indicator);
    }
    return tab;
  }

  function syncTabs(forceCenter=false){
    tabSyncFrame=null;
    if(!tabList||!tabsViewport) return;
    if(typeof syncMobileSessionNavigation==='function') syncMobileSessionNavigation();
    setTabMetrics();
    const activeSid=currentSid();
    const sessions=tabSessions();
    const nextSignature=JSON.stringify(sessions.map(session=>[
      String(session.session_id||''),
      displayTitle(session),
      String(session.session_id||'')===activeSid,
      tabSessionStateKey(session.session_id),
    ]));
    const activeChanged=lastActiveSid!==activeSid;
    if(nextSignature!==tabSignature){
      const oldScroll=tabsViewport.scrollLeft;
      tabList.replaceChildren(...sessions.map(session=>buildTab(session,activeSid)));
      tabSignature=nextSignature;
      if(!activeChanged&&!forceCenter) tabsViewport.scrollLeft=oldScroll;
    }
    if(forceCenter||activeChanged||lastActiveSid===null){
      centerActiveTab('auto');
    }
    lastActiveSid=activeSid;
  }

  function scheduleTabSync(){
    if(switching){pendingTabSync=true;return;}
    if(tabSyncFrame!==null) return;
    tabSyncFrame=window.requestAnimationFrame(()=>syncTabs(false));
  }

  function ensureContentSkeleton(){
    let skeleton=byId('sessionSwitchSkeleton');
    if(skeleton) return skeleton;
    const messages=byId('messages');
    if(!messages) return null;
    skeleton=document.createElement('section');
    skeleton.id='sessionSwitchSkeleton';
    skeleton.className='session-switch-skeleton';
    skeleton.setAttribute('role','status');
    skeleton.setAttribute('aria-label','Loading session content');
    skeleton.hidden=true;
    skeleton.innerHTML='<span class="sr-only">Loading session content</span><header class="session-switch-skeleton-original" aria-hidden="true"><span class="session-switch-skeleton-label"></span><span class="session-switch-skeleton-line session-switch-skeleton-line--wide"></span><span class="session-switch-skeleton-line session-switch-skeleton-line--medium"></span></header>'
      +'<article class="session-switch-skeleton-card" aria-hidden="true"><span class="session-switch-skeleton-label"></span><span class="session-switch-skeleton-line session-switch-skeleton-line--wide"></span><span class="session-switch-skeleton-line session-switch-skeleton-line--short"></span></article>'
      +'<article class="session-switch-skeleton-card" aria-hidden="true"><span class="session-switch-skeleton-label"></span><span class="session-switch-skeleton-line session-switch-skeleton-line--medium"></span><span class="session-switch-skeleton-line session-switch-skeleton-line--wide"></span></article>'
      +'<article class="session-switch-skeleton-card" aria-hidden="true"><span class="session-switch-skeleton-label"></span><span class="session-switch-skeleton-line session-switch-skeleton-line--wide"></span><span class="session-switch-skeleton-line session-switch-skeleton-line--medium"></span><span class="session-switch-skeleton-line session-switch-skeleton-line--short"></span></article>';
    messages.insertBefore(skeleton,messages.firstElementChild||null);
    return skeleton;
  }

  function setContentLoading(on){
    contentLoadingDepth=Math.max(0,contentLoadingDepth+(on?1:-1));
    const visible=contentLoadingDepth>0;
    const messages=byId('messages');
    const skeleton=ensureContentSkeleton();
    if(messages){
      messages.classList.toggle('session-switch-loading',visible);
      messages.setAttribute('aria-busy',visible?'true':'false');
    }
    if(skeleton) skeleton.hidden=!visible;
  }


  async function openTarget(target,source='mobile-session-swipe'){
    if(typeof _openSidebarSession==='function') return _openSidebarSession(target,{source});
    if(typeof loadSession==='function') return loadSession(target.session_id,{source});
    throw new Error('Session navigation is unavailable');
  }

  async function switchTarget(target,source){
    if(switching||!target) return;
    switching=true;
    pendingTabSync=false;
    setContentLoading(true);
    try{
      await openTarget(target,source);
      syncTabs(true);
    }catch(error){
      if(typeof showToast==='function') showToast('Could not open that session: '+(error&&error.message||error));
    }finally{
      switching=false;
      setContentLoading(false);
      if(pendingTabSync){pendingTabSync=false;scheduleTabSync();}
    }
  }

  async function openTabDirection(direction){
    if(switching||!media(PHONE_QUERY)) return;
    const target=adjacentSession(direction);
    if(!target) return;
    await switchTarget(target,'mobile-session-tab');
  }

  function commitDistance(){
    const width=Math.max(1,pane&&pane.getBoundingClientRect().width||window.innerWidth||1);
    return Math.max(COMMIT_DISTANCE_MIN,Math.min(COMMIT_DISTANCE_MAX,width*COMMIT_DISTANCE_RATIO));
  }

  function snapBack(){
    gesture=null;
  }

  function start(event){
    if(!enabled()||switching||gesture||!currentSid()) return;
    if(event.pointerType&&event.pointerType!=='touch'&&event.pointerType!=='pen') return;
    if(event.button!==undefined&&event.button!==0) return;
    if(event.clientX<=EDGE_GUARD||event.clientX>=window.innerWidth-EDGE_GUARD) return;
    if(event.target&&event.target.closest&&event.target.closest(INTERACTIVE_SELECTOR)) return;
    const selection=typeof window.getSelection==='function'?window.getSelection():null;
    if(selection&&selection.type==='Range'&&!selection.isCollapsed) return;
    gesture={
      pointerId:event.pointerId,
      startX:event.clientX,
      startY:event.clientY,
      lastX:event.clientX,
      lastTime:event.timeStamp||performance.now(),
      velocityX:0,
      dx:0,
      axis:'pending',
      target:null,
      direction:0,
    };
  }

  function move(event){
    if(!gesture||event.pointerId!==gesture.pointerId||switching) return;
    const dx=event.clientX-gesture.startX;
    const dy=event.clientY-gesture.startY;
    const absX=Math.abs(dx);
    const absY=Math.abs(dy);
    if(gesture.axis==='pending'){
      if(Math.max(absX,absY)<LOCK_DISTANCE) return;
      if(absY>absX*1.12){gesture=null;return;}
      gesture.axis='horizontal';
      try{surface.setPointerCapture(event.pointerId);}catch(_){}
    }
    if(gesture.axis!=='horizontal') return;
    if(event.cancelable) event.preventDefault();
    const now=event.timeStamp||performance.now();
    const elapsed=Math.max(1,now-gesture.lastTime);
    const sample=(event.clientX-gesture.lastX)/elapsed;
    gesture.velocityX=gesture.velocityX*.35+sample*.65;
    gesture.lastX=event.clientX;
    gesture.lastTime=now;
    gesture.direction=dx<0?-1:1;
    gesture.target=adjacentSession(gesture.direction);
    gesture.dx=dx;
  }

  async function finish(event,cancelled){
    if(!gesture||(event.pointerId!==undefined&&event.pointerId!==gesture.pointerId)) return;
    if(gesture.axis!=='horizontal'||cancelled){snapBack();return;}
    try{surface.releasePointerCapture(gesture.pointerId);}catch(_){}
    const active=gesture;
    const distance=Math.abs(active.dx);
    const fast=Math.abs(active.velocityX)>=FLICK_VELOCITY&&distance>=FLICK_MIN_DISTANCE;
    const far=distance>=commitDistance();
    const target=active.target;
    if(!target||(!fast&&!far)){snapBack();return;}

    gesture=null;
    await switchTarget(target,'mobile-session-swipe');
  }

  function cancel(){
    if(!gesture) return;
    snapBack();
  }

  function onTabClick(event){
    const tab=event.target&&event.target.closest&&event.target.closest('.mobile-session-tab');
    if(!tab||!tabList||!tabList.contains(tab)||switching) return;
    const sid=String(tab.dataset.sid||'');
    if(!sid||sid===currentSid()){
      centerActiveTab(reducedMotion()?'auto':'smooth');
      return;
    }
    void switchTarget(sessionForSid(sid),'mobile-session-tab');
  }

  function onTabKeydown(event){
    if(!['ArrowLeft','ArrowRight','Home','End'].includes(event.key)) return;
    const tabs=[...tabList.querySelectorAll('.mobile-session-tab')];
    const current=event.target&&event.target.closest&&event.target.closest('.mobile-session-tab');
    let index=tabs.indexOf(current);
    if(index<0) return;
    event.preventDefault();
    if(event.key==='Home') index=0;
    else if(event.key==='End') index=tabs.length-1;
    else index=Math.max(0,Math.min(tabs.length-1,index+(event.key==='ArrowRight'?1:-1)));
    tabs[index].tabIndex=0;
    tabs[index].focus({preventScroll:true});
    tabs[index].scrollIntoView({behavior:reducedMotion()?'auto':'smooth',block:'nearest',inline:'center'});
  }

  function init(){
    pane=byId('mainChat');
    surface=pane&&pane.querySelector('.messages-shell');
    if(!pane||!surface) return;
    tabsViewport=byId('mobileSessionTabsViewport');
    tabList=byId('mobileSessionTabList');
    if(tabList){
      tabList.addEventListener('click',onTabClick);
      tabList.addEventListener('keydown',onTabKeydown);
    }
    syncTabs(true);
    const title=byId('appTitlebarTitle');
    const list=byId('sessionList');
    if(typeof MutationObserver==='function'&&(title||list)){
      tabsObserver=new MutationObserver(scheduleTabSync);
      if(title) tabsObserver.observe(title,{childList:true,characterData:true,subtree:true});
      if(list) tabsObserver.observe(list,{childList:true,characterData:true,attributes:true,attributeFilter:['class'],subtree:true});
    }
    surface.addEventListener('pointerdown',start,{passive:true});
    window.addEventListener('pointermove',move,{passive:false});
    window.addEventListener('pointerup',event=>{void finish(event,false);},{passive:true});
    window.addEventListener('pointercancel',event=>{void finish(event,true);},{passive:true});
    window.addEventListener('blur',cancel);
    window.addEventListener('resize',()=>{
      cancel();
      setTabMetrics();
      centerActiveTab('auto');
    },{passive:true});
  }

  window.__sessionSwipeNavigation={
    adjacentSession,
    enabled,
    cancel,
    syncTabs,
    openTabDirection,
    centerActiveTab,
    setContentLoading,
    config:{LOCK_DISTANCE,FLICK_MIN_DISTANCE,FLICK_VELOCITY,EDGE_GUARD}
  };

  if(document.readyState==='loading') document.addEventListener('DOMContentLoaded',init,{once:true});
  else init();
})();
