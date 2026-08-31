import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import {
  Excalidraw,
  MainMenu,
  serializeAsJSON,
} from '@excalidraw/excalidraw';
import '@excalidraw/excalidraw/index.css';
import './style.css';
import {
  claimDraftSlot,
  clearDraftIfSaved,
  loadDraft,
  recoverySnapshotIsCurrent,
  resolveDraftBaseRevision,
  selectInitialCanvas,
  selectProtectedSerialized,
  storeDraft,
} from './draft-store.mjs';

const ENDPOINT = '/apps/api/wizard-canvas';
const SAVE_DELAY_MS = 800;
const SAVED_VISIBLE_MS = 2600;
const CLIENT_MAX_BYTES = 8 * 1024 * 1024;
const LIGHT_BACKGROUND = '#ffffff';
const INITIAL_FIT_VIEWPORT_FACTOR = 0.72;

function canonicalViewport() {
  return {
    scrollX: 0,
    scrollY: 0,
    zoom: { value: 1 },
  };
}

function storedTheme() {
  try {
    const value = localStorage.getItem('hermes-theme');
    if (value === 'dark' || value === 'light') return value;
    if (value === 'system') {
      return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
    }
  } catch (_) {}
  return window.parent !== window && window.parent.document.documentElement.classList.contains('dark')
    ? 'dark'
    : 'light';
}

function byteLength(value) {
  return new TextEncoder().encode(value).byteLength;
}

function browserStorage() {
  try {
    return window.localStorage;
  } catch (_) {
    return null;
  }
}

function createTabId() {
  if (typeof window.crypto?.randomUUID === 'function') return window.crypto.randomUUID();
  return `tab-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

let DRAFT_KEY = null;
let INHERITED_DRAFT_KEY = null;
let draftClaimChannel = null;

function sceneData(scene, theme) {
  if (!scene || typeof scene !== 'object' || Array.isArray(scene)) return null;
  return {
    elements: Array.isArray(scene.elements) ? scene.elements : [],
    appState: {
      ...(scene.appState && typeof scene.appState === 'object' ? scene.appState : {}),
      theme,
      // Excalidraw's dark renderer maps the canonical white scene background
      // into its dark canvas. Supplying a dark color here would invert it light.
      viewBackgroundColor: LIGHT_BACKGROUND,
      // Viewport position is local presentation state. Start neutral, then fit
      // all restored content after Excalidraw and its container are ready.
      ...canonicalViewport(),
    },
    files: scene.files && typeof scene.files === 'object' ? scene.files : {},
  };
}

function isSceneBlank(elements) {
  return !Array.isArray(elements) || !elements.some(element => element && !element.isDeleted);
}

function WizardCanvas() {
  const revisionRef = useRef(0);
  const readyRef = useRef(false);
  const baselineReadyRef = useRef(false);
  const lockedRef = useRef(false);
  const lastSavedRef = useRef('');
  const currentSerializedRef = useRef('');
  const changeSequenceRef = useRef(0);
  const pendingRef = useRef(null);
  const timerRef = useRef(null);
  const savedTimerRef = useRef(null);
  const savingRef = useRef(false);
  const initialThemeRef = useRef(storedTheme());
  const canvasThemeRef = useRef(initialThemeRef.current);
  const excalidrawApiRef = useRef(null);
  const canvasShellRef = useRef(null);
  const initialElementsRef = useRef(null);
  const initialFitFrameRef = useRef(null);
  const initialFitDoneRef = useRef(false);
  const draftNeedsSaveRef = useRef(false);
  const protectedDraftRef = useRef(false);
  const draftBaseRevisionRef = useRef(null);
  const draftStoredRef = useRef(false);
  const protectedSerializedRef = useRef(null);
  const recoveringDraftRef = useRef(false);
  const [problem, setProblem] = useState(null);
  const [saveStatus, setSaveStatus] = useState(null);
  const [sceneReady, setSceneReady] = useState(false);
  const [sceneBlank, setSceneBlank] = useState(false);
  const [canvasTheme, setCanvasTheme] = useState(initialThemeRef.current);
  const applyCanvasTheme = useCallback(theme => {
    const next = theme === 'dark' ? 'dark' : 'light';
    canvasThemeRef.current = next;
    setCanvasTheme(next);
    document.documentElement.dataset.canvasTheme = next;
    if (excalidrawApiRef.current) {
      excalidrawApiRef.current.updateScene({
        appState: {
          theme: next,
          viewBackgroundColor: LIGHT_BACKGROUND,
        },
      });
    }
  }, []);
  const showSaveStatus = useCallback(phase => {
    window.clearTimeout(savedTimerRef.current);
    savedTimerRef.current = null;
    if (!phase) {
      setSaveStatus(null);
      return;
    }
    const text = phase === 'saved' ? 'Saved' : 'Saving…';
    setSaveStatus(current => (
      current?.phase === phase ? current : { phase, text }
    ));
    if (phase === 'saved') {
      savedTimerRef.current = window.setTimeout(() => {
        setSaveStatus(current => current?.phase === 'saved' ? null : current);
      }, SAVED_VISIBLE_MS);
    }
  }, []);
  const updateProblem = useCallback((tone, text, action = null) => {
    setProblem(current => (
      current?.tone === tone && current?.text === text && current?.action === action
        ? current
        : { tone, text, action }
    ));
  }, []);

  const fitInitialScene = useCallback(() => {
    if (initialFitDoneRef.current || initialFitFrameRef.current) return;
    const restoredElements = initialElementsRef.current;
    if (!Array.isArray(restoredElements)) return;
    const liveElements = restoredElements.filter(element => element && !element.isDeleted);
    if (!liveElements.length) {
      initialFitDoneRef.current = true;
      return;
    }
    initialFitFrameRef.current = window.requestAnimationFrame(() => {
      initialFitFrameRef.current = window.requestAnimationFrame(() => {
        initialFitFrameRef.current = null;
        const api = excalidrawApiRef.current;
        const shell = canvasShellRef.current;
        if (!api || !shell || shell.clientWidth <= 0 || shell.clientHeight <= 0) return;
        api.scrollToContent(liveElements, {
          fitToViewport: true,
          viewportZoomFactor: INITIAL_FIT_VIEWPORT_FACTOR,
          animate: false,
          maxZoom: 1,
        });
        initialFitDoneRef.current = true;
      });
    });
  }, []);

  const loadInitialData = useMemo(() => (async () => {
    try {
      const response = await fetch(ENDPOINT, {
        headers: { Accept: 'application/json' },
        cache: 'no-store',
      });
      if (!response.ok) throw new Error(`Canvas load failed (${response.status})`);
      const payload = await response.json();
      revisionRef.current = Number.isInteger(payload.revision) ? payload.revision : 0;
      const serverSerialized = payload.scene ? JSON.stringify(payload.scene) : null;
      const storage = browserStorage();
      let draft = loadDraft(storage, DRAFT_KEY);
      const draftFromCurrentSlot = Boolean(draft);
      if (!draft && INHERITED_DRAFT_KEY) {
        draft = loadDraft(storage, INHERITED_DRAFT_KEY);
        if (draft) {
          storeDraft(storage, DRAFT_KEY, {
            baseRevision: draft.baseRevision,
            serialized: draft.serialized,
          });
        }
      }
      draftStoredRef.current = Boolean(draft);
      const selected = selectInitialCanvas({
        serverRevision: revisionRef.current,
        serverSerialized,
        draft,
      });
      if (draftFromCurrentSlot && selected.source === 'server' && !selected.hasConflict) {
        clearDraftIfSaved(storage, DRAFT_KEY, draft.serialized);
        draftStoredRef.current = false;
      }
      draftNeedsSaveRef.current = selected.needsSave;
      protectedDraftRef.current = selected.hasConflict;
      draftBaseRevisionRef.current = selected.hasConflict ? draft.baseRevision : null;
      protectedSerializedRef.current = selected.hasConflict ? selected.serialized : null;
      if (selected.hasConflict) {
        lockedRef.current = true;
        updateProblem('conflict', 'Unsaved changes protected', 'recover');
      }
      const selectedScene = selected.serialized ? JSON.parse(selected.serialized) : payload.scene;
      const initialScene = sceneData(selectedScene, canvasThemeRef.current);
      initialElementsRef.current = initialScene?.elements || [];
      setSceneBlank(isSceneBlank(initialScene?.elements));
      setSceneReady(true);
      readyRef.current = true;
      if (!selected.hasConflict) setProblem(null);
      fitInitialScene();
      return initialScene;
    } catch (error) {
      console.error('[wizard-canvas] load failed', error);
      lockedRef.current = true;
      updateProblem('error', 'Server save unavailable', 'reload');
      return null;
    }
  })(), [fitInitialScene, updateProblem]);

  const flushSave = useCallback(async () => {
    if (savingRef.current || lockedRef.current || !readyRef.current) return;
    const serialized = pendingRef.current;
    if (!serialized || serialized === lastSavedRef.current) return;
    if (byteLength(serialized) > CLIENT_MAX_BYTES) {
      lockedRef.current = true;
      showSaveStatus(null);
      updateProblem('error', 'Canvas is too large to save');
      return;
    }

    savingRef.current = true;
    showSaveStatus('saving');
    try {
      const response = await fetch(ENDPOINT, {
        method: 'PUT',
        headers: {
          Accept: 'application/json',
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          baseRevision: revisionRef.current,
          scene: JSON.parse(serialized),
        }),
        cache: 'no-store',
      });
      if (response.status === 409) {
        lockedRef.current = true;
        protectedDraftRef.current = true;
        draftBaseRevisionRef.current = revisionRef.current;
        protectedSerializedRef.current = pendingRef.current || serialized;
        showSaveStatus(null);
        updateProblem(
          'conflict',
          draftStoredRef.current ? 'Unsaved changes protected' : 'Unsaved changes — keep this tab open',
          'recover',
        );
        return;
      }
      if (!response.ok) throw new Error(`Canvas save failed (${response.status})`);
      const payload = await response.json();
      revisionRef.current = payload.revision;
      lastSavedRef.current = serialized;
      const storage = browserStorage();
      const cleared = clearDraftIfSaved(storage, DRAFT_KEY, serialized);
      draftStoredRef.current = !cleared && Boolean(loadDraft(storage, DRAFT_KEY));
      if (pendingRef.current === serialized) pendingRef.current = null;
      protectedDraftRef.current = false;
      draftBaseRevisionRef.current = null;
      protectedSerializedRef.current = null;
      setProblem(null);
      showSaveStatus(
        pendingRef.current && pendingRef.current !== lastSavedRef.current ? 'saving' : 'saved'
      );
    } catch (error) {
      console.error('[wizard-canvas] save failed', error);
      showSaveStatus(null);
      updateProblem(
        'error',
        draftStoredRef.current ? 'Not saved — kept on this device' : 'Not saved — keep this tab open',
        'retry',
      );
    } finally {
      savingRef.current = false;
      if (!lockedRef.current && pendingRef.current && pendingRef.current !== lastSavedRef.current) {
        window.clearTimeout(timerRef.current);
        timerRef.current = window.setTimeout(flushSave, SAVE_DELAY_MS);
      }
    }
  }, [showSaveStatus, updateProblem]);

  const handleChange = useCallback((elements, appState, files) => {
    if (readyRef.current) setSceneBlank(isSceneBlank(elements));
    if (!readyRef.current) return;
    let serialized;
    try {
      // The local serializer is self-contained: it retains bounded embedded files.
      // No Excalidraw cloud or browser file action is enabled by this choice.
      // Theme is a local view preference. Normalize it out of the shared scene
      // so a light/dark toggle never creates a server save or changes another tab.
      const persistentAppState = {
        ...appState,
        theme: 'light',
        viewBackgroundColor: LIGHT_BACKGROUND,
        // Pan and zoom are local view state and must not rewrite the shared scene.
        ...canonicalViewport(),
      };
      serialized = serializeAsJSON(elements, persistentAppState, files, 'local');
    } catch (error) {
      console.error('[wizard-canvas] serialize failed', error);
      showSaveStatus(null);
      updateProblem('error', 'Canvas could not be prepared');
      return;
    }

    if (!baselineReadyRef.current) {
      baselineReadyRef.current = true;
      currentSerializedRef.current = serialized;
      if (draftNeedsSaveRef.current || protectedDraftRef.current) {
        draftNeedsSaveRef.current = false;
        lastSavedRef.current = '';
        pendingRef.current = serialized;
        if (protectedDraftRef.current) protectedSerializedRef.current = serialized;
        draftStoredRef.current = storeDraft(browserStorage(), DRAFT_KEY, {
          baseRevision: resolveDraftBaseRevision(
            revisionRef.current,
            protectedDraftRef.current ? draftBaseRevisionRef.current : null,
          ),
          serialized,
        });
        if (!lockedRef.current) {
          showSaveStatus('saving');
          window.clearTimeout(timerRef.current);
          timerRef.current = window.setTimeout(flushSave, SAVE_DELAY_MS);
        }
      } else {
        lastSavedRef.current = serialized;
      }
      return;
    }
    if (currentSerializedRef.current !== serialized) {
      currentSerializedRef.current = serialized;
      changeSequenceRef.current += 1;
    }
    if (serialized === lastSavedRef.current && !lockedRef.current) return;
    pendingRef.current = serialized;
    if (protectedDraftRef.current) protectedSerializedRef.current = serialized;
    draftStoredRef.current = storeDraft(browserStorage(), DRAFT_KEY, {
      baseRevision: resolveDraftBaseRevision(
        revisionRef.current,
        protectedDraftRef.current ? draftBaseRevisionRef.current : null,
      ),
      serialized,
    });
    if (lockedRef.current) return;
    showSaveStatus('saving');
    window.clearTimeout(timerRef.current);
    timerRef.current = window.setTimeout(flushSave, SAVE_DELAY_MS);
  }, [flushSave, showSaveStatus, updateProblem]);

  const recoverDraft = useCallback(async () => {
    if (recoveringDraftRef.current) return;
    const storage = browserStorage();
    const storedDraft = loadDraft(storage, DRAFT_KEY);
    const serialized = selectProtectedSerialized(
      protectedSerializedRef.current,
      pendingRef.current,
      storedDraft?.serialized,
    );
    if (!serialized) {
      updateProblem('error', 'Unsaved changes are only in this tab — keep it open', 'recover');
      return;
    }
    const recoverySequence = changeSequenceRef.current;
    recoveringDraftRef.current = true;
    updateProblem('conflict', 'Checking saved version…');
    try {
      const response = await fetch(ENDPOINT, {
        headers: { Accept: 'application/json' },
        cache: 'no-store',
      });
      if (!response.ok) throw new Error(`Canvas load failed (${response.status})`);
      const payload = await response.json();
      const serverSerialized = payload.scene ? JSON.stringify(payload.scene) : '';
      if (!recoverySnapshotIsCurrent(recoverySequence, changeSequenceRef.current)) {
        updateProblem(
          'conflict',
          draftStoredRef.current ? 'Newer changes protected — recover again' : 'Newer changes kept in this tab — recover again',
          'recover',
        );
        return;
      }
      revisionRef.current = Number.isInteger(payload.revision) ? payload.revision : 0;
      if (serverSerialized === serialized) {
        lastSavedRef.current = serialized;
        pendingRef.current = null;
        const cleared = clearDraftIfSaved(storage, DRAFT_KEY, serialized);
        draftStoredRef.current = !cleared && Boolean(loadDraft(storage, DRAFT_KEY));
        protectedDraftRef.current = false;
        draftBaseRevisionRef.current = null;
        protectedSerializedRef.current = null;
        lockedRef.current = false;
        setProblem(null);
        showSaveStatus('saved');
        return;
      }
      lastSavedRef.current = serverSerialized;
      pendingRef.current = serialized;
      draftBaseRevisionRef.current = null;
      draftStoredRef.current = storeDraft(storage, DRAFT_KEY, {
        baseRevision: revisionRef.current,
        serialized,
      });
      protectedDraftRef.current = false;
      lockedRef.current = false;
      setProblem(null);
      showSaveStatus('saving');
      window.clearTimeout(timerRef.current);
      timerRef.current = window.setTimeout(flushSave, 0);
    } catch (error) {
      console.error('[wizard-canvas] recovery check failed', error);
      updateProblem(
        'error',
        draftStoredRef.current ? 'Draft kept — server check failed' : 'Server check failed — keep this tab open',
        'recover',
      );
    } finally {
      recoveringDraftRef.current = false;
    }
  }, [flushSave, showSaveStatus, updateProblem]);

  useEffect(() => {
    const flushOnHide = () => {
      window.clearTimeout(timerRef.current);
      void flushSave();
    };
    const warnIfUnsaved = event => {
      if (!pendingRef.current || pendingRef.current === lastSavedRef.current) return;
      event.preventDefault();
      event.returnValue = '';
    };
    window.addEventListener('pagehide', flushOnHide);
    window.addEventListener('beforeunload', warnIfUnsaved);
    return () => {
      window.removeEventListener('pagehide', flushOnHide);
      window.removeEventListener('beforeunload', warnIfUnsaved);
      window.clearTimeout(timerRef.current);
      window.clearTimeout(savedTimerRef.current);
      window.cancelAnimationFrame(initialFitFrameRef.current);
    };
  }, [flushSave]);

  useEffect(() => {
    const shell = canvasShellRef.current;
    if (!shell || typeof ResizeObserver === 'undefined') return undefined;
    const observer = new ResizeObserver(() => fitInitialScene());
    observer.observe(shell);
    return () => observer.disconnect();
  }, [fitInitialScene]);

  useEffect(() => {
    document.documentElement.dataset.canvasTheme = canvasTheme;
  }, [canvasTheme]);

  useEffect(() => {
    const handleThemeMessage = event => {
      if (event.origin !== location.origin || event.source !== window.parent) return;
      if (!event.data || event.data.type !== 'hermesui:theme') return;
      applyCanvasTheme(event.data.theme);
    };
    const handleStoredTheme = event => {
      if (!event || event.key === 'hermes-theme') applyCanvasTheme(storedTheme());
    };
    const media = window.matchMedia('(prefers-color-scheme: dark)');
    const handleSystemTheme = () => {
      try {
        if (localStorage.getItem('hermes-theme') === 'system') applyCanvasTheme(storedTheme());
      } catch (_) {}
    };
    window.addEventListener('message', handleThemeMessage);
    window.addEventListener('storage', handleStoredTheme);
    media.addEventListener('change', handleSystemTheme);
    return () => {
      window.removeEventListener('message', handleThemeMessage);
      window.removeEventListener('storage', handleStoredTheme);
      media.removeEventListener('change', handleSystemTheme);
    };
  }, [applyCanvasTheme]);

  const captureExcalidrawApi = useCallback(api => {
    excalidrawApiRef.current = api;
    applyCanvasTheme(canvasThemeRef.current);
    fitInitialScene();
  }, [applyCanvasTheme, fitInitialScene]);

  const topRightUi = useCallback(() => {
    if (problem) {
      const action = problem.action;
      const label = action === 'recover' ? 'Recover' : action === 'retry' ? 'Retry' : 'Reload';
      const act = action === 'recover'
        ? recoverDraft
        : action === 'retry'
          ? () => void flushSave()
          : () => window.location.reload();
      return (
        <div className={`wizard-canvas-recovery is-${problem.tone}`} role="alert">
          <span>{problem.text}</span>
          {action ? <button type="button" onClick={act}>{label}</button> : null}
        </div>
      );
    }
    return saveStatus ? (
      <div
        className={`wizard-canvas-save is-${saveStatus.phase}`}
        role="status"
        aria-live="polite"
      >
        {saveStatus.text}
      </div>
    ) : null;
  }, [flushSave, problem, recoverDraft, saveStatus]);

  return (
    <main ref={canvasShellRef} className="wizard-canvas-shell" aria-label="Persistent Wizard canvas">
      <Excalidraw
        excalidrawAPI={captureExcalidrawApi}
        initialData={loadInitialData}
        onChange={handleChange}
        renderTopRightUI={topRightUi}
        theme={canvasTheme}
        name="Wizard Canvas"
        langCode="en"
        autoFocus={false}
        handleKeyboardGlobally={false}
        isCollaborating={false}
        aiEnabled={false}
        validateEmbeddable={() => false}
        UIOptions={{
          canvasActions: {
            changeViewBackgroundColor: false,
            clearCanvas: true,
            export: false,
            loadScene: false,
            saveToActiveFile: false,
            toggleTheme: false,
            saveAsImage: false,
          },
          tools: { image: true },
        }}
      >
        <MainMenu>
          <MainMenu.DefaultItems.ClearCanvas />
        </MainMenu>
      </Excalidraw>
      {sceneReady && sceneBlank ? (
        <div className="wizard-canvas-watermark" aria-hidden="true">
          <img src="../wizard-hat-mark.svg" alt="" />
        </div>
      ) : null}
    </main>
  );
}

async function startWizardCanvas() {
  const claim = await claimDraftSlot({
    sessionStorage: window.sessionStorage,
    BroadcastChannelClass: window.BroadcastChannel,
    createId: createTabId,
  });
  DRAFT_KEY = claim.draftKey;
  INHERITED_DRAFT_KEY = claim.inheritedDraftKey;
  draftClaimChannel = claim.channel;
  createRoot(document.getElementById('root')).render(<WizardCanvas />);
}

void startWizardCanvas();
