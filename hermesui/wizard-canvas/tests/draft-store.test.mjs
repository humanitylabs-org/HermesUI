import assert from 'node:assert/strict';
import test from 'node:test';

import {
  claimDraftSlot,
  clearDraftIfSaved,
  draftKeyForTab,
  loadDraft,
  recoverySnapshotIsCurrent,
  resolveDraftBaseRevision,
  selectInitialCanvas,
  selectProtectedSerialized,
  storeDraft,
} from '../src/draft-store.mjs';

class MemoryStorage {
  constructor() {
    this.values = new Map();
  }

  getItem(key) {
    return this.values.has(key) ? this.values.get(key) : null;
  }

  setItem(key, value) {
    this.values.set(key, String(value));
  }

  removeItem(key) {
    this.values.delete(key);
  }
}

class FailingStorage extends MemoryStorage {
  setItem() {
    throw new Error('quota exceeded');
  }
}

class FakeBroadcastChannel {
  static channels = new Map();

  constructor(name) {
    this.name = name;
    this.listener = null;
    const peers = FakeBroadcastChannel.channels.get(name) || new Set();
    peers.add(this);
    FakeBroadcastChannel.channels.set(name, peers);
  }

  addEventListener(type, listener) {
    if (type === 'message') this.listener = listener;
  }

  postMessage(data) {
    for (const peer of FakeBroadcastChannel.channels.get(this.name) || []) {
      if (peer === this || !peer.listener) continue;
      queueMicrotask(() => peer.listener({ data }));
    }
  }

  close() {
    FakeBroadcastChannel.channels.get(this.name)?.delete(this);
  }

  static reset() {
    FakeBroadcastChannel.channels.clear();
  }
}

function ids(...values) {
  let index = 0;
  return () => values[index++];
}

const KEY = 'wizard-canvas.unsaved.v1';
const serverScene = JSON.stringify({
  type: 'excalidraw',
  version: 2,
  source: 'local',
  elements: [],
  appState: {},
  files: {},
});
const editedScene = JSON.stringify({
  type: 'excalidraw',
  version: 2,
  source: 'local',
  elements: [{ id: 'important-change', type: 'text', text: 'Keep me' }],
  appState: {},
  files: {},
});

test('an unsaved same-revision draft survives a fresh app instance and is selected for recovery', () => {
  const storage = new MemoryStorage();
  assert.equal(storeDraft(storage, KEY, { baseRevision: 7, serialized: editedScene }), true);

  const reloadedDraft = loadDraft(storage, KEY);
  assert.equal(reloadedDraft.baseRevision, 7);
  assert.equal(reloadedDraft.serialized, editedScene);
  assert.deepEqual(selectInitialCanvas({
    serverRevision: 7,
    serverSerialized: serverScene,
    draft: reloadedDraft,
  }), {
    source: 'draft',
    serialized: editedScene,
    needsSave: true,
    hasConflict: false,
  });
});

test('different tabs keep independent draft slots and clear only their own confirmed save', () => {
  const storage = new MemoryStorage();
  const tabA = draftKeyForTab('tab-a-12345678');
  const tabB = draftKeyForTab('tab-b-12345678');
  assert.notEqual(tabA, tabB);
  storeDraft(storage, tabA, { baseRevision: 7, serialized: editedScene });
  storeDraft(storage, tabB, { baseRevision: 7, serialized: serverScene });
  assert.equal(clearDraftIfSaved(storage, tabA, serverScene), false);
  assert.equal(loadDraft(storage, tabA).serialized, editedScene);
  assert.equal(clearDraftIfSaved(storage, tabA, editedScene), true);
  assert.equal(loadDraft(storage, tabA), null);
  assert.equal(loadDraft(storage, tabB).serialized, serverScene);
});

test('an opener-cloned tab rotates the inherited draft slot while the original stays active', async t => {
  FakeBroadcastChannel.reset();
  t.after(() => FakeBroadcastChannel.reset());
  const parentSession = new MemoryStorage();
  const parent = await claimDraftSlot({
    sessionStorage: parentSession,
    BroadcastChannelClass: FakeBroadcastChannel,
    createId: ids('parent-tab-12345678', 'parent-nonce-12345678'),
    waitMs: 1,
  });
  const childSession = new MemoryStorage();
  childSession.setItem('wizard-canvas.tab-id.v1', parent.tabId);
  const child = await claimDraftSlot({
    sessionStorage: childSession,
    BroadcastChannelClass: FakeBroadcastChannel,
    createId: ids('child-nonce-12345678', 'child-tab-12345678'),
    waitMs: 1,
  });

  assert.notEqual(child.tabId, parent.tabId);
  assert.notEqual(child.draftKey, parent.draftKey);
  assert.equal(child.inheritedDraftKey, parent.draftKey);
  assert.equal(parentSession.getItem('wizard-canvas.tab-id.v1'), parent.tabId);
  assert.equal(childSession.getItem('wizard-canvas.tab-id.v1'), child.tabId);
  parent.channel.close();
  child.channel.close();
});

test('without BroadcastChannel an inherited slot is rotated but remains available for recovery', async () => {
  const session = new MemoryStorage();
  session.setItem('wizard-canvas.tab-id.v1', 'inherited-tab-12345678');
  const claim = await claimDraftSlot({
    sessionStorage: session,
    BroadcastChannelClass: null,
    createId: ids('nonce-tab-12345678', 'fresh-tab-12345678'),
    waitMs: 0,
  });

  assert.equal(claim.tabId, 'fresh-tab-12345678');
  assert.equal(claim.inheritedDraftKey, draftKeyForTab('inherited-tab-12345678'));
  assert.equal(session.getItem('wizard-canvas.tab-id.v1'), 'fresh-tab-12345678');
});

test('a newer server revision is not overwritten while the local draft remains recoverable', () => {
  const storage = new MemoryStorage();
  storeDraft(storage, KEY, { baseRevision: 7, serialized: editedScene });
  const draft = loadDraft(storage, KEY);

  assert.deepEqual(selectInitialCanvas({
    serverRevision: 8,
    serverSerialized: serverScene,
    draft,
  }), {
    source: 'draft',
    serialized: editedScene,
    needsSave: false,
    hasConflict: true,
  });
  assert.equal(loadDraft(storage, KEY).serialized, editedScene);
  assert.equal(resolveDraftBaseRevision(8, draft.baseRevision), 7);
  assert.equal(resolveDraftBaseRevision(8), 8);
});

test('the in-memory snapshot remains recoverable when browser draft storage fails', () => {
  const storage = new FailingStorage();
  assert.equal(storeDraft(storage, KEY, { baseRevision: 7, serialized: editedScene }), false);
  assert.equal(loadDraft(storage, KEY), null);
  assert.equal(selectProtectedSerialized(editedScene, null, null), editedScene);
});

test('a recovery result is rejected after the visible scene changes', () => {
  assert.equal(recoverySnapshotIsCurrent(7, 7), true);
  assert.equal(recoverySnapshotIsCurrent(7, 8), false);
  assert.equal(recoverySnapshotIsCurrent(7, 9), false);
});

test('a draft already present on the server is safely discarded after reload', () => {
  const storage = new MemoryStorage();
  storeDraft(storage, KEY, { baseRevision: 7, serialized: editedScene });
  const draft = loadDraft(storage, KEY);

  assert.deepEqual(selectInitialCanvas({
    serverRevision: 8,
    serverSerialized: editedScene,
    draft,
  }), {
    source: 'server',
    serialized: editedScene,
    needsSave: false,
    hasConflict: false,
  });
});