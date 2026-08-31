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

  const isBackgroundTrigger=message=>{
    if(!message||roleOf(message)!=='user') return false;
    if(typeof root._isBackgroundUpdateTriggerMessage==='function'){
      return !!root._isBackgroundUpdateTriggerMessage(message);
    }
    if(message._source==='process_wakeup'||message._source==='async_delegation') return true;
    const text=textOf(message);
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
    const text=textOf(message);
    const processMatch=text.match(/\b(proc_[A-Za-z0-9_-]+)\b/);
    if(processMatch) return processMatch[1];
    const delegationMatch=text.match(/^\s*\[ASYNC DELEGATION(?: BATCH)? COMPLETE\s*(?:—|-)\s*([^\]\s]+)/i);
    return delegationMatch?delegationMatch[1]:'';
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
    if(!taskId||!Number.isInteger(state.lastHumanIdx)||state.lastHumanIdx<0||index<=state.lastHumanIdx) return false;
    const start=Math.max(state.lastHumanIdx+1,index-600);
    for(let cursor=index-1;cursor>=start;cursor--){
      const prior=source[cursor];
      if(prior&&roleOf(prior)==='tool'&&textOf(prior).includes(taskId)) return true;
    }
    return false;
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
  });

  const append=(state,source,index)=>{
    const message=source[index];
    if(!message) return null;
    const role=roleOf(message);

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
      return {message,rawIdx:index,visible:false,boundary:true,semanticType:'system_control',backgroundUpdate:state.backgroundActive};
    }

    if(role==='user'){
      if(isSystemControl(message)){
        return {message,rawIdx:index,visible:false,boundary:true,semanticType:'system_control',backgroundUpdate:false};
      }
      state.turnId+=1;
      state.lastHumanIdx=index;
      state.humanRunOpen=true;
      state.backgroundActive=false;
      state.backgroundTaskId='';
      state.backgroundCanResumePrimary=false;
      state.lastPrimaryAssistant=null;
      state.lastPrimaryAssistantLooksInterim=false;
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
