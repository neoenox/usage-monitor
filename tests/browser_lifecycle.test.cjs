const {test} = require('node:test');
const assert = require('node:assert/strict');

// Stateful chrome stub: drives install/startup handlers like a real restart.
const state = {alarm: null, tab: null, storage: {}, createdTabs: [], removedTabs: [], reloadedTabs: [], createdAlarms: 0};
const listeners = {};
function reset(s) {
  Object.assign(state, {alarm: null, tab: null, storage: {}, createdTabs: [], removedTabs: [], reloadedTabs: [], createdAlarms: 0}, s);
}
globalThis.chrome = {
  runtime: {
    id: 'test',
    onMessage: {addListener: (fn) => { listeners.message = fn; }},
    onInstalled: {addListener: (fn) => { listeners.installed = fn; }},
    onStartup: {addListener: (fn) => { listeners.startup = fn; }},
    sendNativeMessage: () => {},
  },
  action: {
    onClicked: {addListener: (fn) => { listeners.clicked = fn; }},
    setBadgeText: async () => {}, setBadgeBackgroundColor: async () => {}, setTitle: async () => {},
  },
  storage: {
    local: {
      get: async (k) => (typeof k === 'string' ? {[k]: state.storage[k]} : {...state.storage}),
      set: async (o) => { Object.assign(state.storage, o); },
      remove: async (k) => { delete state.storage[k]; },
    },
  },
  tabs: {
    get: async (id) => {
      if (state.tab && state.tab.id === id) return state.tab;
      const err = new Error('No tab');
      throw err;
    },
    reload: async (id) => { state.reloadedTabs.push(id); },
    create: async (o) => { const t = {id: 900 + state.createdTabs.length, url: o.url}; state.createdTabs.push(t); return t; },
    remove: async (id) => { state.removedTabs.push(id); },
  },
  alarms: {
    get: async () => state.alarm,
    create: async () => { state.createdAlarms++; state.alarm = {name: 'usage-refresh'}; },
    onAlarm: {addListener: (fn) => { listeners.alarm = fn; }},
  },
};
require('../browser-extension/background.js');

test('restart without alarm or tab recreates both', async () => {
  reset({});
  await listeners.startup();
  assert.equal(state.createdAlarms, 1);
  assert.equal(state.createdTabs.length, 1);
  assert.match(state.createdTabs[0].url, /claude\.ai\/settings\/usage/);
  assert.equal(state.storage.usageTabId, state.createdTabs[0].id);
});

test('restart keeps existing alarm and reloads healthy tab', async () => {
  reset({alarm: {name: 'usage-refresh'}, tab: {id: 7, url: 'https://claude.ai/settings/usage'}, storage: {usageTabId: 7}});
  await listeners.startup();
  assert.equal(state.createdAlarms, 0);
  assert.deepEqual(state.reloadedTabs, [7]);
  assert.equal(state.createdTabs.length, 0);
});

test('restart drops login-wall tab and tracks a fresh one', async () => {
  reset({alarm: {name: 'usage-refresh'},
    tab: {id: 8, url: 'https://claude.ai/login?from=logout'}, storage: {usageTabId: 8}});
  await listeners.startup();
  assert.deepEqual(state.removedTabs, [8]);
  assert.equal(state.createdTabs.length, 1);
  assert.equal(state.storage.usageTabId, state.createdTabs[0].id);
});

test('restart never closes a repurposed user tab', async () => {
  reset({alarm: {name: 'usage-refresh'},
    tab: {id: 9, url: 'https://example.com/'}, storage: {usageTabId: 9}});
  await listeners.startup();
  assert.deepEqual(state.removedTabs, []);
  assert.equal(state.createdTabs.length, 1);
  assert.equal(state.storage.usageTabId, state.createdTabs[0].id);
});

test('install registers alarm and opens usage tab', async () => {
  reset({});
  await listeners.installed();
  assert.equal(state.createdAlarms, 1);
  assert.equal(state.createdTabs.length, 1);
});

test('closed tab suppresses recreation until startup', async () => {
  reset({alarm: {name: 'usage-refresh'}, tab: null, storage: {usageTabId: 8}});
  await listeners.alarm({name: 'usage-refresh'});
  assert.equal(state.createdTabs.length, 0);
  assert.equal(state.storage.tabSuppressed, true);
  assert.ok(!('usageTabId' in state.storage));
  // Next alarms stay quiet: no tab pileup, no churn.
  await listeners.alarm({name: 'usage-refresh'});
  assert.equal(state.createdTabs.length, 0);
});

test('repurposed tab suppresses without closing user destination', async () => {
  reset({alarm: {name: 'usage-refresh'},
    tab: {id: 9, url: 'https://example.com/'}, storage: {usageTabId: 9}});
  await listeners.alarm({name: 'usage-refresh'});
  assert.deepEqual(state.removedTabs, []);
  assert.equal(state.createdTabs.length, 0);
  assert.equal(state.storage.tabSuppressed, true);
});

test('icon click clears suppression and opens a fresh tab', async () => {
  reset({alarm: {name: 'usage-refresh'},
    tab: null, storage: {usageTabId: 8, tabSuppressed: true}});
  await listeners.clicked();
  assert.equal(state.createdTabs.length, 1);
  assert.ok(!('tabSuppressed' in state.storage));
  assert.equal(state.storage.usageTabId, state.createdTabs[0].id);
});

test('startup resumes even when previously suppressed', async () => {
  reset({alarm: {name: 'usage-refresh'},
    tab: null, storage: {tabSuppressed: true}});
  await listeners.startup();
  assert.equal(state.createdTabs.length, 1);
  assert.ok(!('tabSuppressed' in state.storage));
});
