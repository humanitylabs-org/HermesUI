(function(root){
  'use strict';

  const textOf=message=>{
    if(!message) return '';
    if(typeof root.msgContent==='function') return String(root.msgContent(message)||'');
    const value=message.content;
    if(typeof value==='string') return value;
    if(Array.isArray(value)) return value.map(part=>{
      if(!part) return '';
      if(typeof part==='string') return part;
      return typeof part.text==='string'?part.text:'';
    }).join('');
    return value==null?'':String(value);
  };

  const roleOf=message=>String(message&&message.role||'').toLowerCase();

  const controlTextOf=message=>{
    const text=textOf(message);
    if(typeof root._stripWorkspaceDisplayPrefix==='function'){
      return String(root._stripWorkspaceDisplayPrefix(text)||'').trim();
    }
    return String(text||'').replace(/^\s*\[Workspace(?:::[^\]]*|:[^\]]*)\]\s*/i,'').trim();
  };

  const isBackgroundTrigger=message=>{
    if(!message||roleOf(message)!=='user') return false;
    if(typeof root._isBackgroundUpdateTriggerMessage==='function'){
      return !!root._isBackgroundUpdateTriggerMessage(message);
    }
    if(message._source==='process_wakeup'||message._source==='async_delegation') return true;
    const text=controlTextOf(message);
    return /^\s*\[ASYNC DELEGATION(?: BATCH)? COMPLETE(?:\s*(?:—|-)\s*[^\]]*)?\]/i.test(text)
      || /^\s*\[IMPORTANT:\s*Background process\b/i.test(text)
      || /^\s*\[BACKGROUND WAKEUP\b/i.test(text);
  };

  const isSystemControl=message=>{
    if(!message||roleOf(message)!=='user') return false;
    if(isBackgroundTrigger(message)||message.recovery_control===true) return true;
    if(typeof root._isContextCompactionMessage==='function'&&root._isContextCompactionMessage(message)) return true;
    if(typeof root._isPreservedCompressionTaskListMessage==='function'&&root._isPreservedCompressionTaskListMessage(message)) return true;
    if(typeof root._isRecoveryControlMessage==='function'&&root._isRecoveryControlMessage(message)) return true;
    return false;
  };

  const isRenderable=message=>{
    if(!message||!['user','assistant'].includes(roleOf(message))) return false;
    if(message._latest_turn_gap) return true;
    if(isSystemControl(message)) return false;
    if(typeof root._messageIsRenderable==='function') return !!root._messageIsRenderable(message);
    if(textOf(message).trim()) return true;
    return roleOf(message)==='assistant'&&(
      Array.isArray(message.tool_calls)&&message.tool_calls.length
      || Array.isArray(message._partial_tool_calls)&&message._partial_tool_calls.length
    );
  };

  const assistantContinues=message=>{
    if(!message||roleOf(message)!=='assistant') return false;
    if(message._latest_turn_gap) return true;
    if(typeof root._assistantMessageHasToolCall==='function'&&root._assistantMessageHasToolCall(message)) return true;
    if(Array.isArray(message.tool_calls)&&message.tool_calls.length) return true;
    if(Array.isArray(message._partial_tool_calls)&&message._partial_tool_calls.length) return true;
    if(Array.isArray(message.content)&&message.content.some(part=>part&&part.type==='tool_use')) return true;
    return String(message.finish_reason||'').toLowerCase()==='tool_calls';
  };

  // Legacy histories do not carry an explicit interim/final bit. Keep this
  // deliberately narrow: only short, future-facing wait/progress prose may be
  // resumed by a task-linked wakeup. A completed report stays final even when
  // it launched independent QA earlier in the same human turn.
  const assistantLooksInterim=message=>{
    if(!message||roleOf(message)!=='assistant') return false;
    if(message._interim===true||message.interim===true||message._live===true) return true;
    const text=textOf(message).replace(/\s+/g,' ').trim();
    if(!text||text.length>800) return false;
    return /\b(?:is|are|am)\s+still\s+(?:running|working|processing|waiting|verifying|deploying)\b/i.test(text)
      || /\b(?:is|are)\s+(?:currently\s+)?(?:in progress|pending)\b/i.test(text)
      || /\bwaiting for\b/i.test(text)
      || /\bI(?:'ll| will)\b.{0,120}\b(?:when|once|after)\b/i.test(text);
  };

  const triggerTaskId=message=>{
    if(typeof root._backgroundUpdateTriggerTaskId==='function'){
      return String(root._backgroundUpdateTriggerTaskId(message)||'');
    }
    const meta=message&&message._wakeup_meta&&typeof message._wakeup_meta==='object'?message._wakeup_meta:{};
    const direct=[meta.task_id,meta.process_id,meta.delegation_id,meta.completion_id]
      .map(value=>String(value||'').trim())
      .find(value=>value.length>=4&&value.length<=200);
    if(direct) return direct;
    const text=controlTextOf(message);
    const processMatch=text.match(/\b(proc_[A-Za-z0-9_-]+)\b/);
    if(processMatch) return processMatch[1];
    const delegationMatch=text.match(/^\s*\[ASYNC DELEGATION(?: BATCH)? COMPLETE\s*(?:—|-)\s*([^\]\s]+)/i);
    return delegationMatch?delegationMatch[1]:'';
  };

  const toolTaskIds=message=>{
    const ids=new Set();
    if(!message||roleOf(message)!=='tool') return ids;
    const meta=message._wakeup_meta&&typeof message._wakeup_meta==='object'?message._wakeup_meta:{};
    for(const value of [meta.task_id,meta.process_id,meta.delegation_id,meta.completion_id]){
      const candidate=String(value||'').trim();
      if(candidate.length>=4&&candidate.length<=200) ids.add(candidate);
    }
    const matches=textOf(message).match(/\b[A-Za-z0-9][A-Za-z0-9_-]{3,199}\b/g)||[];
    for(const candidate of matches){
      if(candidate.includes('_')||candidate.includes('-')||/^[A-Fa-f0-9]{8,64}$/.test(candidate)) ids.add(candidate);
    }
    return ids;
  };

  const assistantReferencesTask=(message,taskId)=>{
    if(!taskId) return false;
    if(typeof root._assistantMessageReferencesTaskId==='function'){
      return !!root._assistantMessageReferencesTaskId(message,taskId);
    }
    const meta=message&&message._wakeup_meta&&typeof message._wakeup_meta==='object'?message._wakeup_meta:{};
    if([meta.task_id,meta.process_id,meta.delegation_id,meta.completion_id]
      .some(value=>String(value||'')===taskId)) return true;
    return textOf(message).includes(taskId);
  };

  const triggerResumesHumanTurn=(state,source,index,taskId)=>{
    if(source[index]&&source[index]._display_resumes_human_turn===true) return true;
    if(!taskId||!Number.isInteger(state.lastHumanIdx)||state.lastHumanIdx<0||index<=state.lastHumanIdx) return false;
    return state.linkedTaskIds.has(taskId);
  };

  const createState=()=>({
    turnId:0,
    lastHumanIdx:-1,
    humanRunOpen:false,
    backgroundActive:false,
    backgroundTaskId:'',
    backgroundCanResumePrimary:false,
    lastPrimaryAssistant:null,
    lastPrimaryAssistantLooksInterim:false,
    linkedTaskIds:new Set(),
  });

  const append=(state,source,index)=>{
    const message=source[index];
    if(!message) return null;
    const role=roleOf(message);
    if(role==='tool'){
      for(const taskId of toolTaskIds(message)) state.linkedTaskIds.add(taskId);
      return null;
    }

    // A server-created omission marker is display-only. It must not advance or
    // reopen the assistant state machine: doing so would demote an already
    // completed primary answer and cause a later independent update to appear
    // as that turn's final answer.
    if(message._latest_turn_gap){
      return {
        message,rawIdx:index,visible:true,boundary:false,
        semanticType:'assistant_interim',backgroundUpdate:false,turnId:state.turnId,
      };
    }

    const explicitSemanticType=String(message._display_semantic_type||'');
    if(role==='assistant'&&['assistant_interim','assistant_final','async_update'].includes(explicitSemanticType)){
      const backgroundUpdate=message._display_background_update===true||explicitSemanticType==='async_update';
      const entry={
        message,rawIdx:index,
        visible:explicitSemanticType==='async_update'
          ? isRenderable(message)&&!!(textOf(message).trim()||message.attachments?.length||message._statusCard)
          : isRenderable(message),
        boundary:false,semanticType:explicitSemanticType,backgroundUpdate,turnId:state.turnId,
      };
      if(explicitSemanticType!=='async_update'){
        state.lastPrimaryAssistant=entry;
        state.lastPrimaryAssistantLooksInterim=explicitSemanticType==='assistant_interim';
        state.humanRunOpen=explicitSemanticType==='assistant_interim';
        state.backgroundActive=false;
      }else{
        state.backgroundActive=false;
        state.humanRunOpen=false;
      }
      return entry;
    }

    if(role==='user'&&isBackgroundTrigger(message)){
      const taskId=triggerTaskId(message);
      const canResume=!!state.lastPrimaryAssistant&&!!state.lastPrimaryAssistantLooksInterim;
      const resumes=canResume&&triggerResumesHumanTurn(state,source,index,taskId);
      if(resumes){
        if(state.lastPrimaryAssistant) state.lastPrimaryAssistant.semanticType='assistant_interim';
        state.humanRunOpen=true;
        state.backgroundActive=false;
      }else{
        state.backgroundActive=!state.humanRunOpen;
      }
      state.backgroundTaskId=taskId;
      state.backgroundCanResumePrimary=canResume;
      return {
        message,rawIdx:index,visible:false,boundary:true,
        semanticType:'system_control',backgroundUpdate:state.backgroundActive,
        resumesHumanTurn:resumes,
      };
    }

    if(role==='user'){
      if(isSystemControl(message)){
        return {message,rawIdx:index,visible:false,boundary:true,semanticType:'system_control',backgroundUpdate:false};
      }
      const previousHuman=(state.lastHumanIdx===index-1)?source[state.lastHumanIdx]:null;
      if(
        previousHuman
        && typeof root._isSerializedMultimodalShadow==='function'
        && root._isSerializedMultimodalShadow(message,previousHuman)
      ){
        return {
          message,rawIdx:index,visible:false,boundary:false,
          semanticType:'system_control',backgroundUpdate:false,turnId:state.turnId,
        };
      }
      state.turnId+=1;
      state.lastHumanIdx=index;
      state.humanRunOpen=true;
      state.backgroundActive=false;
      state.backgroundTaskId='';
      state.backgroundCanResumePrimary=false;
      state.lastPrimaryAssistant=null;
      state.lastPrimaryAssistantLooksInterim=false;
      state.linkedTaskIds.clear();
      return {
        message,rawIdx:index,visible:isRenderable(message),boundary:true,
        semanticType:'human_prompt',backgroundUpdate:false,turnId:state.turnId,
      };
    }

    if(role!=='assistant') return null;

    if(state.backgroundActive){
      const resumes=state.backgroundCanResumePrimary&&assistantReferencesTask(message,state.backgroundTaskId);
      if(resumes){
        state.backgroundActive=false;
        state.humanRunOpen=true;
      }else{
        const entry={
          message,rawIdx:index,
          visible:isRenderable(message)&&!!(textOf(message).trim()||message.attachments?.length||message._statusCard),
          boundary:false,semanticType:'async_update',backgroundUpdate:true,turnId:state.turnId,
        };
        if(!assistantContinues(message)){
          state.backgroundActive=false;
          state.backgroundTaskId='';
          state.backgroundCanResumePrimary=false;
        }
        return entry;
      }
    }

    const continues=assistantContinues(message);
    const looksInterim=continues||assistantLooksInterim(message);
    const entry={
      message,rawIdx:index,visible:isRenderable(message),boundary:false,
      semanticType:looksInterim?'assistant_interim':'assistant_final',
      backgroundUpdate:false,turnId:state.turnId,
    };
    if(entry.visible){
      if(state.lastPrimaryAssistant&&state.lastPrimaryAssistant.turnId===entry.turnId){
        state.lastPrimaryAssistant.semanticType='assistant_interim';
      }
      state.lastPrimaryAssistant=entry;
      state.lastPrimaryAssistantLooksInterim=looksInterim;
    }
    state.humanRunOpen=continues;
    return entry;
  };

  const project=messages=>{
    const source=Array.isArray(messages)?messages:[];
    const state=createState();
    const entries=[];
    for(let index=0;index<source.length;index++){
      const entry=append(state,source,index);
      if(entry) entries.push(entry);
    }
    return entries;
  };

  const visible=messages=>project(messages).filter(entry=>entry.visible);
  const latestHumanPrompt=messages=>{
    const entries=project(messages);
    for(let index=entries.length-1;index>=0;index--){
      if(entries[index].semanticType==='human_prompt'&&entries[index].visible) return entries[index];
    }
    return null;
  };

  root.HermesMessageProjection=Object.freeze({
    append,
    createState,
    isBackgroundTrigger,
    isSystemControl,
    latestHumanPrompt,
    project,
    visible,
  });
})(typeof window!=='undefined'?window:globalThis);
