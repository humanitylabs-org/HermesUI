/* HermesUI frontend-only session dashboard. The transcript remains intact. */
(function(){
  'use strict';
  if(window.__sessionDashboardInstalled) return;
  window.__sessionDashboardInstalled=true;

  const byId=id=>document.getElementById(id);
  const state=()=>typeof S!=='undefined'&&S?S:{session:null,messages:[],busy:false};
  const acceptedRunSteers=new Map();
  const messageEntryCache=new Map();
  const openingEvidenceCache=new Map();
  const openingEvidenceRequests=new Map();
  const OPENING_EVIDENCE_LIMIT=30;
  const rawText=message=>{
    if(!message) return '';
    if(typeof msgContent==='function') return msgContent(message);
    const content=message.content||'';
    if(Array.isArray(content)) return content.filter(part=>part&&part.type==='text').map(part=>part.text||'').join('').trim();
    return String(content).trim();
  };
  const cleanUserText=message=>{
    let text=rawText(message);
    if(typeof _stripWorkspaceDisplayPrefix==='function') text=_stripWorkspaceDisplayPrefix(text);
    else text=String(text||'').replace(/^\s*\[Workspace(?:::[^\]]*|:[^\]]*)\]\s*/i,'').trim();
    if(typeof _stripAttachedFilesMarkerForDisplay==='function') text=_stripAttachedFilesMarkerForDisplay(text);
    return String(text||'').trim();
  };
  const isSystemLike=message=>{
    if(!message) return true;
    if(isBackgroundUpdateTrigger(message)||message.recovery_control===true) return true;
    if(typeof _isContextCompactionMessage==='function'&&_isContextCompactionMessage(message)) return true;
    if(typeof _isPreservedCompressionTaskListMessage==='function'&&_isPreservedCompressionTaskListMessage(message)) return true;
    if(typeof _isRecoveryControlMessage==='function'&&_isRecoveryControlMessage(message)) return true;
    return false;
  };
  function isBackgroundUpdateTrigger(message){
    if(!message||message.role!=='user') return false;
    if(message._source==='process_wakeup'||message._source==='async_delegation') return true;
    return /^\s*\[ASYNC DELEGATION(?: BATCH)? COMPLETE(?:\s*(?:—|-)\s*[^\]]*)?\]/i.test(rawText(message));
  }
  const isRenderable=message=>{
    if(!message||!['user','assistant'].includes(message.role)) return false;
    if(isSystemLike(message)) return false;
    if(typeof _messageIsRenderable==='function'&&!_messageIsRenderable(message)) return false;
    return !!rawText(message);
  };
  const messageSignature=message=>{
    if(!message) return '';
    return [
      message.role||'',
      message.id||message.message_id||message.event_id||'',
      message.created_at||message.timestamp||'',
      message._live?'1':'0',
      rawText(message)
    ].join('\u001f');
  };
  const appendMessageEntry=(cached,message,index)=>{
    if(message&&message.role==='user'){
      cached.backgroundUpdateActive=isBackgroundUpdateTrigger(message);
      if(cached.backgroundUpdateActive) return;
    }
    if(cached.backgroundUpdateActive&&message&&message.role==='assistant'){
      if(isRenderable(message)) cached.entries.push({message,index,intermediary:true});
      return;
    }
    if(!isRenderable(message)) return;
    const entry={message,index};
    cached.entries.push(entry);
    if(!cached.firstUser&&message.role==='user'&&cleanUserText(message)) cached.firstUser=entry;
  };
  const rebuildProjection=(messages)=>{
    const cached={source:messages,length:0,entries:[],firstUser:null,firstSignature:'',tailSignature:'',backgroundUpdateActive:false};
    for(let index=0;index<messages.length;index++) appendMessageEntry(cached,messages[index],index);
    cached.length=messages.length;
    cached.firstSignature=messages.length?messageSignature(messages[0]):'';
    cached.tailSignature=messages.length?messageSignature(messages[messages.length-1]):'';
    return cached;
  };
  const sessionProjection=()=>{
    const current=state();
    const messages=Array.isArray(current.messages)?current.messages:[];
    const session=current.session||{};
    const key=String(session.session_id||session.id||'__none__');
    let cached=messageEntryCache.get(key);
    if(!cached||messages.length<cached.length){
      cached=rebuildProjection(messages);
    }else{
      const firstSignature=messages.length?messageSignature(messages[0]):'';
      const oldTailStillMatches=!cached.length||(
        messages.length>=cached.length&&
        messageSignature(messages[cached.length-1])===cached.tailSignature
      );
      if(firstSignature!==cached.firstSignature||!oldTailStillMatches){
        cached=rebuildProjection(messages);
      }else if(messages.length>cached.length){
        for(let index=cached.length;index<messages.length;index++) appendMessageEntry(cached,messages[index],index);
        cached.source=messages;
        cached.length=messages.length;
        cached.tailSignature=messages.length?messageSignature(messages[messages.length-1]):'';
      }else{
        cached.source=messages;
      }
    }
    messageEntryCache.set(key,cached);
    while(messageEntryCache.size>20) messageEntryCache.delete(messageEntryCache.keys().next().value);
    return cached;
  };
  const sessionMessages=()=>sessionProjection().entries;
  const compact=(text,max=640)=>{
    const value=String(text||'').replace(/\r/g,'').replace(/[ \t]+/g,' ').replace(/\n{3,}/g,'\n\n').trim();
    if(value.length<=max) return value;
    const clipped=value.slice(0,max-1).replace(/\s+\S*$/,'').trim();
    return `${clipped||value.slice(0,max-1)}…`;
  };
  const brief=(text,max=480)=>{
    const value=compact(text,max*2).replace(/```[\s\S]*?```/g,'[code]').replace(/\n+/g,' ').trim();
    const matches=value.match(/[^.!?]+[.!?]+(?:\s+|$)/g);
    const two=matches&&matches.length?matches.slice(0,2).join(' ').trim():value;
    return compact(two,max);
  };
  const setText=(id,text)=>{const element=byId(id);if(element) element.textContent=text;};
  const setMarkdown=(id,text)=>{
    const element=byId(id);
    if(!element) return;
    if(typeof renderMd==='function') element.innerHTML=renderMd(String(text||''));
    else element.textContent=String(text||'');
  };
  const latestMatchingEntry=(entries,predicate)=>{
    for(let index=entries.length-1;index>=0;index--) if(predicate(entries[index])) return entries[index];
    return undefined;
  };
  const latestUserEntry=entries=>latestMatchingEntry(entries,entry=>entry.message.role==='user'&&!entry.intermediary&&cleanUserText(entry.message));
  const latestAssistantEntry=entries=>latestMatchingEntry(entries,entry=>entry.message.role==='assistant'&&!entry.intermediary&&rawText(entry.message)&&!entry.message._live);
  const latestStatusAssistantEntry=entries=>latestMatchingEntry(entries,entry=>entry.message.role==='assistant'&&rawText(entry.message)&&!entry.message._live);

  function latestRunUserEntries(entries){
    const current=state();
    const latestUser=latestUserEntry(entries);
    const latestAssistant=latestAssistantEntry(entries);
    if(!latestUser) return [];
    let boundary=-1;
    if(current.busy||current.activeStreamId||!latestAssistant||latestUser.index>latestAssistant.index){
      boundary=latestAssistant?latestAssistant.index:-1;
    }else{
      for(let index=entries.length-1;index>=0;index--){
        const entry=entries[index];
        if(entry.index>=latestAssistant.index) continue;
        if(entry.message.role==='assistant'&&rawText(entry.message)&&!entry.message._live){
          boundary=entry.index;
          break;
        }
      }
    }
    const users=[];
    const ceiling=latestAssistant&&!current.busy&&!current.activeStreamId&&latestUser.index<latestAssistant.index
      ? latestAssistant.index
      : Number.POSITIVE_INFINITY;
    for(let index=entries.length-1;index>=0;index--){
      const entry=entries[index];
      if(entry.index<=boundary) break;
      if(entry.index<ceiling&&entry.message.role==='user'&&cleanUserText(entry.message)) users.push(entry);
    }
    return users.reverse();
  }

  function activeRunKey(){
    const current=state();
    const session=current.session||{};
    const sid=String(session.session_id||'').trim();
    const streamId=String(current.activeStreamId||session.active_stream_id||'').trim();
    return sid&&streamId?`${sid}:${streamId}`:'';
  }

  function acceptedSteersForActiveRun(){
    if(!state().busy&&!state().activeStreamId) return [];
    const key=activeRunKey();
    return key&&acceptedRunSteers.has(key)?acceptedRunSteers.get(key):[];
  }

  function dashboardInstruction(entries){
    const accepted=acceptedSteersForActiveRun();
    if(accepted.length) return accepted[accepted.length-1];
    const runUsers=latestRunUserEntries(entries);
    if(!runUsers.length) return 'No instruction is available yet.';
    return cleanUserText(runUsers[runUsers.length-1].message);
  }

  function dashboardSessionSummary(projection){
    const openingOffset=typeof _oldestIdx!=='undefined'?Number(_oldestIdx):0;
    const openingIsMissing=(typeof _messagesTruncated!=='undefined'&&!!_messagesTruncated)||(
      Number.isFinite(openingOffset)&&openingOffset>0
    );
    if(openingIsMissing){
      const evidence=openingEvidenceCache.get(sessionKey());
      if(evidence&&evidence.text) return evidence.text;
      if(evidence&&evidence.error) return 'The original request could not be loaded. Use Refresh goal to retry.';
      return 'Loading the original request…';
    }
    const firstUser=projection.firstUser;
    const firstText=firstUser?cleanUserText(firstUser.message):'';
    return firstText||'No goal is available yet.';
  }

  async function hydrateDashboardOpeningEvidence(options={}){
    const key=sessionKey();
    if(!key||typeof api!=='function') return;
    if(!options.force&&openingEvidenceCache.has(key)) return;
    if(openingEvidenceRequests.has(key)) return openingEvidenceRequests.get(key);
    openingEvidenceCache.set(key,{pending:true,text:'',error:''});
    if(key===sessionKey()) scheduleSessionDashboardSync();
    const request=(async()=>{
      try{
        const data=await api(`/api/session?session_id=${encodeURIComponent(key)}&messages=1&resolve_model=0&msg_before=${OPENING_EVIDENCE_LIMIT}&msg_limit=${OPENING_EVIDENCE_LIMIT}`,{timeoutMs:120000});
        const session=data&&data.session?data.session:data;
        const messages=session&&Array.isArray(session.messages)?session.messages:[];
        const projection=rebuildProjection(messages);
        const firstText=projection.firstUser?cleanUserText(projection.firstUser.message):'';
        openingEvidenceCache.set(key,{pending:false,text:firstText,error:firstText?'':'missing'});
      }catch(error){
        openingEvidenceCache.set(key,{pending:false,text:'',error:String(error&&error.message||error||'unavailable')});
      }finally{
        openingEvidenceRequests.delete(key);
        if(key===sessionKey()) scheduleSessionDashboardSync();
      }
    })();
    openingEvidenceRequests.set(key,request);
    return request;
  }

  function refreshDashboardSummary(){
    openingEvidenceCache.delete(sessionKey());
    setMarkdown('sessionDashboardOriginalRequest','Loading the original request…');
    setText('sessionDashboardSummaryUpdated','Loading');
    void hydrateDashboardOpeningEvidence({force:true});
  }

  function activeStep(){
    const current=state();
    const sid=current.session&&current.session.session_id;
    const inflight=typeof INFLIGHT!=='undefined'&&sid&&INFLIGHT?INFLIGHT[sid]:null;
    const todos=inflight&&Array.isArray(inflight.todos)?inflight.todos:[];
    const active=todos.find(todo=>todo&&todo.status==='in_progress')||todos.find(todo=>todo&&todo.status==='pending');
    return active&&active.content?brief(active.content,220):'';
  }

  function dashboardTurnProgress(){
    const current=state();
    const sid=current.session&&current.session.session_id;
    const inflight=typeof INFLIGHT!=='undefined'&&sid&&INFLIGHT?INFLIGHT[sid]:null;
    const candidates=[
      inflight&&inflight.turn_progress,
      inflight&&inflight.run_progress,
      inflight&&inflight.progress,
      inflight,
      current.session&&current.session.turn_progress,
      current.session&&current.session.run_progress,
      current.session&&current.session.progress,
      current.session
    ].filter(value=>value&&typeof value==='object');
    const read=(value,keys)=>{
      for(const key of keys){
        const number=Number(value[key]);
        if(Number.isFinite(number)&&number>=0) return number;
      }
      return null;
    };
    for(const candidate of candidates){
      const turn=read(candidate,['current_turn','currentTurn','turn_number','turnNumber','current_iteration','currentIteration','iteration']);
      const max=read(candidate,['max_turns','maxTurns','turn_limit','turnLimit','max_iterations','maxIterations','iteration_limit','iterationLimit']);
      if(turn!==null&&max!==null&&max>0&&turn<=max) return {turn,max};
    }
    return null;
  }

  function assistantUpdatesSinceLatestInstruction(entries){
    const user=latestUserEntry(entries);
    if(!user) return '';
    return entries
      .filter(entry=>entry.index>user.index&&entry.message.role==='assistant'&&rawText(entry.message))
      .map(entry=>rawText(entry.message))
      .join('\n\n');
  }

  function dashboardStatus(entries){
    const current=state();
    if(!current.session) return 'No session is selected. Start or open a session to see its status.';
    if(current.busy||current.activeStreamId){
      const updates=assistantUpdatesSinceLatestInstruction(entries);
      if(updates) return updates;
      const step=activeStep();
      return step
        ? `Hermes is working on your latest instruction. Current step: ${step}`
        : 'Hermes is working on your latest instruction. The current run is active; refresh this card for the latest frontend state.';
    }
    const user=latestUserEntry(entries);
    const statusAssistant=latestStatusAssistantEntry(entries);
    if(user&&statusAssistant&&statusAssistant.intermediary&&statusAssistant.index>user.index){
      return brief(rawText(statusAssistant.message),900);
    }
    const assistant=latestAssistantEntry(entries);
    if(user&&assistant&&assistant.index>user.index){
      return 'The latest run has finished. Its completed result is available below.';
    }
    if(user) return 'Your latest instruction is recorded. Hermes has not produced a completed result for it yet.';
    return 'This session has no instructions yet. Send a message to begin.';
  }

  function dashboardCompleted(entries){
    const current=state();
    if(current.busy||current.activeStreamId) return '';
    const user=latestUserEntry(entries);
    const assistant=latestAssistantEntry(entries);
    if(!assistant||user&&assistant.index<user.index) return '';
    return compact(rawText(assistant.message),12000);
  }

  const statusSnapshots=new Map();
  const sessionKey=()=>{
    const current=state();
    return current.session&&String(current.session.session_id||current.session.id||'');
  };

  function showStatusSnapshot(){
    const snapshot=statusSnapshots.get(sessionKey());
    setMarkdown('sessionDashboardStatus',snapshot?snapshot.text:dashboardStatus(sessionMessages()));
    setText('sessionDashboardUpdated',snapshot?`Updated ${snapshot.updated}`:'Current frontend state');
    const turnBadge=byId('sessionDashboardTurn');
    if(turnBadge){
      turnBadge.hidden=!(snapshot&&snapshot.turnProgress);
      turnBadge.textContent=snapshot&&snapshot.turnProgress?`Turn ${snapshot.turnProgress.turn} of ${snapshot.turnProgress.max}`:'';
    }
  }

  function refreshDashboardStatus(){
    const key=sessionKey();
    if(!key) return;
    statusSnapshots.set(key,{
      text:dashboardStatus(sessionMessages()),
      updated:new Date().toLocaleTimeString([], {hour:'numeric',minute:'2-digit',second:'2-digit'}),
      turnProgress:dashboardTurnProgress()
    });
    showStatusSnapshot();
  }

  function syncSessionDashboard(){
    const dashboard=byId('sessionDashboard');
    if(!dashboard) return;
    const root=document.documentElement;
    updateSessionViewToggle();
    if(root&&root.dataset&&root.dataset.sessionView==='classic'){
      dashboard.hidden=true;
      return;
    }
    const current=state();
    const projection=sessionProjection();
    const entries=projection.entries;
    const hasSession=!!(current.session&&entries.length);
    dashboard.hidden=!hasSession;
    if(!hasSession) return;

    const completed=dashboardCompleted(entries);
    setMarkdown('sessionDashboardOriginalRequest',dashboardSessionSummary(projection));
    const openingOffset=typeof _oldestIdx!=='undefined'?Number(_oldestIdx):0;
    const openingIsMissing=(typeof _messagesTruncated!=='undefined'&&!!_messagesTruncated)||(Number.isFinite(openingOffset)&&openingOffset>0);
    const openingEvidence=openingEvidenceCache.get(sessionKey());
    setText('sessionDashboardSummaryUpdated',openingIsMissing
      ? openingEvidence&&openingEvidence.text?'Loaded from session start':openingEvidence&&openingEvidence.error?'Unavailable':'Loading'
      : 'From session start');
    setMarkdown('sessionDashboardInstruction',dashboardInstruction(entries));
    setMarkdown('sessionDashboardCompleted',completed||'Not completed yet.');
    showStatusSnapshot();
    const completedCard=byId('sessionDashboardCompletedCard');
    if(completedCard) completedCard.dataset.empty=completed?'0':'1';
    if(openingIsMissing&&!openingEvidenceCache.has(sessionKey())) void hydrateDashboardOpeningEvidence();
  }

  function updateSessionViewToggle(){
    const toggle=byId('sessionViewToggle');
    if(!toggle||typeof toggle.setAttribute!=='function') return;
    const root=document.documentElement;
    const dashboard=!!(root&&root.dataset&&root.dataset.sessionView==='dashboard');
    toggle.setAttribute('aria-pressed',dashboard?'true':'false');
    const label=dashboard?'Disable High Signal mode':'Enable High Signal mode';
    toggle.setAttribute('aria-label',label);
    toggle.title=label;
  }

  function setSessionView(view,options={}){
    const next=view==='dashboard'||view==='high-signal'?'dashboard':'classic';
    const root=document.documentElement;
    if(root&&root.dataset) root.dataset.sessionView=next;
    try{localStorage.setItem('hermes-session-view',next);}catch(_){ }
    if(options.updateUrl!==false&&window.history&&typeof window.history.replaceState==='function'){
      const url=new URL(window.location.href);
      url.searchParams.set('session_view',next==='dashboard'?'high-signal':'classic');
      window.history.replaceState(window.history.state,'',url);
    }
    updateSessionViewToggle();
    syncSessionDashboard();
    return next;
  }

  let dashboardSyncScheduled=false;
  function scheduleSessionDashboardSync(){
    if(dashboardSyncScheduled) return;
    dashboardSyncScheduled=true;
    const schedule=typeof requestAnimationFrame==='function'
      ? requestAnimationFrame
      : callback=>setTimeout(callback,0);
    schedule(()=>{
      dashboardSyncScheduled=false;
      syncSessionDashboard();
    });
  }

  function wrapAfter(name){
    const original=window[name];
    if(typeof original!=='function'||original.__sessionDashboardWrapped) return;
    const wrapped=function(){
      const result=original.apply(this,arguments);
      if(result&&typeof result.finally==='function') result.finally(()=>queueMicrotask(scheduleSessionDashboardSync));
      else queueMicrotask(scheduleSessionDashboardSync);
      return result;
    };
    wrapped.__sessionDashboardWrapped=true;
    window[name]=wrapped;
  }

  window.syncSessionDashboard=syncSessionDashboard;
  window.setSessionView=setSessionView;
  window.toggleSessionView=function(){
    const next=document.documentElement.dataset.sessionView==='dashboard'?'classic':'dashboard';
    return setSessionView(next);
  };
  window.recordSessionDashboardSteer=function(detail){
    const sid=String(detail&&detail.sessionId||'').trim();
    const streamId=String(detail&&detail.streamId||'').trim();
    const text=cleanUserText({content:detail&&detail.text});
    if(!sid||!streamId||!text) return;
    const key=`${sid}:${streamId}`;
    const steers=acceptedRunSteers.get(key)||[];
    steers.push(text);
    acceptedRunSteers.set(key,steers);
    while(acceptedRunSteers.size>20) acceptedRunSteers.delete(acceptedRunSteers.keys().next().value);
    scheduleSessionDashboardSync();
  };
  ['renderMessages','setBusy','syncTopbar'].forEach(wrapAfter);

  const init=()=>{
    const refresh=byId('sessionDashboardRefresh');
    if(refresh) refresh.addEventListener('click',refreshDashboardStatus);
    const summaryRefresh=byId('sessionDashboardSummaryRefresh');
    if(summaryRefresh) summaryRefresh.addEventListener('click',refreshDashboardSummary);
    syncSessionDashboard();
  };
  if(document.readyState==='loading') document.addEventListener('DOMContentLoaded',init,{once:true});
  else init();
})();
