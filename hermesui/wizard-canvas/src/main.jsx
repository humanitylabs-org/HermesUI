import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import {
  Excalidraw,
  MainMenu,
  serializeAsJSON,
} from '@excalidraw/excalidraw';
import '@excalidraw/excalidraw/index.css';
import './style.css';

const ENDPOINT = '/apps/api/wizard-canvas';
const SAVE_DELAY_MS = 800;
const CLIENT_MAX_BYTES = 8 * 1024 * 1024;

function byteLength(value) {
  return new TextEncoder().encode(value).byteLength;
}

function sceneData(scene) {
  if (!scene || typeof scene !== 'object' || Array.isArray(scene)) return null;
  return {
    elements: Array.isArray(scene.elements) ? scene.elements : [],
    appState: scene.appState && typeof scene.appState === 'object' ? scene.appState : {},
    files: scene.files && typeof scene.files === 'object' ? scene.files : {},
  };
}

function WizardCanvas() {
  const revisionRef = useRef(0);
  const readyRef = useRef(false);
  const baselineReadyRef = useRef(false);
  const lockedRef = useRef(false);
  const lastSavedRef = useRef('');
  const pendingRef = useRef(null);
  const timerRef = useRef(null);
  const savingRef = useRef(false);
  const [status, setStatus] = useState({ tone: 'loading', text: 'Loading canvas…' });
  const updateStatus = useCallback((tone, text) => {
    setStatus(current => (
      current.tone === tone && current.text === text ? current : { tone, text }
    ));
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
      readyRef.current = true;
      updateStatus('saved', 'Saved on this server');
      return sceneData(payload.scene);
    } catch (error) {
      console.error('[wizard-canvas] load failed', error);
      lockedRef.current = true;
      updateStatus('error', 'Server save unavailable');
      return null;
    }
  })(), [updateStatus]);

  const flushSave = useCallback(async () => {
    if (savingRef.current || lockedRef.current || !readyRef.current) return;
    const serialized = pendingRef.current;
    if (!serialized || serialized === lastSavedRef.current) return;
    if (byteLength(serialized) > CLIENT_MAX_BYTES) {
      lockedRef.current = true;
      updateStatus('error', 'Canvas is too large to save');
      return;
    }

    savingRef.current = true;
    updateStatus('saving', 'Saving…');
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
        updateStatus('conflict', 'Changed in another tab');
        return;
      }
      if (!response.ok) throw new Error(`Canvas save failed (${response.status})`);
      const payload = await response.json();
      revisionRef.current = payload.revision;
      lastSavedRef.current = serialized;
      if (pendingRef.current === serialized) pendingRef.current = null;
      updateStatus('saved', 'Saved on this server');
    } catch (error) {
      console.error('[wizard-canvas] save failed', error);
      updateStatus('error', 'Not saved — retrying');
    } finally {
      savingRef.current = false;
      if (!lockedRef.current && pendingRef.current && pendingRef.current !== lastSavedRef.current) {
        window.clearTimeout(timerRef.current);
        timerRef.current = window.setTimeout(flushSave, SAVE_DELAY_MS);
      }
    }
  }, [updateStatus]);

  const handleChange = useCallback((elements, appState, files) => {
    if (!readyRef.current || lockedRef.current) return;
    let serialized;
    try {
      // The local serializer is self-contained: it retains bounded embedded files.
      // No Excalidraw cloud or browser file action is enabled by this choice.
      serialized = serializeAsJSON(elements, appState, files, 'local');
    } catch (error) {
      console.error('[wizard-canvas] serialize failed', error);
      updateStatus('error', 'Canvas could not be prepared');
      return;
    }

    if (!baselineReadyRef.current) {
      baselineReadyRef.current = true;
      lastSavedRef.current = serialized;
      return;
    }
    if (serialized === lastSavedRef.current) return;
    pendingRef.current = serialized;
    updateStatus('saving', 'Saving…');
    window.clearTimeout(timerRef.current);
    timerRef.current = window.setTimeout(flushSave, SAVE_DELAY_MS);
  }, [flushSave, updateStatus]);

  useEffect(() => {
    const flushOnHide = () => {
      window.clearTimeout(timerRef.current);
      void flushSave();
    };
    window.addEventListener('pagehide', flushOnHide);
    return () => {
      window.removeEventListener('pagehide', flushOnHide);
      window.clearTimeout(timerRef.current);
    };
  }, [flushSave]);

  const statusUi = useCallback(() => (
    <div className={`wizard-canvas-status is-${status.tone}`} role="status" aria-live="polite">
      <span className="wizard-canvas-status-dot" aria-hidden="true" />
      <span>{status.text}</span>
      {(status.tone === 'conflict' || status.tone === 'error') && (
        <button type="button" onClick={() => window.location.reload()}>Reload</button>
      )}
    </div>
  ), [status]);

  return (
    <main className="wizard-canvas-shell" aria-label="Persistent Wizard canvas">
      <Excalidraw
        initialData={loadInitialData}
        onChange={handleChange}
        renderTopRightUI={statusUi}
        theme="light"
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
    </main>
  );
}

createRoot(document.getElementById('root')).render(<WizardCanvas />);
