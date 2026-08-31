const DRAFT_VERSION = 1;
const DEFAULT_MAX_BYTES = 8 * 1024 * 1024;
export const DRAFT_KEY_PREFIX = 'wizard-canvas.unsaved.v1.';

export function draftKeyForTab(tabId) {
  if (typeof tabId !== 'string' || !/^[A-Za-z0-9-]{8,80}$/.test(tabId)) return null;
  return `${DRAFT_KEY_PREFIX}${tabId}`;
}

function encodedBytes(value) {
  return new TextEncoder().encode(value).byteLength;
}

function validSerializedScene(serialized, maxBytes) {
  if (typeof serialized !== 'string' || !serialized || encodedBytes(serialized) > maxBytes) return false;
  try {
    const scene = JSON.parse(serialized);
    return Boolean(scene && typeof scene === 'object' && !Array.isArray(scene));
  } catch (_) {
    return false;
  }
}

export function loadDraft(storage, key, { maxBytes = DEFAULT_MAX_BYTES } = {}) {
  if (!storage || !key) return null;
  try {
    const raw = storage.getItem(key);
    if (!raw || encodedBytes(raw) > maxBytes + 65536) return null;
    const draft = JSON.parse(raw);
    if (
      draft?.version !== DRAFT_VERSION
      || !Number.isSafeInteger(draft.baseRevision)
      || draft.baseRevision < 0
      || !validSerializedScene(draft.serialized, maxBytes)
    ) return null;
    return {
      version: DRAFT_VERSION,
      baseRevision: draft.baseRevision,
      updatedAt: typeof draft.updatedAt === 'string' ? draft.updatedAt : null,
      serialized: draft.serialized,
    };
  } catch (_) {
    return null;
  }
}

export function storeDraft(storage, key, { baseRevision, serialized }) {
  if (
    !storage
    || !key
    || !Number.isSafeInteger(baseRevision)
    || baseRevision < 0
    || !validSerializedScene(serialized, DEFAULT_MAX_BYTES)
  ) return false;
  try {
    storage.setItem(key, JSON.stringify({
      version: DRAFT_VERSION,
      baseRevision,
      updatedAt: new Date().toISOString(),
      serialized,
    }));
    return true;
  } catch (_) {
    return false;
  }
}

export function clearDraftIfSaved(storage, key, serialized) {
  const draft = loadDraft(storage, key);
  if (!draft || draft.serialized !== serialized) return false;
  try {
    storage.removeItem(key);
    return true;
  } catch (_) {
    return false;
  }
}

export function resolveDraftBaseRevision(serverRevision, protectedRevision = null) {
  if (Number.isSafeInteger(protectedRevision) && protectedRevision >= 0) return protectedRevision;
  return serverRevision;
}

export function selectProtectedSerialized(...candidates) {
  return candidates.find(candidate => validSerializedScene(candidate, DEFAULT_MAX_BYTES)) || null;
}

export function recoverySnapshotIsCurrent(startSequence, currentSequence) {
  return Number.isSafeInteger(startSequence)
    && Number.isSafeInteger(currentSequence)
    && startSequence === currentSequence;
}

export function selectInitialCanvas({ serverRevision, serverSerialized, draft }) {
  if (!draft || draft.serialized === serverSerialized) {
    return {
      source: 'server',
      serialized: serverSerialized,
      needsSave: false,
      hasConflict: false,
    };
  }
  if (draft.baseRevision === serverRevision) {
    return {
      source: 'draft',
      serialized: draft.serialized,
      needsSave: true,
      hasConflict: false,
    };
  }
  return {
    source: 'draft',
    serialized: draft.serialized,
    needsSave: false,
    hasConflict: true,
  };
}
