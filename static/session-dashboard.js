/* HermesUI frontend-only session dashboard. The transcript remains intact. */
(function(){
  'use strict';
  if(window.__sessionDashboardInstalled) return;
  window.__sessionDashboardInstalled=true;

  const byId=id=>document.getElementById(id);
  const state=()=>typeof S!=='undefined'&&S?S:{session:null,messages:[],busy:false};
  const acceptedRunSteers=new Map();
  const latestSteerRunBySession=new Map();
  const messageEntryCache=new Map();
  const openingEvidenceCache=new Map();
  const openingEvidenceRequests=new Map();
  const promptEvidenceCache=new Map();
  const promptEvidenceRequests=new Map();
  const grokSummaryCache=new Map();
  const grokSummaryRequests=new Map();
  const grokSummaryErrors=new Map();
  const OPENING_EVIDENCE_LIMIT=30;
  const PROMPT_EVIDENCE_LIMIT=30;
  const PROMPT_EVIDENCE_MAX_PAGES=4;
  const GROK_SUMMARY_ENDPOINT='/apps/api/high-signal-summary';
  const SUMMARY_MODEL_TASK='high_signal_summary';
  let summaryModelConfig={provider:'',model:'',label:'AI model'};
  let summaryModelGroups=[];
  let summaryModelLoadPromise=null;
  let summaryModelLoaded=false;
  let summaryModelSaving=false;
  let summaryModelDropdown=null;
  let summaryModelAnchor=null;
  let summaryModelError='';
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
  function backgroundTriggerTaskId(message){
    if(!message) return '';
    const meta=message._wakeup_meta&&typeof message._wakeup_meta==='object'?message._wakeup_meta:{};
    const direct=[meta.task_id,meta.process_id,meta.delegation_id,meta.completion_id]
      .map(value=>String(value||'').trim())
      .find(value=>value.length>=4&&value.length<=200);
    if(direct) return direct;
    const text=rawText(message);
    const processMatch=text.match(/\b(proc_[A-Za-z0-9_-]+)\b/);
    if(processMatch) return processMatch[1];
    const delegationMatch=text.match(/^\s*\[ASYNC DELEGATION(?: BATCH)? COMPLETE\s*(?:—|-)\s*([^\]\s]+)/i);
    return delegationMatch?delegationMatch[1]:'';
  }
  function backgroundTriggerResumesUserRun(cached,message,index){
    const taskId=backgroundTriggerTaskId(message);
    const lastUserIdx=Number(cached&&cached.lastUserDirectedIdx);
    const messages=cached&&Array.isArray(cached.source)?cached.source:[];
    if(!taskId||!Number.isInteger(lastUserIdx)||lastUserIdx<0||index<=lastUserIdx) return false;
    const start=Math.max(lastUserIdx+1,index-600);
    for(let cursor=index-1;cursor>=start;cursor--){
      const prior=messages[cursor];
      if(prior&&prior.role==='tool'&&rawText(prior).includes(taskId)) return true;
    }
    return false;
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
        const resumesUserRun=backgroundTriggerResumesUserRun(cached,message,index);
        if(resumesUserRun){
          const boundary=latestMatchingEntry(cached.entries,entry=>entry.message.role==='assistant'&&!entry.intermediary&&rawText(entry.message));
          if(boundary) boundary.intermediary=true;
          cached.backgroundUpdateActive=false;
          cached.backgroundResumeBoundary=null;
          cached.userDirectedRunOpen=true;
          return;
        }
        cached.backgroundUpdateActive=!cached.userDirectedRunOpen;
        cached.backgroundResumeBoundary=cached.backgroundUpdateActive
          ? latestMatchingEntry(cached.entries,entry=>entry.message.role==='assistant'&&!entry.intermediary&&rawText(entry.message))
          : null;
        return;
      }
      cached.backgroundUpdateActive=false;
      cached.backgroundResumeBoundary=null;
      cached.userDirectedRunOpen=true;
      cached.lastUserDirectedIdx=index;
    }
    if(cached.backgroundUpdateActive){
      if(message&&message.role==='assistant'&&assistantContinuesUserDirectedTurn(message)){
        // A wakeup can resume the user's unfinished turn after an earlier
        // progress-only assistant message closed our local run heuristic. Tool
        // work is proof that this is an active continuation, not a standalone
        // background note. Reopen the turn so its eventual final answer becomes
        // the High Signal Result instead of disappearing with the wakeup row.
        cached.backgroundUpdateActive=false;
        cached.userDirectedRunOpen=true;
        if(cached.backgroundResumeBoundary) cached.backgroundResumeBoundary.intermediary=true;
        cached.backgroundResumeBoundary=null;
      }else{
        if(message&&message.role==='assistant'){
          cached.backgroundUpdateActive=false;
          cached.backgroundResumeBoundary=null;
        }
        return;
      }
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
    const cached={source:messages,length:0,entries:[],firstUser:null,firstSignature:'',tailSignature:'',backgroundUpdateActive:false,backgroundResumeBoundary:null,userDirectedRunOpen:false,lastUserDirectedIdx:-1};
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
        cached.source=messages;
        for(let index=cached.length;index<messages.length;index++) appendMessageEntry(cached,messages[index],index);
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
  const enhanceMarkdown=element=>{
    if(!element) return;
    if(typeof highlightCode==='function') highlightCode(element);
    if(typeof addCopyButtons==='function') addCopyButtons(element);
  };
  const markdownHtml=text=>typeof renderMd==='function'?renderMd(String(text||'')):String(text||'');
  const setMarkdown=(id,text)=>{
    const element=byId(id);
    if(!element) return;
    if(typeof renderMd==='function') element.innerHTML=renderMd(String(text||''));
    else element.textContent=String(text||'');
    enhanceMarkdown(element);
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
          && !entry.intermediary
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

  function acceptedSteersForInstruction(baseText){
    const current=state();
    const session=current.session||{};
    const sid=String(session.session_id||'').trim();
    if(!sid) return [];
    if(current.busy||current.activeStreamId){
      const key=activeRunKey();
      return key&&acceptedRunSteers.has(key)?acceptedRunSteers.get(key):[];
    }
    const latest=latestSteerRunBySession.get(sid);
    if(!latest||latest.baseText!==baseText) return [];
    return acceptedRunSteers.get(latest.key)||[];
  }

  function dashboardInstruction(entries,resultAnchor=''){
    const runUsers=latestRunUserEntries(entries);
    let text=runUsers.length?cleanUserText(runUsers[runUsers.length-1].message):'';
    let pending=false;
    if(!text&&resultAnchor){
      const evidence=promptEvidenceCache.get(sessionKey());
      if(evidence&&evidence.anchor===resultAnchor){
        if(evidence.text) text=evidence.text;
        else if(evidence.pending) pending=true;
      }
    }
    const empty=!text&&!pending;
    if(!text) text=pending?'Loading the last prompt…':'No prompt is available yet.';
    return {text,pending,empty,steers:acceptedSteersForInstruction(text)};
  }

  function updateDashboardLoadEarlier(instruction){
    const button=byId('sessionDashboardLoadEarlier');
    if(!button) return;
    const before=typeof _oldestIdx!=='undefined'?Number(_oldestIdx):0;
    const hasOlder=typeof _messagesTruncated!=='undefined'&&!!_messagesTruncated&&Number.isFinite(before)&&before>0;
    const loading=typeof _loadingOlder!=='undefined'&&!!_loadingOlder;
    const visible=!!(instruction&&instruction.empty&&hasOlder);
    button.hidden=!visible;
    button.disabled=visible&&loading;
    button.textContent=loading
      ? 'Loading earlier messages…'
      : (hasOlder?`Load earlier messages (${before} older)`:'Load earlier messages');
  }

  function renderDashboardInstruction(entries,resultAnchor=''){
    const element=byId('sessionDashboardInstruction');
    if(!element) return;
    const instruction=dashboardInstruction(entries,resultAnchor);
    updateDashboardLoadEarlier(instruction);
    if(!instruction.steers.length){
      setMarkdown('sessionDashboardInstruction',instruction.text);
      return;
    }
    const cards=instruction.steers.map((steer,index)=>(
      `<article class="session-dashboard-steer"><div class="session-dashboard-steer-label">Steer ${index+1}</div><div class="session-dashboard-steer-copy">${markdownHtml(steer)}</div></article>`
    )).join('');
    element.innerHTML=`<div class="session-dashboard-instruction-copy">${markdownHtml(instruction.text)}</div><div class="session-dashboard-steers" aria-label="Accepted steers">${cards}</div>`;
    enhanceMarkdown(element);
  }

  async function loadEarlierDashboardMessages(){
    if(typeof _loadOlderMessages!=='function') return;
    const button=byId('sessionDashboardLoadEarlier');
    if(button){
      button.disabled=true;
      button.textContent='Loading earlier messages…';
    }
    try{
      await _loadOlderMessages();
    }finally{
      scheduleSessionDashboardSync();
    }
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

  async function hydrateDashboardPromptEvidence(resultAnchor){
    const key=sessionKey();
    if(!key||!resultAnchor||typeof api!=='function') return;
    const cached=promptEvidenceCache.get(key);
    if(cached&&cached.anchor===resultAnchor) return;
    if(promptEvidenceRequests.has(key)) return promptEvidenceRequests.get(key);
    let before=typeof _oldestIdx!=='undefined'?Number(_oldestIdx):0;
    if(!Number.isFinite(before)||before<=0){
      promptEvidenceCache.set(key,{anchor:resultAnchor,pending:false,text:'',error:'missing'});
      return;
    }
    promptEvidenceCache.set(key,{anchor:resultAnchor,pending:true,text:'',error:''});
    if(key===sessionKey()) scheduleSessionDashboardSync();
    const request=(async()=>{
      let text='';
      let error='missing';
      let pages=0;
      try{
        while(before>0&&!text&&pages<PROMPT_EVIDENCE_MAX_PAGES){
          pages+=1;
          const data=await api(`/api/session?session_id=${encodeURIComponent(key)}&messages=1&resolve_model=0&msg_before=${before}&msg_limit=${PROMPT_EVIDENCE_LIMIT}`,{timeoutMs:120000});
          const session=data&&data.session?data.session:data;
          const messages=session&&Array.isArray(session.messages)?session.messages:[];
          const projection=rebuildProjection(messages);
          const user=latestUserEntry(projection.entries);
          text=user?cleanUserText(user.message):'';
          if(text){error='';break;}
          const nextBefore=Number(session&&session._messages_offset);
          if(!Number.isFinite(nextBefore)||nextBefore<=0||nextBefore>=before) break;
          before=nextBefore;
        }
      }catch(fetchError){
        error=String(fetchError&&fetchError.message||fetchError||'unavailable');
      }finally{
        promptEvidenceCache.set(key,{anchor:resultAnchor,pending:false,text,error:text?'':error});
        while(promptEvidenceCache.size>20) promptEvidenceCache.delete(promptEvidenceCache.keys().next().value);
        promptEvidenceRequests.delete(key);
        if(key===sessionKey()) scheduleSessionDashboardSync();
      }
    })();
    promptEvidenceRequests.set(key,request);
    return request;
  }

  function refreshDashboardSummary(){
    void refreshGrokSummary('goal');
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

  function completedAssistantEntry(entries){
    const current=state();
    if(current.busy||current.activeStreamId) return undefined;
    const user=latestUserEntry(entries);
    const assistant=latestAssistantEntry(entries);
    if(!assistant||user&&assistant.index<user.index) return undefined;
    return assistant;
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
        if(message.role==='assistant'&&assistantContinuesUserDirectedTurn(message)){
          backgroundActive=false;
          userDirectedRunOpen=true;
        }else{
          if(message.role==='assistant') backgroundActive=false;
          continue;
        }
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

  function summaryModelControls(){
    if(typeof document.querySelectorAll!=='function') return [];
    return Array.from(document.querySelectorAll('[data-high-signal-model]'));
  }

  function summaryModelToken(model){
    return String(model||'').trim().replace(/^@[^:]+:/,'');
  }

  function prettySummaryModelLabel(model){
    const value=summaryModelToken(model);
    if(!value) return 'Auto';
    return value.split('-').map(part=>{
      if(/^gpt$/i.test(part)) return 'GPT';
      if(/^ai$/i.test(part)) return 'AI';
      if(/^sol$/i.test(part)) return 'SOL';
      if(/^pro$/i.test(part)) return 'PRO';
      if(/^\d+(?:\.\d+)*$/.test(part)) return part;
      return part.charAt(0).toUpperCase()+part.slice(1);
    }).join(' ');
  }

  function summaryModelMatches(provider,model,candidateProvider,candidateModel){
    return String(provider||'auto')===String(candidateProvider||'auto')
      && summaryModelToken(model)===summaryModelToken(candidateModel);
  }

  function summaryModelCatalogLabel(provider,model){
    for(const group of summaryModelGroups){
      if(String(group.providerId)!==String(provider)) continue;
      const found=group.models.find(item=>summaryModelMatches(provider,model,group.providerId,item.id));
      if(found) return String(found.label||prettySummaryModelLabel(model));
    }
    return String(provider||'auto')==='auto'&&!model?'Auto':prettySummaryModelLabel(model);
  }

  function syncSummaryModelControls(){
    const label=summaryModelSaving?'Saving…':String(summaryModelConfig.label||summaryModelCatalogLabel(summaryModelConfig.provider,summaryModelConfig.model));
    const blocked=summaryModelSaving||grokSummaryRequests.size>0;
    summaryModelControls().forEach(button=>{
      const target=button.querySelector&&button.querySelector('[data-high-signal-model-label]');
      if(target) target.textContent=label;
      button.disabled=blocked;
      button.title=summaryModelError||`${label} · Goal and Status model`;
      button.setAttribute('aria-expanded',String(button===summaryModelAnchor&&!!summaryModelDropdown&&summaryModelDropdown.classList.contains('open')));
    });
  }

  function summaryModelIsTextCapable(item){
    const value=`${item&&item.id||''} ${item&&item.label||''}`.toLowerCase();
    return !/(?:image|video|embedding|whisper|speech|audio|tts)/.test(value);
  }

  function normalizeSummaryModelGroups(payload){
    return (Array.isArray(payload&&payload.groups)?payload.groups:[]).map(group=>({
      providerId:String(group.provider_id||group.provider||''),
      provider:String(group.provider||group.provider_id||''),
      models:[...(group.models||[]),...(group.extra_models||[])]
        .filter(summaryModelIsTextCapable)
        .map(model=>({id:String(model.id||''),label:String(model.label||prettySummaryModelLabel(model.id))}))
        .filter(model=>model.id)
    })).filter(group=>group.providerId&&group.models.length);
  }

  function ensureConfiguredSummaryModelVisible(){
    const provider=String(summaryModelConfig.provider||'auto');
    const model=String(summaryModelConfig.model||'');
    if(provider==='auto'&&!model) return;
    let group=summaryModelGroups.find(item=>item.providerId===provider);
    if(!group){
      group={providerId:provider,provider,models:[]};
      summaryModelGroups.push(group);
    }
    if(!group.models.some(item=>summaryModelMatches(provider,model,provider,item.id))){
      group.models.unshift({id:model,label:prettySummaryModelLabel(model)});
    }
  }

  async function loadSummaryModelConfig({force=false}={}){
    if(summaryModelLoaded&&!force) return summaryModelConfig;
    if(summaryModelLoadPromise&&!force) return summaryModelLoadPromise;
    summaryModelLoadPromise=(async()=>{
      try{
        if(typeof api!=='function') throw new Error('Model selector unavailable');
        const [auxiliary,catalog]=await Promise.all([
          api('/api/model/auxiliary'),
          api('/api/models')
        ]);
        summaryModelGroups=normalizeSummaryModelGroups(catalog);
        const task=(Array.isArray(auxiliary&&auxiliary.tasks)?auxiliary.tasks:[]).find(item=>item&&item.task===SUMMARY_MODEL_TASK)||{};
        summaryModelConfig={provider:String(task.provider||'auto'),model:String(task.model||''),label:''};
        ensureConfiguredSummaryModelVisible();
        summaryModelConfig.label=summaryModelCatalogLabel(summaryModelConfig.provider,summaryModelConfig.model);
        summaryModelLoaded=true;
        summaryModelError='';
      }catch(error){
        summaryModelLoaded=false;
        summaryModelError=compact(error&&error.message||'Model selector unavailable',100);
      }finally{
        syncSummaryModelControls();
      }
      return summaryModelConfig;
    })();
    try{return await summaryModelLoadPromise;}
    finally{summaryModelLoadPromise=null;}
  }

  function closeSummaryModelDropdown(){
    if(summaryModelDropdown) summaryModelDropdown.classList.remove('open');
    summaryModelControls().forEach(button=>button.setAttribute('aria-expanded','false'));
    summaryModelAnchor=null;
  }

  function positionSummaryModelDropdown(anchor){
    if(!summaryModelDropdown||!anchor||typeof anchor.getBoundingClientRect!=='function') return;
    const margin=8;
    const gap=6;
    const rect=anchor.getBoundingClientRect();
    const visual=window.visualViewport;
    const viewportLeft=Number(visual&&visual.offsetLeft)||0;
    const viewportTop=Number(visual&&visual.offsetTop)||0;
    const viewportWidth=Math.max(0,Number(visual&&visual.width)||window.innerWidth);
    const viewportHeight=Math.max(0,Number(visual&&visual.height)||window.innerHeight);
    const viewportRight=viewportLeft+viewportWidth;
    const viewportBottom=viewportTop+viewportHeight;
    let leftEdge=viewportLeft+margin;
    const rightEdge=viewportRight-margin;
    if(viewportWidth<=640){
      const rail=document.querySelector('.tailnet-app-rail');
      const railRect=rail&&typeof rail.getBoundingClientRect==='function'?rail.getBoundingClientRect():null;
      if(railRect&&railRect.width>0&&railRect.right>viewportLeft&&railRect.left<viewportRight){
        leftEdge=Math.min(rightEdge,Math.max(leftEdge,railRect.right+margin));
      }
    }
    const availableWidth=Math.max(0,rightEdge-leftEdge);
    const width=Math.min(320,availableWidth);
    const left=viewportWidth<=640
      ? leftEdge
      : Math.max(leftEdge,Math.min(rect.right-width,rightEdge-width));
    summaryModelDropdown.style.width=`${width}px`;
    summaryModelDropdown.style.left=`${left}px`;

    const topEdge=viewportTop+margin;
    const bottomEdge=viewportBottom-margin;
    const availableBelow=Math.max(0,bottomEdge-(rect.bottom+gap));
    const availableAbove=Math.max(0,(rect.top-gap)-topEdge);
    const naturalHeight=Math.min(440,summaryModelDropdown.scrollHeight||440);
    const openAbove=naturalHeight>availableBelow&&availableAbove>availableBelow;
    const availableHeight=openAbove?availableAbove:availableBelow;
    const maxHeight=Math.min(440,availableHeight);
    summaryModelDropdown.style.maxHeight=`${maxHeight}px`;
    const renderedHeight=Math.min(naturalHeight,maxHeight);
    const top=openAbove
      ? Math.max(topEdge,rect.top-gap-renderedHeight)
      : Math.min(rect.bottom+gap,bottomEdge-renderedHeight);
    summaryModelDropdown.style.top=`${Math.max(topEdge,top)}px`;
  }

  function summaryModelOption(provider,model,label,providerLabel){
    const option=document.createElement('div');
    const active=summaryModelMatches(summaryModelConfig.provider,summaryModelConfig.model,provider,model);
    option.className=`model-opt${active?' active':''}`;
    option.tabIndex=0;
    option.setAttribute('role','option');
    option.setAttribute('aria-selected',String(active));
    const top=document.createElement('span');
    top.className='model-opt-top';
    const name=document.createElement('span');
    name.className='model-opt-name';
    name.textContent=label;
    top.appendChild(name);
    if(providerLabel){
      const providerChip=document.createElement('span');
      providerChip.className='model-opt-provider';
      providerChip.textContent=providerLabel;
      top.appendChild(providerChip);
    }
    option.appendChild(top);
    const select=()=>void saveSummaryModel(provider,model,label);
    option.addEventListener('click',select);
    option.addEventListener('keydown',event=>{
      if(event.key==='Enter'||event.key===' '){event.preventDefault();select();}
    });
    return option;
  }

  function renderSummaryModelDropdown(){
    if(!summaryModelDropdown){
      summaryModelDropdown=document.createElement('div');
      summaryModelDropdown.id='sessionDashboardModelDropdown';
      summaryModelDropdown.className='model-dropdown model-dropdown--floating session-dashboard-model-dropdown';
      summaryModelDropdown.setAttribute('role','listbox');
      summaryModelDropdown.setAttribute('aria-label','Goal and Status model');
      document.body.appendChild(summaryModelDropdown);
    }
    summaryModelDropdown.replaceChildren();
    const note=document.createElement('div');
    note.className='model-scope-note';
    note.textContent=summaryModelError||'Shared by Goal and Status everywhere';
    summaryModelDropdown.appendChild(note);
    summaryModelDropdown.appendChild(summaryModelOption('auto','','Auto','Hermes'));
    summaryModelGroups.forEach(group=>{
      const heading=document.createElement('div');
      heading.className='model-group';
      heading.textContent=group.provider;
      summaryModelDropdown.appendChild(heading);
      group.models.forEach(model=>summaryModelDropdown.appendChild(summaryModelOption(group.providerId,model.id,model.label,group.provider)));
    });
  }

  async function saveSummaryModel(provider,model,label){
    if(summaryModelSaving||grokSummaryRequests.size) return;
    if(summaryModelMatches(summaryModelConfig.provider,summaryModelConfig.model,provider,model)){
      closeSummaryModelDropdown();
      return;
    }
    summaryModelSaving=true;
    summaryModelError='';
    syncSummaryModelControls();
    try{
      if(typeof api!=='function') throw new Error('Model selector unavailable');
      await api('/api/model/set',{
        method:'POST',
        body:JSON.stringify({scope:'auxiliary',task:SUMMARY_MODEL_TASK,provider,model})
      });
      summaryModelConfig={provider:String(provider||'auto'),model:String(model||''),label:String(label||prettySummaryModelLabel(model))};
      summaryModelLoaded=true;
      grokSummaryCache.clear();
      grokSummaryErrors.clear();
      closeSummaryModelDropdown();
      renderGrokSummary('goal');
      renderGrokSummary('status');
      window.dispatchEvent(new CustomEvent('hermesui:high-signal-model-changed',{detail:{provider:summaryModelConfig.provider,model:summaryModelConfig.model,label:summaryModelConfig.label}}));
      if(typeof window._loadAuxiliaryModels==='function') void window._loadAuxiliaryModels();
    }catch(error){
      summaryModelError=compact(error&&error.message||'Model change failed',100);
      renderSummaryModelDropdown();
      if(summaryModelAnchor) positionSummaryModelDropdown(summaryModelAnchor);
    }finally{
      summaryModelSaving=false;
      syncSummaryModelControls();
    }
  }

  async function toggleSummaryModelDropdown(event){
    const anchor=event&&event.currentTarget;
    if(!anchor||summaryModelSaving||grokSummaryRequests.size) return;
    event.preventDefault();
    event.stopPropagation();
    if(summaryModelAnchor===anchor&&summaryModelDropdown&&summaryModelDropdown.classList.contains('open')){
      closeSummaryModelDropdown();
      return;
    }
    summaryModelAnchor=anchor;
    await loadSummaryModelConfig();
    renderSummaryModelDropdown();
    summaryModelDropdown.classList.add('open');
    summaryModelControls().forEach(button=>button.setAttribute('aria-expanded',String(button===anchor)));
    positionSummaryModelDropdown(anchor);
  }

  function applyExternalSummaryModel(detail){
    if(!detail||summaryModelSaving) return;
    const provider=String(detail.provider||'auto');
    const model=String(detail.model||'');
    summaryModelConfig={provider,model,label:String(detail.label||summaryModelCatalogLabel(provider,model))};
    summaryModelLoaded=true;
    ensureConfiguredSummaryModelVisible();
    grokSummaryCache.clear();
    grokSummaryErrors.clear();
    closeSummaryModelDropdown();
    syncSummaryModelControls();
    renderGrokSummary('goal');
    renderGrokSummary('status');
  }

  function summaryRelativeTime(updatedAt){
    const elapsed=Math.max(0,Math.floor((Date.now()-Number(updatedAt))/1000));
    if(!Number.isFinite(elapsed)) return '';
    if(elapsed<60) return 'now';
    if(elapsed<3600) return `${Math.floor(elapsed/60)}m ago`;
    if(elapsed<86400) return `${Math.floor(elapsed/3600)}h ago`;
    return `${Math.floor(elapsed/86400)}d ago`;
  }

  function renderGrokSummary(kind){
    const sid=sessionKey();
    const key=grokCacheKey(kind,sid);
    const record=grokSummaryCache.get(key);
    const error=grokSummaryErrors.get(key);
    const targetId=kind==='goal'?'sessionDashboardOriginalRequest':'sessionDashboardStatus';
    const metaId=kind==='goal'?'sessionDashboardSummaryUpdated':'sessionDashboardUpdated';
    const emptyText=kind==='goal'
      ? 'Select Refresh to generate the goal summary.'
      : 'Select Refresh to generate the current status.';
    const currentEvidence=record?grokEvidence(kind):null;
    const stale=Boolean(record&&record.fingerprint&&currentEvidence&&record.fingerprint!==currentEvidence.fingerprint);
    setMarkdown(targetId,record&&record.text?record.text:error?`Could not refresh: ${error}`:emptyText);
    const target=byId(targetId);
    if(target){
      target.dataset.summaryState=record&&record.text?(stale?'stale':'current'):(error?'error':'empty');
    }
    const updated=byId(metaId);
    if(updated){
      const relative=record&&record.updatedAt?summaryRelativeTime(record.updatedAt):'';
      updated.textContent=relative?`· ${relative}${stale?' · stale':''}`:'';
      updated.dataset.stale=stale?'1':'0';
      updated.title=stale?'The session has advanced since this summary was refreshed.':'';
      updated.hidden=!relative;
    }
  }

  function setSummaryButtonBusy(kind,busy){
    const button=byId(kind==='goal'?'sessionDashboardSummaryRefresh':'sessionDashboardRefresh');
    if(!button) return;
    button.disabled=!!busy;
    button.setAttribute('aria-busy',busy?'true':'false');
    button.textContent=busy?'Updating…':'Refresh';
    syncSummaryModelControls();
  }

  async function refreshGrokSummary(kind){
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
    void refreshGrokSummary('status');
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

    const completedEntry=completedAssistantEntry(entries);
    const completed=completedEntry?compact(rawText(completedEntry.message),12000):'';
    const resultAnchor=completedEntry?messageSignature(completedEntry.message):'';
    const promptMissing=!!completed&&!latestRunUserEntries(entries).length;
    if(promptMissing) void hydrateDashboardPromptEvidence(resultAnchor);
    renderGrokSummary('goal');
    renderDashboardInstruction(entries,resultAnchor);
    setMarkdown('sessionDashboardCompleted',completed||'Not completed yet.');
    renderGrokSummary('status');
    const completedCard=byId('sessionDashboardCompletedCard');
    if(completedCard) completedCard.dataset.empty=completed?'0':'1';

  }

  function updateSessionViewToggle(){
    const toggle=byId('sessionViewToggle');
    if(!toggle||typeof toggle.setAttribute!=='function') return;
    const root=document.documentElement;
    const dashboard=!!(root&&root.dataset&&root.dataset.sessionView==='dashboard');
    const label=dashboard?'Switch to Classic view':'Switch to High Signal mode';
    toggle.setAttribute('aria-label',label);
    toggle.setAttribute('aria-pressed',dashboard?'true':'false');
    toggle.setAttribute('data-tooltip',label);
    toggle.dataset.targetView=dashboard?'classic':'dashboard';
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
    const runUsers=latestRunUserEntries(sessionMessages());
    const baseText=runUsers.length?cleanUserText(runUsers[runUsers.length-1].message):'';
    latestSteerRunBySession.set(sid,{key,baseText});
    while(acceptedRunSteers.size>20) acceptedRunSteers.delete(acceptedRunSteers.keys().next().value);
    while(latestSteerRunBySession.size>20) latestSteerRunBySession.delete(latestSteerRunBySession.keys().next().value);
    scheduleSessionDashboardSync();
  };
  ['renderMessages','setBusy','syncTopbar'].forEach(wrapAfter);

  const init=()=>{
    const refresh=byId('sessionDashboardRefresh');
    if(refresh) refresh.addEventListener('click',refreshDashboardStatus);
    const summaryRefresh=byId('sessionDashboardSummaryRefresh');
    if(summaryRefresh) summaryRefresh.addEventListener('click',refreshDashboardSummary);
    const loadEarlier=byId('sessionDashboardLoadEarlier');
    if(loadEarlier) loadEarlier.addEventListener('click',()=>{void loadEarlierDashboardMessages();});
    const controls=summaryModelControls();
    controls.forEach(button=>button.addEventListener('click',toggleSummaryModelDropdown));
    if(controls.length){
      void loadSummaryModelConfig();
      document.addEventListener('pointerdown',event=>{
        if(summaryModelDropdown&&summaryModelDropdown.classList.contains('open')&&!summaryModelDropdown.contains(event.target)&&!controls.includes(event.target)&&!controls.some(button=>button.contains(event.target))) closeSummaryModelDropdown();
      });
      document.addEventListener('keydown',event=>{if(event.key==='Escape') closeSummaryModelDropdown();});
      window.addEventListener('resize',closeSummaryModelDropdown);
      window.addEventListener('hermesui:high-signal-model-changed',event=>applyExternalSummaryModel(event.detail));
    }
    syncSessionDashboard();
  };
  if(document.readyState==='loading') document.addEventListener('DOMContentLoaded',init,{once:true});
  else init();
})();
