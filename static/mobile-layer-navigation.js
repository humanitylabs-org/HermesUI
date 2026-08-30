(function(){
  'use strict';

  const root=document.documentElement;
  const backSwipeZone=document.getElementById('mobileLayerBackSwipeZone');
  const appSwipeZone=document.getElementById('mobileAppLayerSwipeZone');
  const announcer=document.getElementById('mobileLayerAnnouncer');
  const BACK_EDGE_WIDTH_PX=24;
  const AXIS_LOCK_PX=10;
  const INTERACTIVE_COMMIT_RATIO=.34;
  const INTERACTIVE_FLICK_MIN_PX=28;
  const INTERACTIVE_FLICK_VELOCITY_PX_MS=.35;
  const INTERACTIVE_REVERSE_VELOCITY_PX_MS=.35;
  const DOMINANCE_RATIO=1.6;
  const CLICK_SUPPRESSION_MS=250;
  const BLOCKED_ORIGIN_SELECTOR=[
    '.composer-box','textarea','input','select','[contenteditable="true"]',
    '.messages pre','.msg-body pre','code','table','.project-bar','.session-source-tabs',
    '.mobile-primary-menu','.mobile-session-utilities-menu','.rail','.mobile-rail-handle',
    '.rightpanel','.tailnet-notifications','.settings-popup:not([hidden])','dialog[open]','[role="dialog"]'
  ].join(',');

  let gesture=null;
  let settleTimer=0;
  let suppressClickUntil=0;
  let pendingTouchPointerId=null;

  function isPhoneWidth(){
    try{return window.matchMedia('(max-width:640px)').matches;}catch(_){return window.innerWidth<=640;}
  }

  function currentLayer(){
    if(root.dataset.tailnetView==='external')return 'app';
    if(root.dataset.mobileSessionView==='sessions')return 'sessions';
    return 'conversation';
  }

  function verticalGestureBounds(){
    const titlebar=document.querySelector('.app-titlebar');
    const titleRect=titlebar&&getComputedStyle(titlebar).display!=='none'?titlebar.getBoundingClientRect():null;
    const menu=document.getElementById('mobilePrimaryMenu');
    const menuRect=menu&&getComputedStyle(menu).display!=='none'?menu.getBoundingClientRect():null;
    return {
      top:Math.max(8,(titleRect?titleRect.bottom:0)+8),
      bottom:Math.min(window.innerHeight-8,(menuRect?menuRect.top:window.innerHeight)-8)
    };
  }

  function originBlocked(target){
    if(!target||typeof target.closest!=='function')return false;
    if(target===backSwipeZone||target===appSwipeZone)return false;
    return Boolean(target.closest(BLOCKED_ORIGIN_SELECTOR));
  }

  function modalBlocksNavigation(){
    if(document.querySelector('.app-dialog-overlay[aria-hidden="false"],dialog[open]'))return true;
    return Array.from(document.querySelectorAll('[role="dialog"]')).some(node=>{
      const style=getComputedStyle(node);
      return !node.hidden&&node.getClientRects().length>0&&style.display!=='none'&&style.visibility!=='hidden';
    });
  }

  function hasConversation(){
    if(typeof window._mobileSessionSelectionRequired==='function')return !window._mobileSessionSelectionRequired();
    return Boolean(window.S&&window.S.session&&window.S.session.session_id);
  }

  function conversationIsLoading(){
    const messages=document.getElementById('messages');
    return Boolean(messages&&messages.classList.contains('session-switch-loading'));
  }

  function candidateForTouch(touch,target){
    if(!isPhoneWidth()||root.hasAttribute('data-mobile-layer-busy')||modalBlocksNavigation()||originBlocked(target))return null;
    const bounds=verticalGestureBounds();
    if(touch.clientY<bounds.top||touch.clientY>bounds.bottom)return null;
    const inBackBand=touch.clientX>=0&&touch.clientX<=BACK_EDGE_WIDTH_PX;
    if(!inBackBand)return null;
    const layer=currentLayer();
    const tailnet=window.hermesMobileTailnetNavigation;
    if(layer==='conversation'&&target===backSwipeZone){
      if(conversationIsLoading())return null;
      if(!tailnet||typeof tailnet.openSessionsFromConversation!=='function')return null;
      return {layer,destination:'sessions',direction:'back',sign:1,interactive:true,dragMode:'conversation-to-sessions'};
    }
    if(layer==='app'){
      if(target!==appSwipeZone)return null;
      if(!tailnet||typeof tailnet.canLeaveActiveApp!=='function'||!tailnet.canLeaveActiveApp())return null;
      return {
        layer,
        destination:hasConversation()?'conversation':'sessions',
        direction:'back',
        sign:1,
        interactive:true,
        dragMode:hasConversation()?'app-to-conversation':'app-to-sessions'
      };
    }
    return null;
  }

  function resetGesture(){gesture=null;pendingTouchPointerId=null;}

  function markDragPreview(){
    if(!gesture||!/-to-sessions$/.test(gesture.dragMode))return;
    const sidebar=document.querySelector('.sidebar');
    if(!sidebar||sidebar.classList.contains('mobile-session-page'))return;
    sidebar.dataset.mobileLayerPreview='sessions';
    sidebar.classList.add('mobile-session-page');
  }

  function clearDragPreview(){
    const sidebar=document.querySelector('.sidebar');
    if(!sidebar||sidebar.dataset.mobileLayerPreview!=='sessions')return;
    delete sidebar.dataset.mobileLayerPreview;
    if(root.dataset.mobileSessionView!=='sessions')sidebar.classList.remove('mobile-session-page');
  }

  function clearInteractiveDrag(){
    clearDragPreview();
    if(settleTimer){window.clearTimeout(settleTimer);settleTimer=0;}
    root.removeAttribute('data-mobile-layer-drag');
    root.removeAttribute('data-mobile-layer-drag-phase');
    root.removeAttribute('data-mobile-layer-busy');
    root.style.removeProperty('--mobile-layer-drag-offset');
    root.style.removeProperty('--mobile-layer-drag-duration');
  }

  function interactiveWidth(){
    if(!gesture)return Math.max(1,window.innerWidth||document.documentElement.clientWidth||1);
    const surface=gesture.dragMode==='conversation-to-sessions'
      ?document.querySelector('.main')
      :document.getElementById('tailnetAppWorkspace');
    const rect=surface&&surface.getBoundingClientRect();
    return Math.max(1,rect&&rect.width||window.innerWidth||document.documentElement.clientWidth||1);
  }

  function beginInteractiveDrag(){
    if(!gesture||!gesture.interactive)return;
    const active=document.activeElement;
    if(active&&typeof active.matches==='function'&&active.matches('textarea,input,select,[contenteditable="true"]')){
      try{active.blur();}catch(_){}
    }
    root.dataset.mobileLayerDrag=gesture.dragMode;
    root.dataset.mobileLayerDragPhase='dragging';
    gesture.width=interactiveWidth();
    gesture.progress=0;
    root.style.setProperty('--mobile-layer-drag-duration','0ms');
    root.style.setProperty('--mobile-layer-drag-offset','0px');
    markDragPreview();
    const surface=gesture.dragMode==='conversation-to-sessions'
      ?document.querySelector('.main')
      :document.getElementById('tailnetAppWorkspace');
    if(surface)surface.getBoundingClientRect();
  }

  function updateInteractiveDrag(dx){
    if(!gesture||!gesture.interactive)return;
    const width=gesture.width||interactiveWidth();
    const offset=Math.max(0,Math.min(width,dx));
    const progress=Math.max(0,Math.min(1,offset/width));
    gesture.progress=progress;
    root.style.setProperty('--mobile-layer-drag-offset',`${offset}px`);
  }

  function recordSample(touch,now){
    gesture.samples.push({x:touch.clientX,t:now});
    gesture.samples=gesture.samples.filter(sample=>now-sample.t<=120);
  }

  function closeOpenUtilities(target){
    const toggle=document.getElementById('mobileSessionUtilitiesToggle');
    if(!toggle||toggle.getAttribute('aria-expanded')!=='true')return false;
    const menu=document.getElementById('mobileSessionUtilitiesMenu');
    if(target instanceof Node&&((menu&&menu.contains(target))||toggle.contains(target)))return false;
    const tailnet=window.hermesMobileTailnetNavigation;
    return Boolean(tailnet&&typeof tailnet.closeUtilities==='function'&&tailnet.closeUtilities());
  }

  function onTouchStart(event){
    if(gesture){
      if(event.touches.length!==1)onTouchCancel(null);
      return;
    }
    if(root.hasAttribute('data-mobile-layer-busy'))return;
    if(event.touches.length!==1)return resetGesture();
    if(closeOpenUtilities(event.target))return resetGesture();
    const touch=event.touches[0];
    const pointerId=pendingTouchPointerId;
    pendingTouchPointerId=null;
    const candidate=candidateForTouch(touch,event.target);
    if(!candidate)return resetGesture();
    gesture={
      ...candidate,
      origin:event.target,
      startX:touch.clientX,
      startY:touch.clientY,
      lastX:touch.clientX,
      lastY:touch.clientY,
      pointerId,
      locked:false,
      active:false,
      cancelled:false,
      releasing:false,
      samples:[{x:touch.clientX,t:performance.now()}]
    };
  }

  function onTouchMove(event){
    if(!gesture||gesture.cancelled||event.touches.length!==1)return;
    const touch=event.touches[0];
    const now=performance.now();
    gesture.lastX=touch.clientX;
    gesture.lastY=touch.clientY;
    const dx=touch.clientX-gesture.startX;
    const dy=touch.clientY-gesture.startY;
    const absX=Math.abs(dx);
    const absY=Math.abs(dy);

    if(dx<0&&absX>=AXIS_LOCK_PX){gesture.cancelled=true;return;}
    if(!gesture.locked&&Math.hypot(dx,dy)>=AXIS_LOCK_PX){
      if(absY>=absX){gesture.cancelled=true;return;}
      gesture.locked=true;
    }
    if(!gesture.locked)return;
    recordSample(touch,now);
    if(!gesture.active&&absX>=AXIS_LOCK_PX&&absX>=DOMINANCE_RATIO*absY){
      gesture.active=true;
      beginInteractiveDrag();
    }
    if(gesture.active){
      event.preventDefault();
      event.stopImmediatePropagation();
      updateInteractiveDrag(dx);
    }
  }

  function trailingVelocity(now=performance.now()){
    if(!gesture||gesture.samples.length<2)return 0;
    const first=gesture.samples[0];
    const last=gesture.samples[gesture.samples.length-1];
    if(now-last.t>120)return 0;
    return (last.x-first.x)/Math.max(1,last.t-first.t);
  }

  function announceLayer(layer){
    if(!announcer)return;
    let message='';
    if(layer==='sessions')message='Sessions';
    else if(layer==='conversation'){
      const title=document.getElementById('appTitlebarTitle');
      message=`Conversation${title&&title.textContent?` — ${title.textContent.trim()}`:''}`;
    }else{
      const workspace=document.getElementById('tailnetAppWorkspace');
      message=workspace&&workspace.getAttribute('aria-label')||'Tailnet app';
    }
    announcer.textContent='';
    requestAnimationFrame(()=>{announcer.textContent=message;});
  }

  function focusLayer(layer){
    let target=null;
    if(layer==='sessions')target=document.querySelector('#panelChat>.panel-head');
    else if(layer==='conversation')target=document.getElementById('appTitlebarTitle');
    else target=document.getElementById('tailnetAppWorkspace');
    if(!target)return;
    if(!target.hasAttribute('tabindex'))target.setAttribute('tabindex','-1');
    try{target.focus({preventScroll:true});}catch(_){try{target.focus();}catch(__){}}
  }

  function finishTransition(layer){
    root.dataset.mobileLayer=layer;
    announceLayer(layer);
    focusLayer(layer);
    document.dispatchEvent(new CustomEvent('hermesui:mobile-layer-change',{detail:{layer}}));
    return true;
  }

  function canCommitBack(finished){
    if(!finished||currentLayer()!==finished.layer)return false;
    const tailnet=window.hermesMobileTailnetNavigation;
    if(!tailnet)return false;
    if(finished.dragMode==='conversation-to-sessions')return typeof tailnet.openSessionsFromConversation==='function';
    if(typeof tailnet.canLeaveActiveApp!=='function'||!tailnet.canLeaveActiveApp())return false;
    if(finished.destination==='conversation')return hasConversation()&&typeof tailnet.openConversation==='function';
    return typeof tailnet.openSessions==='function';
  }

  function navigate(direction,{destination=''}={}){
    if(!isPhoneWidth()||direction!=='back')return false;
    const tailnet=window.hermesMobileTailnetNavigation;
    const layer=currentLayer();
    if(layer==='conversation'&&direction==='back'){
      if(!tailnet||typeof tailnet.openSessionsFromConversation!=='function'||!tailnet.openSessionsFromConversation())return false;
      return finishTransition('sessions');
    }
    if(layer==='app'&&direction==='back'){
      const target=destination||(hasConversation()?'conversation':'sessions');
      if(target==='conversation'){
        if(!hasConversation()||!tailnet||typeof tailnet.openConversation!=='function'||!tailnet.openConversation())return false;
        return finishTransition('conversation');
      }
      if(!tailnet||typeof tailnet.openSessions!=='function'||!tailnet.openSessions())return false;
      return finishTransition('sessions');
    }
    return false;
  }

  function settleInteractive(finished,commits,event){
    if(event){event.preventDefault();event.stopImmediatePropagation();}
    if(commits&&!canCommitBack(finished))commits=false;
    const current=Number.isFinite(finished.progress)?finished.progress:0;
    const target=commits?1:0;
    const remaining=Math.min(1,Math.abs(target-current));
    let reduced=false;
    try{reduced=window.matchMedia('(prefers-reduced-motion:reduce)').matches;}catch(_){}
    let duration=0;
    if(!reduced){
      duration=Math.round(Math.max(140,Math.min(260,140+120*remaining)));
      if(!commits)duration=Math.min(180,duration);
    }
    root.dataset.mobileLayerBusy='true';
    root.dataset.mobileLayerDragPhase='settling';
    root.style.setProperty('--mobile-layer-drag-duration',`${duration}ms`);
    if(commits)suppressClickUntil=Date.now()+250;
    const transitionSurface=finished.dragMode==='conversation-to-sessions'
      ?document.querySelector('.main')
      :document.getElementById('tailnetAppWorkspace');
    if(transitionSurface)transitionSurface.getBoundingClientRect();
    requestAnimationFrame(()=>{
      root.style.setProperty('--mobile-layer-drag-offset',`${target*finished.width}px`);
    });

    let finalized=false;
    const finalize=()=>{
      if(finalized)return;
      finalized=true;
      if(settleTimer){window.clearTimeout(settleTimer);settleTimer=0;}
      if(transitionSurface)transitionSurface.removeEventListener('transitionend',onTransitionEnd);
      if(commits)navigate(finished.direction,{destination:finished.destination});
      clearInteractiveDrag();
      resetGesture();
    };
    const onTransitionEnd=transitionEvent=>{
      if(transitionEvent.target===transitionSurface&&transitionEvent.propertyName==='transform')finalize();
    };
    if(transitionSurface)transitionSurface.addEventListener('transitionend',onTransitionEnd);
    if(duration===0)requestAnimationFrame(finalize);
    else settleTimer=window.setTimeout(finalize,duration+80);
  }

  function finishGestureAt(clientX,clientY,event){
    if(!gesture||gesture.releasing)return;
    gesture.releasing=true;
    const finished=gesture;
    const endX=Number.isFinite(clientX)?clientX:finished.lastX;
    const endY=Number.isFinite(clientY)?clientY:finished.lastY;
    const dx=endX-finished.startX;
    const dy=endY-finished.startY;
    const velocity=trailingVelocity();
    if(finished.interactive&&finished.active){
      const width=finished.width||interactiveWidth();
      const distance=Math.max(0,dx);
      const reverseFling=velocity<=-INTERACTIVE_REVERSE_VELOCITY_PX_MS;
      const commits=!finished.cancelled&&!reverseFling&&(
        distance>=width*INTERACTIVE_COMMIT_RATIO||
        (distance>=INTERACTIVE_FLICK_MIN_PX&&velocity>=INTERACTIVE_FLICK_VELOCITY_PX_MS)
      );
      settleInteractive(finished,commits,event);
      return;
    }
    resetGesture();
  }

  function onTouchEnd(event){
    if(!gesture)return;
    finishGestureAt(gesture.lastX,gesture.lastY,event);
  }

  function onPointerRelease(event){
    if(!gesture||gesture.releasing||event.pointerType!=='touch')return;
    if(gesture.pointerId!==null&&gesture.pointerId!==undefined&&gesture.pointerId!==event.pointerId)return;
    finishGestureAt(gesture.lastX,gesture.lastY,event);
  }

  function onPointerCancel(event){
    if(!gesture||gesture.releasing||event.pointerType!=='touch')return;
    if(gesture.pointerId!==null&&gesture.pointerId!==undefined&&gesture.pointerId!==event.pointerId)return;
    onTouchCancel(event);
  }

  function onTouchCancel(event){
    if(event&&event.mobileLayerSynthetic)return;
    if(!gesture||gesture.releasing)return;
    gesture.releasing=true;
    if(gesture.interactive&&gesture.active){settleInteractive(gesture,false,null);return;}
    clearInteractiveDrag();
    resetGesture();
  }

  function syncLayer(){
    if(!isPhoneWidth()){
      root.removeAttribute('data-mobile-layer');
      clearInteractiveDrag();
      resetGesture();
      return;
    }
    root.dataset.mobileLayer=currentLayer();
  }

  document.addEventListener('pointerdown',event=>{
    if(event.pointerType==='touch'&&!gesture)pendingTouchPointerId=event.pointerId;
  },{capture:true,passive:true});
  window.addEventListener('pointerup',onPointerRelease,{capture:true,passive:false});
  window.addEventListener('pointercancel',onPointerCancel,{capture:true,passive:true});
  document.addEventListener('touchstart',onTouchStart,{capture:true,passive:true});
  document.addEventListener('touchmove',onTouchMove,{capture:true,passive:false});
  document.addEventListener('touchend',onTouchEnd,{capture:true,passive:false});
  document.addEventListener('touchcancel',onTouchCancel,{capture:true,passive:true});
  document.addEventListener('click',event=>{
    if(!isPhoneWidth()||Date.now()>=suppressClickUntil)return;
    event.preventDefault();
    event.stopImmediatePropagation();
    suppressClickUntil=0;
  },{capture:true});
  document.addEventListener('contextmenu',event=>{
    if(!isPhoneWidth()||(!gesture&&Date.now()>=suppressClickUntil))return;
    event.preventDefault();
    event.stopImmediatePropagation();
  },{capture:true});
  window.addEventListener('resize',()=>{clearInteractiveDrag();resetGesture();syncLayer();},{passive:true});
  window.addEventListener('pagehide',()=>{clearInteractiveDrag();resetGesture();},{passive:true});
  document.addEventListener('visibilitychange',()=>{if(document.hidden){clearInteractiveDrag();resetGesture();}},{passive:true});
  document.addEventListener('hermesui:tailnet-app-selected',()=>{clearInteractiveDrag();resetGesture();syncLayer();});
  const observer=new MutationObserver(()=>{
    if(gesture&&!root.hasAttribute('data-mobile-layer-busy')){clearInteractiveDrag();resetGesture();}
    syncLayer();
  });
  observer.observe(root,{attributes:true,attributeFilter:['data-tailnet-view','data-mobile-session-view']});
  if(document.getElementById('appTitlebarTitle'))document.getElementById('appTitlebarTitle').setAttribute('tabindex','-1');
  if(document.getElementById('tailnetAppWorkspace'))document.getElementById('tailnetAppWorkspace').setAttribute('tabindex','-1');
  window.__mobileLayerNavigation={
    currentLayer,
    navigate,
    thresholds:{backEdgeWidth:BACK_EDGE_WIDTH_PX,interactiveActivate:AXIS_LOCK_PX,interactiveCommitRatio:INTERACTIVE_COMMIT_RATIO,dominance:DOMINANCE_RATIO}
  };
  syncLayer();
})();
