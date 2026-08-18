/* HermesUI frontend-only session dashboard. The transcript remains intact. */
(function(){
  'use strict';
  if(window.__sessionDashboardInstalled) return;
  window.__sessionDashboardInstalled=true;

  const byId=id=>document.getElementById(id);
  const state=()=>typeof S!=='undefined'&&S?S:{session:null,messages:[],busy:false};
  const acceptedRunSteers=new Map();
  const messageEntryCache=new Map();
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
    if(message._source==='process_wakeup'||message.recovery_control===true) return true;
    if(typeof _isContextCompactionMessage==='function'&&_isContextCompactionMessage(message)) return true;
    if(typeof _isPreservedCompressionTaskListMessage==='function'&&_isPreservedCompressionTaskListMessage(message)) return true;
    if(typeof _isRecoveryControlMessage==='function'&&_isRecoveryControlMessage(message)) return true;
    return false;
  };
  const isRenderable=message=>{
    if(!message||!['user','assistant'].includes(message.role)) return false;
    if(isSystemLike(message)) return false;
    if(typeof _messageIsRenderable==='function'&&!_messageIsRenderable(message)) return false;
    return !!rawText(message);
  };
  const sessionMessages=()=>{
    const current=state();
    const messages=Array.isArray(current.messages)?current.messages:[];
    const session=current.session||{};
    const key=String(session.session_id||session.id||'__none__');
    let cached=messageEntryCache.get(key);
    if(!cached||cached.source!==messages||messages.length<cached.length){
      cached={source:messages,length:0,entries:[]};
    }
    if(messages.length>cached.length){
      for(let index=cached.length;index<messages.length;index++){
        const message=messages[index];
        if(isRenderable(message)) cached.entries.push({message,index});
      }
    }else if(messages.length&&cached.length===messages.length){
      const index=messages.length-1;
      cached.entries=cached.entries.filter(entry=>entry.index!==index);
      if(isRenderable(messages[index])) cached.entries.push({message:messages[index],index});
    }
    cached.length=messages.length;
    messageEntryCache.set(key,cached);
    while(messageEntryCache.size>20) messageEntryCache.delete(messageEntryCache.keys().next().value);
    return cached.entries;
  };
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
  const latestUserEntry=entries=>[...entries].reverse().find(entry=>entry.message.role==='user'&&cleanUserText(entry.message));
  const latestAssistantEntry=entries=>[...entries].reverse().find(entry=>entry.message.role==='assistant'&&rawText(entry.message)&&!entry.message._live);

  function latestRunUserEntries(entries){
    const current=state();
    const users=entries.filter(entry=>entry.message.role==='user'&&cleanUserText(entry.message));
    const assistants=entries.filter(entry=>entry.message.role==='assistant'&&rawText(entry.message)&&!entry.message._live);
    const latestUser=users[users.length-1];
    const latestAssistant=assistants[assistants.length-1];
    if(!latestUser) return [];
    if(current.busy||current.activeStreamId||!latestAssistant||latestUser.index>latestAssistant.index){
      const boundary=latestAssistant?latestAssistant.index:-1;
      return users.filter(entry=>entry.index>boundary);
    }
    const previousAssistant=[...assistants].reverse().find(entry=>entry.index<latestAssistant.index);
    const boundary=previousAssistant?previousAssistant.index:-1;
    return users.filter(entry=>entry.index>boundary&&entry.index<latestAssistant.index);
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

  function dashboardSessionSummary(entries){
    const firstUser=entries.find(entry=>entry.message.role==='user'&&cleanUserText(entry.message));
    const firstText=firstUser?cleanUserText(firstUser.message):'';
    return firstText||'No original request is available yet.';
  }

  function refreshDashboardSummary(){
    setMarkdown('sessionDashboardOriginalRequest',dashboardSessionSummary(sessionMessages()));
    setText('sessionDashboardSummaryUpdated',`Placeholder refreshed ${new Date().toLocaleTimeString([], {hour:'numeric',minute:'2-digit',second:'2-digit'})}`);
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
    setMarkdown('sessionDashboardStatus',snapshot?snapshot.text:'Click Refresh status to check the current frontend state.');
    setText('sessionDashboardUpdated',snapshot?`Updated ${snapshot.updated}`:'Manual refresh only');
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
    const current=state();
    const entries=sessionMessages();
    const hasSession=!!(current.session&&entries.length);
    dashboard.hidden=!hasSession;
    if(!hasSession) return;

    const completed=dashboardCompleted(entries);
    setMarkdown('sessionDashboardOriginalRequest',dashboardSessionSummary(entries));
    setMarkdown('sessionDashboardInstruction',dashboardInstruction(entries));
    setMarkdown('sessionDashboardCompleted',completed||'Not completed yet.');
    showStatusSnapshot();
    const completedCard=byId('sessionDashboardCompletedCard');
    if(completedCard) completedCard.dataset.empty=completed?'0':'1';
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
