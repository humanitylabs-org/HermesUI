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
  let contentSurface=null;
  let preview=null;
  let swipeAnimating=false;
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

  function loadingSkeletonMarkup(){
    return '<span class="sr-only">Loading session content</span>'
      +'<div class="session-switch-skeleton-classic" aria-hidden="true">'
      +'<article class="session-switch-skeleton-chat-row session-switch-skeleton-chat-row--user"><div class="session-switch-skeleton-chat-role"><span class="session-switch-skeleton-avatar"></span><span class="session-switch-skeleton-role-line"></span></div><div class="session-switch-skeleton-chat-copy"><span class="session-switch-skeleton-line session-switch-skeleton-line--wide"></span><span class="session-switch-skeleton-line session-switch-skeleton-line--medium"></span></div></article>'
      +'<article class="session-switch-skeleton-chat-row session-switch-skeleton-chat-row--assistant"><div class="session-switch-skeleton-chat-role"><span class="session-switch-skeleton-avatar"></span><span class="session-switch-skeleton-role-line"></span></div><div class="session-switch-skeleton-chat-copy"><span class="session-switch-skeleton-line session-switch-skeleton-line--wide"></span><span class="session-switch-skeleton-line session-switch-skeleton-line--wide"></span><span class="session-switch-skeleton-line session-switch-skeleton-line--short"></span></div></article>'
      +'<article class="session-switch-skeleton-chat-row session-switch-skeleton-chat-row--user"><div class="session-switch-skeleton-chat-role"><span class="session-switch-skeleton-avatar"></span><span class="session-switch-skeleton-role-line"></span></div><div class="session-switch-skeleton-chat-copy"><span class="session-switch-skeleton-line session-switch-skeleton-line--medium"></span><span class="session-switch-skeleton-line session-switch-skeleton-line--short"></span></div></article>'
      +'<article class="session-switch-skeleton-chat-row session-switch-skeleton-chat-row--assistant"><div class="session-switch-skeleton-chat-role"><span class="session-switch-skeleton-avatar"></span><span class="session-switch-skeleton-role-line"></span></div><div class="session-switch-skeleton-chat-copy"><span class="session-switch-skeleton-line session-switch-skeleton-line--wide"></span><span class="session-switch-skeleton-line session-switch-skeleton-line--medium"></span></div></article>'
      +'</div><div class="session-switch-skeleton-high-signal" aria-hidden="true">'
      +'<article class="session-switch-skeleton-pane"><span class="session-switch-skeleton-pane-label">Goal</span><span class="session-switch-skeleton-line session-switch-skeleton-line--wide"></span><span class="session-switch-skeleton-line session-switch-skeleton-line--medium"></span></article>'
      +'<article class="session-switch-skeleton-pane"><span class="session-switch-skeleton-pane-label">Status</span><span class="session-switch-skeleton-line session-switch-skeleton-line--medium"></span><span class="session-switch-skeleton-line session-switch-skeleton-line--wide"></span></article>'
      +'<article class="session-switch-skeleton-pane"><span class="session-switch-skeleton-pane-label">Last instruction</span><span class="session-switch-skeleton-line session-switch-skeleton-line--wide"></span><span class="session-switch-skeleton-line session-switch-skeleton-line--short"></span></article>'
      +'<article class="session-switch-skeleton-pane"><span class="session-switch-skeleton-pane-label">Result</span><span class="session-switch-skeleton-line session-switch-skeleton-line--wide"></span><span class="session-switch-skeleton-line session-switch-skeleton-line--medium"></span></article>'
      +'</div>';
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
    skeleton.innerHTML=loadingSkeletonMarkup();
    messages.insertBefore(skeleton,messages.firstElementChild||null);
    return skeleton;
  }

  function ensureSwipePreview(){
    if(preview&&preview.isConnected) return preview;
    if(!surface) return null;
    const skeleton=ensureContentSkeleton();
    if(!skeleton) return null;
    preview=document.createElement('div');
    preview.className='session-swipe-preview';
    preview.setAttribute('aria-hidden','true');
    const clone=skeleton.cloneNode(true);
    clone.removeAttribute('id');
    clone.removeAttribute('role');
    clone.removeAttribute('aria-label');
    clone.hidden=false;
    clone.classList.add('session-swipe-preview-skeleton');
    preview.appendChild(clone);
    surface.appendChild(preview);
    return preview;
  }

  function swipeWidth(){
    return Math.max(1,contentSurface&&contentSurface.getBoundingClientRect().width||surface&&surface.getBoundingClientRect().width||window.innerWidth||1);
  }

  function resetSwipeVisual(){
    swipeAnimating=false;
    if(surface) surface.classList.remove('session-swipe-active');
    if(contentSurface){
      contentSurface.classList.remove('session-swipe-moving','session-swipe-settling');
      contentSurface.style.transform='';
    }
    if(preview){
      preview.classList.remove('is-visible','session-swipe-moving','session-swipe-settling');
      preview.style.transform='translate3d(100%,0,0)';
    }
  }

  function applySwipeVisual(dx,target,direction){
    if(!contentSurface||!target||!direction){resetSwipeVisual();return;}
    const swipePreview=ensureSwipePreview();
    if(!swipePreview) return;
    const width=swipeWidth();
    dx=Math.max(-width,Math.min(width,dx));
    const base=direction<0?width:-width;
    surface.classList.add('session-swipe-active');
    contentSurface.classList.remove('session-swipe-settling');
    contentSurface.classList.add('session-swipe-moving');
    preview.classList.remove('session-swipe-settling');
    preview.classList.add('is-visible','session-swipe-moving');
    contentSurface.style.transform=`translate3d(${dx}px,0,0)`;
    preview.style.transform=`translate3d(${base+dx}px,0,0)`;
  }

  function animateSwipeTo(contentX,previewX){
    if(!contentSurface||!preview) return Promise.resolve();
    swipeAnimating=true;
    contentSurface.classList.remove('session-swipe-moving');
    preview.classList.remove('session-swipe-moving');
    contentSurface.classList.add('session-swipe-settling');
    preview.classList.add('session-swipe-settling','is-visible');
    const place=()=>{
      contentSurface.style.transform=`translate3d(${contentX}px,0,0)`;
      preview.style.transform=`translate3d(${previewX}px,0,0)`;
    };
    if(reducedMotion()){place();return Promise.resolve();}
    return new Promise(resolve=>{
      let settled=false;
      const done=()=>{if(settled)return;settled=true;resolve();};
      contentSurface.addEventListener('transitionend',done,{once:true});
      requestAnimationFrame(place);
      setTimeout(done,240);
    });
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
    const active=gesture;
    gesture=null;
    if(!active||active.axis!=='horizontal'||!active.target){resetSwipeVisual();return;}
    const width=swipeWidth();
    void animateSwipeTo(0,active.direction<0?width:-width).then(resetSwipeVisual);
  }

  function start(event){
    if(!enabled()||switching||swipeAnimating||gesture||!currentSid()) return;
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
    applySwipeVisual(dx,gesture.target,gesture.direction);
  }

  async function finish(event,cancelled){
    if(!gesture||(event.pointerId!==undefined&&event.pointerId!==gesture.pointerId)) return;
    try{surface.releasePointerCapture(gesture.pointerId);}catch(_){}
    if(gesture.axis!=='horizontal'||cancelled){snapBack();return;}
    const active=gesture;
    const distance=Math.abs(active.dx);
    const fast=Math.abs(active.velocityX)>=FLICK_VELOCITY&&distance>=FLICK_MIN_DISTANCE;
    const far=distance>=commitDistance();
    const target=active.target;
    if(!target||(!fast&&!far)){snapBack();return;}

    gesture=null;
    const width=swipeWidth();
    await animateSwipeTo(active.direction<0?-width:width,0);
    // Hand the fully-arrived preview to the real loading surface before its
    // duplicate is removed, so even a slow request has no blank frame.
    setContentLoading(true);
    resetSwipeVisual();
    try{
      await switchTarget(target,'mobile-session-swipe');
    }finally{
      setContentLoading(false);
    }
  }

  function cancel(){
    if(!gesture) return;
    snapBack();
  }

  function onTabClick(event){
    const tab=event.target&&event.target.closest&&event.target.closest('.mobile-session-tab');
    if(!tab||!tabList||!tabList.contains(tab)||switching||swipeAnimating) return;
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
    contentSurface=byId('messages');
    if(!pane||!surface||!contentSurface) return;
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
      resetSwipeVisual();
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
