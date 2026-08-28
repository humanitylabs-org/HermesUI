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
  const CONVERSATION_COMMIT_PX=24;
  const COMMIT_PX=72;
  const FLICK_DISTANCE_PX=40;
  const FLICK_VELOCITY_PX_MS=.5;
  const DOMINANCE_RATIO=1.6;
  const GESTURE_TIMEOUT_MS=900;
  const COOLDOWN_MS=250;
  const BLOCKED_ORIGIN_SELECTOR=[
    '.composer-box','textarea','input','select','[contenteditable="true"]',
    '.messages pre','.msg-body pre','code','table','.project-bar','.session-source-tabs',
    '.mobile-primary-menu','.mobile-session-utilities-menu','.rail','.mobile-rail-handle',
    '.rightpanel','.tailnet-notifications','.settings-popup:not([hidden])','dialog[open]','[role="dialog"]'
  ].join(',');

  let gesture=null;
  let cooldownUntil=0;
  let utilitiesOpenAtPointerDown=false;

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
    if(layer==='app'){
      if(target!==appSwipeZone)return null;
      return {layer,direction:'forward',sign:-1};
    }
    const rightEdge=contentRightEdge();
    const inBackBand=touch.clientX>=0&&touch.clientX<=BACK_EDGE_WIDTH_PX;
    const forwardBandEnd=rightEdge-EDGE_INSET_PX;
    const inForwardBand=touch.clientX>=forwardBandEnd-EDGE_WIDTH_PX&&touch.clientX<=forwardBandEnd;
    if(layer==='conversation'&&target===backSwipeZone&&inBackBand)return {layer,direction:'back',sign:1};
    if(layer==='sessions'&&inBackBand)return {layer,direction:'back',sign:1};
    if(layer==='sessions'&&inForwardBand)return {layer,direction:'forward',sign:-1};
    return null;
  }

  function resetGesture(){gesture=null;}

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
    if(event.touches.length!==1)return resetGesture();
    const touch=event.touches[0];
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
      startAt:performance.now(),
      locked:false,
      active:false,
      committed:false,
      cancelled:false,
      peak:0,
      samples:[{x:touch.clientX,t:performance.now()}]
    };
  }

  function onTouchMove(event){
    if(gesture&&gesture.committed){
      event.preventDefault();
      event.stopImmediatePropagation();
      return;
    }
    if(!gesture||gesture.cancelled||event.touches.length!==1)return;
    const touch=event.touches[0];
    const now=performance.now();
    const dx=touch.clientX-gesture.startX;
    const dy=touch.clientY-gesture.startY;
    const absX=Math.abs(dx);
    const absY=Math.abs(dy);
    if(now-gesture.startAt>GESTURE_TIMEOUT_MS){gesture.cancelled=true;return;}
    if(dx*gesture.sign<0&&absX>=AXIS_LOCK_PX){gesture.cancelled=true;return;}
    if(!gesture.locked&&Math.hypot(dx,dy)>=AXIS_LOCK_PX){
      if(absY>=12&&absY>=absX){gesture.cancelled=true;return;}
      if(absX<=absY){gesture.cancelled=true;return;}
      gesture.locked=true;
    }
    if(!gesture.locked)return;
    recordSample(touch,now);
    gesture.peak=Math.max(gesture.peak,absX);
    if(gesture.peak>0&&absX<gesture.peak*.5){gesture.cancelled=true;return;}
    if(!gesture.active&&absX>=ACTIVATE_PX&&absX>=DOMINANCE_RATIO*absY){
      gesture.active=true;
      cancelOriginRow();
    }
    if(gesture.active){
      event.preventDefault();
      event.stopImmediatePropagation();
      if(
        !gesture.committed&&
        gesture.layer==='conversation'&&gesture.direction==='back'&&
        absX>=CONVERSATION_COMMIT_PX
      ){
        gesture.committed=true;
        if(!gesture.consumeUtilities)navigate(gesture.direction,{fromGesture:true});
      }
    }
  }

  function trailingVelocity(){
    if(!gesture||gesture.samples.length<2)return 0;
    const first=gesture.samples[0];
    const last=gesture.samples[gesture.samples.length-1];
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

  function focusLayer(layer){
    window.setTimeout(()=>{
      let target=null;
      if(layer==='sessions')target=document.querySelector('#panelChat>.panel-head');
      else if(layer==='conversation')target=document.getElementById('appTitlebarTitle');
      else target=document.getElementById('tailnetAppWorkspace');
      if(!target)return;
      if(!target.hasAttribute('tabindex'))target.setAttribute('tabindex','-1');
      try{target.focus({preventScroll:true});}catch(_){try{target.focus();}catch(__){}}
    },motionDelay());
  }

  function finishTransition(layer){
    cooldownUntil=Date.now()+COOLDOWN_MS;
    root.dataset.mobileLayer=layer;
    announceLayer(layer);
    focusLayer(layer);
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
      return finishTransition('sessions');
    }
    if(layer==='sessions'&&direction==='forward'){
      if(!hasConversation()||typeof window.closeMobileSidebar!=='function')return false;
      window.closeMobileSidebar(true);
      if(currentLayer()==='sessions')return false;
      return finishTransition('conversation');
    }
    if(layer==='sessions'&&direction==='back'){
      if(!tailnet||typeof tailnet.restoreLastApp!=='function'||!tailnet.restoreLastApp())return false;
      return finishTransition('app');
    }
    if(layer==='app'&&direction==='forward'){
      if(!tailnet||typeof tailnet.openSessions!=='function'||!tailnet.openSessions())return false;
      return finishTransition('sessions');
    }
    return false;
  }

  function onTouchEnd(event){
    if(!gesture)return;
    const finished=gesture;
    if(finished.committed){
      resetGesture();
      cooldownUntil=Date.now()+COOLDOWN_MS;
      event.preventDefault();
      event.stopImmediatePropagation();
      return;
    }
    const touch=event.changedTouches&&event.changedTouches[0];
    const dx=touch?touch.clientX-finished.startX:0;
    const dy=touch?touch.clientY-finished.startY:0;
    const velocity=trailingVelocity();
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

  function onTouchCancel(event){
    if(event&&event.mobileLayerSynthetic)return;
    resetGesture();
  }

  function syncLayer(){
    if(!isPhoneWidth()){
      root.removeAttribute('data-mobile-layer');
      resetGesture();
      return;
    }
    root.dataset.mobileLayer=currentLayer();
  }

  document.addEventListener('pointerdown',event=>{
    const toggle=document.getElementById('mobileSessionUtilitiesToggle');
    utilitiesOpenAtPointerDown=Boolean(isPhoneWidth()&&event.pointerType==='touch'&&toggle&&toggle.getAttribute('aria-expanded')==='true');
  },{capture:true,passive:true});
  document.addEventListener('touchstart',onTouchStart,{capture:true,passive:true});
  document.addEventListener('touchmove',onTouchMove,{capture:true,passive:false});
  document.addEventListener('touchend',onTouchEnd,{capture:true,passive:false});
  document.addEventListener('touchcancel',onTouchCancel,{capture:true,passive:true});
  window.addEventListener('resize',syncLayer,{passive:true});
  document.addEventListener('hermesui:tailnet-app-selected',syncLayer);
  const observer=new MutationObserver(syncLayer);
  observer.observe(root,{attributes:true,attributeFilter:['data-tailnet-view','data-mobile-session-view','data-mobile-rail']});
  if(document.getElementById('appTitlebarTitle'))document.getElementById('appTitlebarTitle').setAttribute('tabindex','-1');
  if(document.getElementById('tailnetAppWorkspace'))document.getElementById('tailnetAppWorkspace').setAttribute('tabindex','-1');
  window.__mobileLayerNavigation={
    currentLayer,
    navigate,
    thresholds:{backEdgeWidth:BACK_EDGE_WIDTH_PX,edgeInset:EDGE_INSET_PX,edgeWidth:EDGE_WIDTH_PX,activate:ACTIVATE_PX,conversationCommit:CONVERSATION_COMMIT_PX,commit:COMMIT_PX,dominance:DOMINANCE_RATIO}
  };
  syncLayer();
})();
