(function(){
  'use strict';

  const root=document.documentElement;
  const backSwipeZone=document.getElementById('mobileLayerBackSwipeZone');
  const appSwipeZone=document.getElementById('mobileAppLayerSwipeZone');
  const announcer=document.getElementById('mobileLayerAnnouncer');
  const BACK_EDGE_WIDTH_PX=40;
  const EDGE_INSET_PX=16;
  const EDGE_WIDTH_PX=24;
  const AXIS_LOCK_PX=10;
  const ACTIVATE_PX=24;
  const COMMIT_PX=72;
  const FLICK_DISTANCE_PX=40;
  const FLICK_VELOCITY_PX_MS=.5;
  const INTERACTIVE_COMMIT_RATIO=.34;
  const INTERACTIVE_FLICK_DISTANCE_PX=28;
  const INTERACTIVE_FLICK_VELOCITY_PX_MS=.35;
  const INTERACTIVE_REVERSE_VELOCITY_PX_MS=.35;
  const DOMINANCE_RATIO=1.6;
  const COOLDOWN_MS=250;
  const INTERACTIVE_COOLDOWN_MS=80;
  const BLOCKED_ORIGIN_SELECTOR=[
    '.composer-box','textarea','input','select','[contenteditable="true"]',
    '.messages pre','.msg-body pre','code','table','.project-bar','.session-source-tabs',
    '.mobile-primary-menu','.mobile-session-utilities-menu','.rail','.mobile-rail-handle',
    '.rightpanel','.tailnet-notifications','.settings-popup:not([hidden])','dialog[open]','[role="dialog"]'
  ].join(',');

  let gesture=null;
  let cooldownUntil=0;
  let utilitiesOpenAtPointerDown=false;
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

  function contentRightEdge(){
    if(root.dataset.mobileRail==='collapsed')return window.innerWidth;
    const rail=document.querySelector('.tailnet-app-rail');
    if(!rail)return window.innerWidth;
    const rect=rail.getBoundingClientRect();
    return rect.width>0&&rect.left>0?rect.left:window.innerWidth;
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

  function candidateForTouch(touch,target){
    if(!isPhoneWidth()||Date.now()<cooldownUntil||modalBlocksNavigation()||originBlocked(target))return null;
    const bounds=verticalGestureBounds();
    if(touch.clientY<bounds.top||touch.clientY>bounds.bottom)return null;
    const layer=currentLayer();
    const tailnet=window.hermesMobileTailnetNavigation;
    if(layer==='app'){
      if(target!==appSwipeZone)return null;
      const inBackBand=touch.clientX>=0&&touch.clientX<=BACK_EDGE_WIDTH_PX;
      if(!inBackBand||!hasConversation()||!tailnet||typeof tailnet.canLeaveActiveApp!=='function'||!tailnet.canLeaveActiveApp())return null;
      return {layer,direction:'back',sign:1,interactive:true,dragMode:'app-to-conversation'};
    }
    const rightEdge=contentRightEdge();
    const inBackBand=touch.clientX>=0&&touch.clientX<=BACK_EDGE_WIDTH_PX;
    const forwardBandEnd=rightEdge-EDGE_INSET_PX;
    const inForwardBand=touch.clientX>=forwardBandEnd-EDGE_WIDTH_PX&&touch.clientX<=forwardBandEnd;
    if(layer==='conversation'&&target===backSwipeZone&&inBackBand)return {layer,direction:'back',sign:1,interactive:true,dragMode:'conversation-to-sessions'};
    if(layer==='sessions'&&inForwardBand&&hasConversation())return {layer,direction:'forward',sign:-1,interactive:true,dragMode:'sessions-to-conversation'};
    if(
      layer==='conversation'&&inForwardBand&&
      tailnet&&typeof tailnet.canPreviewLastApp==='function'&&tailnet.canPreviewLastApp()
    )return {layer,direction:'forward',sign:-1,interactive:true,dragMode:'conversation-to-app'};
    return null;
  }

  function resetGesture(){gesture=null;pendingTouchPointerId=null;}

  function clearInteractiveDrag(){
    if(settleTimer){window.clearTimeout(settleTimer);settleTimer=0;}
    root.removeAttribute('data-mobile-layer-drag');
    root.removeAttribute('data-mobile-layer-drag-phase');
    root.style.removeProperty('--mobile-layer-drag-progress');
    root.style.removeProperty('--mobile-layer-drag-duration');
  }

  function interactiveWidth(){
    const layout=document.querySelector('.layout');
    const width=layout&&layout.getBoundingClientRect().width;
    return Math.max(1,width||contentRightEdge()||window.innerWidth);
  }

  function beginInteractiveDrag(){
    if(!gesture||!gesture.interactive||gesture.consumeUtilities)return;
    gesture.width=interactiveWidth();
    gesture.originProgress=gesture.layer==='sessions'||gesture.layer==='app'?1:0;
    gesture.progressSign=gesture.dragMode.includes('app')?-1:1;
    gesture.progress=gesture.originProgress;
    const active=document.activeElement;
    if(active&&typeof active.matches==='function'&&active.matches('textarea,input,select,[contenteditable="true"]')){
      try{active.blur();}catch(_){}
    }
    if(window.__sessionSwipeNavigation&&typeof window.__sessionSwipeNavigation.cancel==='function'){
      try{window.__sessionSwipeNavigation.cancel();}catch(_){}
    }
    if(typeof window.switchPanel==='function'){
      try{void window.switchPanel('chat');}catch(_){}
    }
    root.dataset.mobileLayerDrag=gesture.dragMode;
    root.dataset.mobileLayerDragPhase='dragging';
    root.style.setProperty('--mobile-layer-drag-duration','0ms');
    root.style.setProperty('--mobile-layer-drag-progress',`${gesture.progress*100}%`);
  }

  function updateInteractiveDrag(dx){
    if(!gesture||!gesture.interactive||gesture.consumeUtilities)return;
    const width=gesture.width||interactiveWidth();
    const progress=Math.max(0,Math.min(1,gesture.originProgress+gesture.progressSign*dx/width));
    gesture.progress=progress;
    root.style.setProperty('--mobile-layer-drag-progress',`${progress*100}%`);
  }

  function cancelOriginRow(){
    if(!gesture||!gesture.origin||typeof gesture.origin.closest!=='function')return;
    const row=gesture.origin.closest('.session-item,.session-child-session');
    if(!row)return;
    const cancelEvent=new Event('touchcancel',{bubbles:false,cancelable:false});
    cancelEvent.mobileLayerSynthetic=true;
    row.dispatchEvent(cancelEvent);
  }

  function recordSample(touch,now){
    gesture.samples.push({x:touch.clientX,t:now});
    gesture.samples=gesture.samples.filter(sample=>now-sample.t<=120);
  }

  function onTouchStart(event){
    if(gesture){
      if(event.touches.length!==1)onTouchCancel(null);
      return;
    }
    if(root.dataset.mobileLayerDragPhase==='settling')return;
    if(event.touches.length!==1)return resetGesture();
    const touch=event.touches[0];
    const pointerId=pendingTouchPointerId;
    pendingTouchPointerId=null;
    const candidate=candidateForTouch(touch,event.target);
    const consumeUtilities=utilitiesOpenAtPointerDown;
    utilitiesOpenAtPointerDown=false;
    if(!candidate)return resetGesture();
    gesture={
      ...candidate,
      consumeUtilities,
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
      peak:0,
      samples:[{x:touch.clientX,t:performance.now()}]
    };

    if(candidate.interactive){
      const origin=gesture.origin;
      window.setTimeout(()=>{if(gesture&&gesture.origin===origin&&!gesture.active)cancelOriginRow();},0);
    }
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

    if(dx*gesture.sign<0&&absX>=AXIS_LOCK_PX){gesture.cancelled=true;return;}
    if(!gesture.locked&&Math.hypot(dx,dy)>=AXIS_LOCK_PX){
      if(absY>=12&&absY>=absX){gesture.cancelled=true;return;}
      if(absX<=absY){gesture.cancelled=true;return;}
      gesture.locked=true;
    }
    if(!gesture.locked)return;
    recordSample(touch,now);
    gesture.peak=Math.max(gesture.peak,absX);
    if(!gesture.interactive&&gesture.peak>0&&absX<gesture.peak*.5){gesture.cancelled=true;return;}
    const activateDistance=gesture.interactive?AXIS_LOCK_PX:ACTIVATE_PX;
    if(!gesture.active&&absX>=activateDistance&&absX>=DOMINANCE_RATIO*absY){
      gesture.active=true;
      cancelOriginRow();
      beginInteractiveDrag();
    }
    if(gesture.active){
      event.preventDefault();
      event.stopImmediatePropagation();
      if(gesture.interactive)updateInteractiveDrag(dx);
    }
  }

  function trailingVelocity(now=performance.now()){
    if(!gesture||gesture.samples.length<2)return 0;
    const first=gesture.samples[0];
    const last=gesture.samples[gesture.samples.length-1];
    if(now-last.t>120)return 0;
    const elapsed=Math.max(1,last.t-first.t);
    return (last.x-first.x)/elapsed;
  }

  function hasConversation(){
    if(typeof window._mobileSessionSelectionRequired==='function')return !window._mobileSessionSelectionRequired();
    return Boolean(window.S&&window.S.session&&window.S.session.session_id);
  }

  function motionDelay(){
    try{return window.matchMedia('(prefers-reduced-motion:reduce)').matches?0:230;}catch(_){return 230;}
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

  function focusLayer(layer,delay=motionDelay()){
    window.setTimeout(()=>{
      let target=null;
      if(layer==='sessions')target=document.querySelector('#panelChat>.panel-head');
      else if(layer==='conversation')target=document.getElementById('appTitlebarTitle');
      else target=document.getElementById('tailnetAppWorkspace');
      if(!target)return;
      if(!target.hasAttribute('tabindex'))target.setAttribute('tabindex','-1');
      try{target.focus({preventScroll:true});}catch(_){try{target.focus();}catch(__){}}
    },delay);
  }

  function finishTransition(layer,{focusDelay=motionDelay(),cooldown=COOLDOWN_MS}={}){
    cooldownUntil=Date.now()+cooldown;
    root.dataset.mobileLayer=layer;
    announceLayer(layer);
    focusLayer(layer,focusDelay);
    document.dispatchEvent(new CustomEvent('hermesui:mobile-layer-change',{detail:{layer}}));
    return true;
  }

  function navigate(direction,{fromGesture=false}={}){
    if(!isPhoneWidth())return false;
    const tailnet=window.hermesMobileTailnetNavigation;
    if(tailnet&&typeof tailnet.closeUtilities==='function'&&tailnet.closeUtilities())return false;
    const layer=currentLayer();
    if(layer==='conversation'&&direction==='back'){
      if(!tailnet||typeof tailnet.openSessionsFromConversation!=='function'||!tailnet.openSessionsFromConversation())return false;
      return finishTransition('sessions',{focusDelay:fromGesture?0:motionDelay(),cooldown:fromGesture?INTERACTIVE_COOLDOWN_MS:COOLDOWN_MS});
    }
    if(layer==='sessions'&&direction==='forward'){
      if(!hasConversation()||typeof window.closeMobileSidebar!=='function')return false;
      window.closeMobileSidebar(true);
      if(currentLayer()==='sessions')return false;
      return finishTransition('conversation',{focusDelay:fromGesture?0:motionDelay(),cooldown:fromGesture?INTERACTIVE_COOLDOWN_MS:COOLDOWN_MS});
    }
    if(layer==='conversation'&&direction==='forward'){
      if(!tailnet||typeof tailnet.restoreLastApp!=='function'||!tailnet.restoreLastApp())return false;
      return finishTransition('app',{focusDelay:fromGesture?0:motionDelay(),cooldown:fromGesture?INTERACTIVE_COOLDOWN_MS:COOLDOWN_MS});
    }
    if(layer==='app'&&direction==='back'){
      if(!hasConversation()||!tailnet||typeof tailnet.openConversation!=='function'||!tailnet.openConversation())return false;
      return finishTransition('conversation',{focusDelay:fromGesture?0:motionDelay(),cooldown:fromGesture?INTERACTIVE_COOLDOWN_MS:COOLDOWN_MS});
    }
    return false;
  }

  function settleInteractive(finished,commits,event){
    if(event){event.preventDefault();event.stopImmediatePropagation();}
    if(finished.consumeUtilities){clearInteractiveDrag();resetGesture();return;}
    const current=Number.isFinite(finished.progress)?finished.progress:finished.originProgress;
    const target=commits?(finished.originProgress===0?1:0):finished.originProgress;
    const remaining=Math.min(1,Math.abs(target-current));
    let reduced=false;
    try{reduced=window.matchMedia('(prefers-reduced-motion:reduce)').matches;}catch(_){}
    const duration=reduced?0:Math.round(Math.max(110,Math.min(240,110+130*remaining)));
    root.dataset.mobileLayerDragPhase='settling';
    root.style.setProperty('--mobile-layer-drag-duration',`${duration}ms`);
    suppressClickUntil=Date.now()+350;
    const transitionSurface=finished.dragMode.includes('app')
      ?document.getElementById('tailnetAppWorkspace')
      :document.querySelector('.sidebar');
    if(transitionSurface)transitionSurface.getBoundingClientRect();
    requestAnimationFrame(()=>root.style.setProperty('--mobile-layer-drag-progress',`${target*100}%`));

    let finalized=false;
    const finalize=()=>{
      if(finalized)return;
      finalized=true;
      if(settleTimer){window.clearTimeout(settleTimer);settleTimer=0;}
      if(transitionSurface)transitionSurface.removeEventListener('transitionend',onTransitionEnd);
      if(commits)navigate(finished.direction,{fromGesture:true});
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
      const distance=Math.max(0,dx*finished.sign);
      const reverseFling=velocity*finished.sign<=-INTERACTIVE_REVERSE_VELOCITY_PX_MS;
      const commits=!finished.cancelled&&!reverseFling&&(
        distance>=width*INTERACTIVE_COMMIT_RATIO||
        (distance>=INTERACTIVE_FLICK_DISTANCE_PX&&velocity*finished.sign>=INTERACTIVE_FLICK_VELOCITY_PX_MS)
      );
      settleInteractive(finished,commits,event);
      return;
    }
    const commits=finished.active&&!finished.cancelled&&dx*finished.sign>0&&Math.abs(dx)>=DOMINANCE_RATIO*Math.abs(dy)&&(
      Math.abs(dx)>=COMMIT_PX||
      (Math.abs(dx)>=FLICK_DISTANCE_PX&&Math.abs(velocity)>=FLICK_VELOCITY_PX_MS&&velocity*finished.sign>0)
    );
    resetGesture();
    if(!commits)return;
    event.preventDefault();
    event.stopImmediatePropagation();
    if(finished.consumeUtilities)return;
    navigate(finished.direction,{fromGesture:true});
  }

  function onTouchEnd(event){
    const touch=event.changedTouches&&event.changedTouches[0];
    finishGestureAt(touch&&touch.clientX,touch&&touch.clientY,event);
  }

  function onPointerRelease(event){
    if(!gesture||gesture.releasing||event.pointerType!=='touch')return;
    if(gesture.pointerId!==null&&gesture.pointerId!==undefined&&gesture.pointerId!==event.pointerId)return;
    finishGestureAt(event.clientX,event.clientY,event);
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
    if(gesture&&gesture.interactive&&gesture.active){settleInteractive(gesture,false,null);return;}
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
    const toggle=document.getElementById('mobileSessionUtilitiesToggle');
    utilitiesOpenAtPointerDown=Boolean(isPhoneWidth()&&event.pointerType==='touch'&&toggle&&toggle.getAttribute('aria-expanded')==='true');
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
    if(gesture){clearInteractiveDrag();resetGesture();}
    syncLayer();
  });
  observer.observe(root,{attributes:true,attributeFilter:['data-tailnet-view','data-mobile-session-view','data-mobile-rail']});
  if(document.getElementById('appTitlebarTitle'))document.getElementById('appTitlebarTitle').setAttribute('tabindex','-1');
  if(document.getElementById('tailnetAppWorkspace'))document.getElementById('tailnetAppWorkspace').setAttribute('tabindex','-1');
  window.__mobileLayerNavigation={
    currentLayer,
    navigate,
    thresholds:{backEdgeWidth:BACK_EDGE_WIDTH_PX,edgeInset:EDGE_INSET_PX,edgeWidth:EDGE_WIDTH_PX,activate:ACTIVATE_PX,interactiveActivate:AXIS_LOCK_PX,interactiveCommitRatio:INTERACTIVE_COMMIT_RATIO,commit:COMMIT_PX,dominance:DOMINANCE_RATIO}
  };
  syncLayer();
})();
