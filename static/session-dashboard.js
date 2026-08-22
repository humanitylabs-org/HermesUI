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
  const grokSummaryCache=new Map();
  const grokSummaryRequests=new Map();
  const grokSummaryErrors=new Map();
  const grokSummaryAutoChecks=new Map();
  const OPENING_EVIDENCE_LIMIT=30;
  const GROK_SUMMARY_ENDPOINT='/apps/api/high-signal-summary';
  const SUMMARY_AUTO_CHECK_MS=60*1000;
  const SUMMARY_AUTO_REFRESH_FLOOR_MS=5*60*1000;
  const structuredContentText=value=>{
    if(Array.isArray(value)){
      let recognized=false;
      const text=[];
      for(const part of value){
        const extracted=structuredContentText(part);
        recognized=recognized||extracted.recognized;
        if(extracted.text) text.push(extracted.text);
      }
      return {recognized,text:text.join('\n').trim()};
    }
    if(value&&typeof value==='object'){
      const type=String(value.type||'').toLowerCase();
      if(['image','image_url','input_image','output_image'].includes(type)) return {recognized:true,text:''};
      if(['text','input_text','output_text'].includes(type)&&typeof value.text==='string'){
        return {recognized:true,text:value.text.trim()};
      }
      if(Object.prototype.hasOwnProperty.call(value,'content')){
        const extracted=structuredContentText(value.content);
        return {recognized:true,text:extracted.text};
      }
      return {recognized:false,text:''};
    }
    return {recognized:false,text:''};
  };
  const serializedStructuredText=value=>{
    const text=String(value||'').trim();
    const explicitlySerialized=/^json\s*:/i.test(text);
    const source=explicitlySerialized?text.replace(/^json\s*:\s*/i,''):text;
    if(!/^[\[{]/.test(source)) return null;
    try{
      const extracted=structuredContentText(JSON.parse(source));
      return extracted.recognized?extracted.text:null;
    }catch(_){
      // Some live message adapters prefix structured parts with `json:` after
      // expanding escaped newlines into literal control characters. Recover
      // only text parts from that known shape and ignore every image payload.
      if(!explicitlySerialized) return null;
      const parts=[];
      const pattern=/"type"\s*:\s*"(?:text|input_text|output_text)"[\s\S]*?"text"\s*:\s*"((?:\\.|[^"\\])*)"/gi;
      let match;
      while((match=pattern.exec(source))){
        const quoted=String(match[1]||'').replace(/\r/g,'\\r').replace(/\n/g,'\\n').replace(/\t/g,'\\t');
        try{parts.push(JSON.parse(`"${quoted}"`));}
        catch(_decode){parts.push(String(match[1]||'').replace(/\\n/g,'\n').replace(/\\"/g,'"').replace(/\\\\/g,'\\'));}
      }
      return parts.length?parts.join('\n').trim():null;
    }
  };
  const rawText=message=>{
    if(!message) return '';
    const direct=structuredContentText(message.content);
    if(direct.recognized) return direct.text;
    const fallback=typeof msgContent==='function'?msgContent(message):message.content||'';
    const parsed=serializedStructuredText(fallback);
    return parsed===null?String(fallback||'').trim():parsed;
  };
  const cleanUserText=message=>{
    let text=rawText(message);
    if(typeof _stripWorkspaceDisplayPrefix==='function') text=_stripWorkspaceDisplayPrefix(text);
    else text=String(text||'').replace(/^\s*\[Workspace(?:::[^\]]*|:[^\]]*)\]\s*/i,'').trim();
    if(typeof _stripAttachedFilesMarkerForDisplay==='function') text=_stripAttachedFilesMarkerForDisplay(text);
    else text=String(text||'').replace(/\s*\[Attached files?:[\s\S]*?\]\s*$/i,'').trim();
    text=String(text||'').replace(/\s*<memory-context>[\s\S]*?<\/memory-context>\s*$/i,'').trim();
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
    const text=rawText(message);
    return /^\s*\[ASYNC DELEGATION(?: BATCH)? COMPLETE(?:\s*(?:—|-)\s*[^\]]*)?\]/i.test(text)
      || /^\s*\[IMPORTANT:\s*Background process\b/i.test(text)
      || /^\s*\[BACKGROUND WAKEUP\b/i.test(text);
  }
  function assistantContinuesUserDirectedTurn(message){
    if(!message||message.role!=='assistant') return false;
    if(Array.isArray(message.tool_calls)&&message.tool_calls.length) return true;
    if(Array.isArray(message._partial_tool_calls)&&message._partial_tool_calls.length) return true;
    if(Array.isArray(message.content)&&message.content.some(part=>part&&part.type==='tool_use')) return true;
    return String(message.finish_reason||'').toLowerCase()==='tool_calls';
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
      message.role==='user'?cleanUserText(message):rawText(message)
    ].join('\u001f');
  };
  const appendMessageEntry=(cached,message,index)=>{
    if(message&&message.role==='user'){
      if(isBackgroundUpdateTrigger(message)){
        cached.backgroundUpdateActive=!cached.userDirectedRunOpen;
        return;
      }
      cached.backgroundUpdateActive=false;
      cached.userDirectedRunOpen=true;
    }
    if(cached.backgroundUpdateActive){
      if(message&&message.role==='assistant'&&!assistantContinuesUserDirectedTurn(message)) cached.backgroundUpdateActive=false;
      return;
    }
    if(message&&message.role==='assistant'){
      if(assistantContinuesUserDirectedTurn(message)) cached.userDirectedRunOpen=true;
      else if(isRenderable(message)) cached.userDirectedRunOpen=false;
    }
    if(!isRenderable(message)) return;
    const entry={message,index};
    cached.entries.push(entry);
    if(!cached.firstUser&&message.role==='user'&&cleanUserText(message)) cached.firstUser=entry;
  };
  const rebuildProjection=(messages)=>{
    const cached={source:messages,length:0,entries:[],firstUser:null,firstSignature:'',tailSignature:'',backgroundUpdateActive:false,userDirectedRunOpen:false};
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
  const latestAssistantEntry=entries=>latestMatchingEntry(entries,entry=>(
    entry.message.role==='assistant'
    && !entry.intermediary
    && rawText(entry.message)
    && !entry.message._live
    && !assistantContinuesUserDirectedTurn(entry.message)
  ));

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
        if(
          entry.message.role==='assistant'
          && rawText(entry.message)
          && !entry.message._live
          && !assistantContinuesUserDirectedTurn(entry.message)
        ){
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
        openingEvidenceCache.set(key,{pending:false,text:firstText,messages,error:firstText?'':'missing'});
      }catch(error){
        openingEvidenceCache.set(key,{pending:false,text:'',messages:[],error:String(error&&error.message||error||'unavailable')});
      }finally{
        openingEvidenceRequests.delete(key);
        if(key===sessionKey()) scheduleSessionDashboardSync();
      }
    })();
    openingEvidenceRequests.set(key,request);
    return request;
  }

  function refreshDashboardSummary(){
    void refreshGrokSummary('goal',{force:true});
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

  function dashboardCompleted(entries){
    const current=state();
    if(current.busy||current.activeStreamId) return '';
    const user=latestUserEntry(entries);
    const assistant=latestAssistantEntry(entries);
    if(!assistant||user&&assistant.index<user.index) return '';
    return compact(rawText(assistant.message),12000);
  }

  const sessionKey=()=>{
    const current=state();
    return current.session&&String(current.session.session_id||current.session.id||'');
  };


  function backgroundFreeMessages(messages){
    const filtered=[];
    let backgroundActive=false;
    let userDirectedRunOpen=false;
    for(const message of Array.isArray(messages)?messages:[]){
      if(!message||!message.role) continue;
      if(message.role==='user'){
        if(isBackgroundUpdateTrigger(message)){
          backgroundActive=!userDirectedRunOpen;
          continue;
        }
        backgroundActive=false;
        userDirectedRunOpen=true;
      }
      if(backgroundActive){
        if(message.role==='assistant'&&!assistantContinuesUserDirectedTurn(message)) backgroundActive=false;
        continue;
      }
      if(isSystemLike(message)) continue;
      if(message.role==='assistant'){
        if(assistantContinuesUserDirectedTurn(message)) userDirectedRunOpen=true;
        else if(isRenderable(message)) userDirectedRunOpen=false;
      }
      if(['user','assistant','tool'].includes(message.role)) filtered.push(message);
    }
    return filtered;
  }

  function evidenceLine(message,kind){
    if(!message) return '';
    if(message.role==='user'){
      const text=compact(cleanUserText(message),kind==='goal'?1400:1000);
      return text?`USER: ${text}`:'';
    }
    if(message.role==='assistant'){
      const text=compact(rawText(message),kind==='goal'?1600:1800);
      if(text) return `ASSISTANT: ${text}`;
    }
    return '';
  }

  function uniqueMessages(messages){
    const seen=new Set();
    const unique=[];
    for(const message of messages){
      const signature=messageSignature(message);
      if(!signature||seen.has(signature)) continue;
      seen.add(signature);
      unique.push(message);
    }
    return unique;
  }

  function evidenceFingerprint(lines){
    let hash=2166136261;
    const value=lines.join('\n');
    for(let index=0;index<value.length;index++){
      hash^=value.charCodeAt(index);
      hash=Math.imul(hash,16777619);
    }
    return `${lines.length}:${(hash>>>0).toString(16)}`;
  }

  function grokEvidence(kind){
    const current=state();
    const recent=Array.isArray(current.messages)?current.messages:[];
    let candidates=[];
    if(kind==='goal'){
      const opening=openingEvidenceCache.get(sessionKey());
      const openingMessages=opening&&Array.isArray(opening.messages)?opening.messages:[];
      const all=backgroundFreeMessages(uniqueMessages([...openingMessages,...recent]))
        .filter(message=>message.role==='user');
      candidates=all.length>30?[...all.slice(0,8),...all.slice(-22)]:all;
    }else{
      candidates=backgroundFreeMessages(recent)
        .filter(message=>message.role==='user'||message.role==='assistant')
        .slice(-64);
    }
    const lines=candidates.map(message=>evidenceLine(message,kind)).filter(Boolean);
    if(kind==='status'){
      const currentStep=activeStep();
      if(currentStep) lines.push(`ACTIVE TASK: ${currentStep}`);
      lines.push((current.busy||current.activeStreamId)?'RUNTIME: The user-directed run is active.':'RUNTIME: No user-directed run is currently active.');
    }
    return {lines:lines.slice(-80),fingerprint:evidenceFingerprint(lines.slice(-80))};
  }

  function grokCacheKey(kind,sid=sessionKey()){
    return `${sid}:${kind}`;
  }

  function renderGrokSummary(kind){
    const sid=sessionKey();
    const key=grokCacheKey(kind,sid);
    const record=grokSummaryCache.get(key);
    const request=grokSummaryRequests.get(key);
    const error=grokSummaryErrors.get(key);
    const targetId=kind==='goal'?'sessionDashboardOriginalRequest':'sessionDashboardStatus';
    const metaId=kind==='goal'?'sessionDashboardSummaryUpdated':'sessionDashboardUpdated';
    const emptyText='Preparing summary…';
    const label=record&&(
      String(record.provider||'').includes('xai')
      || String(record.model||'').toLowerCase().includes('grok')
    )?'Grok':'AI';
    setMarkdown(targetId,record&&record.text?record.text:emptyText);
    if(request) setText(metaId,'AI • Evaluating…');
    else if(error) setText(metaId,`AI • ${error}`);
    else if(record){
      const currentFingerprint=grokEvidence(kind).fingerprint;
      setText(metaId,record.fingerprint===currentFingerprint?`${label} • Updated ${record.updated}`:`${label} • Auto-refresh pending`);
    }else setText(metaId,'AI • Preparing…');
  }

  function setSummaryButtonBusy(kind,busy){
    const button=byId(kind==='goal'?'sessionDashboardSummaryRefresh':'sessionDashboardRefresh');
    if(!button) return;
    button.disabled=!!busy;
    button.setAttribute('aria-busy',busy?'true':'false');
    button.textContent=busy?'Updating…':'Refresh';
  }

  async function refreshGrokSummary(kind,options={}){
    const sid=sessionKey();
    if(!sid||!['goal','status'].includes(kind)) return;
    const key=grokCacheKey(kind,sid);
    if(grokSummaryRequests.has(key)) return grokSummaryRequests.get(key);
    if(kind==='goal'){
      const openingOffset=typeof _oldestIdx!=='undefined'?Number(_oldestIdx):0;
      const openingMissing=(typeof _messagesTruncated!=='undefined'&&!!_messagesTruncated)||(Number.isFinite(openingOffset)&&openingOffset>0);
      const cached=openingEvidenceCache.get(sid);
      if(openingMissing&&(!cached||cached.error)) await hydrateDashboardOpeningEvidence({force:!!cached});
    }
    if(grokSummaryRequests.has(key)) return grokSummaryRequests.get(key);
    const evidence=grokEvidence(kind);
    if(!evidence.lines.length){
      grokSummaryErrors.set(key,'No usable session evidence');
      renderGrokSummary(kind);
      return;
    }
    const existing=grokSummaryCache.get(key);
    if(!options.force&&existing&&existing.fingerprint===evidence.fingerprint){
      renderGrokSummary(kind);
      return;
    }
    grokSummaryErrors.delete(key);
    setSummaryButtonBusy(kind,true);
    const request=(async()=>{
      const controller=new AbortController();
      const timer=setTimeout(()=>controller.abort(),65000);
      try{
        const response=await fetch(GROK_SUMMARY_ENDPOINT,{
          method:'POST',
          credentials:'same-origin',
          headers:{'Content-Type':'application/json'},
          body:JSON.stringify({kind,sessionId:sid,evidence:evidence.lines}),
          signal:controller.signal
        });
        let payload={};
        try{payload=await response.json();}catch(_){ }
        if(!response.ok||!payload||payload.ok!==true||!payload.summary){
          throw new Error(payload&&payload.error||`Summary failed (${response.status})`);
        }
        grokSummaryCache.set(key,{
          text:String(payload.summary).trim(),
          fingerprint:evidence.fingerprint,
          updated:new Date().toLocaleTimeString([], {hour:'numeric',minute:'2-digit'}),
          updatedAt:Date.now(),
          provider:String(payload.provider||'auto'),
          model:String(payload.model||'')
        });
        while(grokSummaryCache.size>40) grokSummaryCache.delete(grokSummaryCache.keys().next().value);
      }catch(error){
        const message=error&&error.name==='AbortError'?'Timed out':compact(error&&error.message||error||'Unavailable',120);
        grokSummaryErrors.set(key,message);
      }finally{
        clearTimeout(timer);
        grokSummaryRequests.delete(key);
        if(sid===sessionKey()){
          setSummaryButtonBusy(kind,false);
          renderGrokSummary(kind);
        }
      }
    })();
    grokSummaryRequests.set(key,request);
    renderGrokSummary(kind);
    return request;
  }

  function refreshDashboardStatus(){
    void refreshGrokSummary('status',{force:true});
  }

  function maybeAutoRefreshSummaries(options={}){
    const root=document.documentElement;
    if(!root||!root.dataset||root.dataset.sessionView==='classic'||document.hidden) return;
    const sid=sessionKey();
    if(!sid) return;
    const now=Date.now();
    const lastCheck=Number(grokSummaryAutoChecks.get(sid)||0);
    if(!options.forceCheck&&now-lastCheck<SUMMARY_AUTO_CHECK_MS) return;
    grokSummaryAutoChecks.set(sid,now);
    while(grokSummaryAutoChecks.size>40) grokSummaryAutoChecks.delete(grokSummaryAutoChecks.keys().next().value);
    for(const kind of ['goal','status']){
      const key=grokCacheKey(kind,sid);
      const record=grokSummaryCache.get(key);
      const evidence=grokEvidence(kind);
      if(!evidence.lines.length||grokSummaryRequests.has(key)) continue;
      if(!record){
        void refreshGrokSummary(kind);
        continue;
      }
      const changed=record.fingerprint!==evidence.fingerprint;
      const oldEnough=now-Number(record.updatedAt||0)>=SUMMARY_AUTO_REFRESH_FLOOR_MS;
      if(changed&&oldEnough) void refreshGrokSummary(kind);
    }
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
    const openingOffset=typeof _oldestIdx!=='undefined'?Number(_oldestIdx):0;
    const openingIsMissing=(typeof _messagesTruncated!=='undefined'&&!!_messagesTruncated)||(Number.isFinite(openingOffset)&&openingOffset>0);
    renderGrokSummary('goal');
    setMarkdown('sessionDashboardInstruction',dashboardInstruction(entries));
    setMarkdown('sessionDashboardCompleted',completed||'Not completed yet.');
    renderGrokSummary('status');
    const completedCard=byId('sessionDashboardCompletedCard');
    if(completedCard) completedCard.dataset.empty=completed?'0':'1';
    if(openingIsMissing&&!openingEvidenceCache.has(sessionKey())) void hydrateDashboardOpeningEvidence();
    maybeAutoRefreshSummaries();
  }

  function updateSessionViewToggle(){
    const toggle=byId('sessionViewToggle');
    if(!toggle||typeof toggle.setAttribute!=='function') return;
    const root=document.documentElement;
    const dashboard=!!(root&&root.dataset&&root.dataset.sessionView==='dashboard');
    if(typeof toggle.removeAttribute==='function'){
      toggle.removeAttribute('aria-pressed');
      toggle.removeAttribute('aria-checked');
    }
    const label=dashboard?'Switch to Classic view':'Switch to High Signal mode';
    toggle.textContent=label;
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
    const timer=setInterval(maybeAutoRefreshSummaries,SUMMARY_AUTO_CHECK_MS);
    if(timer&&typeof timer.unref==='function') timer.unref();
    document.addEventListener('visibilitychange',()=>{
      if(!document.hidden) maybeAutoRefreshSummaries({forceCheck:true});
    });
  };
  if(document.readyState==='loading') document.addEventListener('DOMContentLoaded',init,{once:true});
  else init();
})();
