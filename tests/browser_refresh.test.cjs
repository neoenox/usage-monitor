const {test} = require('node:test');
const assert = require('node:assert/strict');

// Minimal chrome stub so background.js top-level listeners can attach.
const listeners = {};
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
  storage: {local: {get: async () => ({}), set: async () => {}, remove: async () => {}}},
  tabs: {get: async () => null, reload: async () => {}, create: async () => ({id: 1})},
  alarms: {
    _existing: null, _created: 0, _lastOptions: null,
    get: async function () { return this._existing; },
    create: async function (name, options) {
      this._created++;
      this._lastOptions = options;
      this._existing = {name};
    },
    onAlarm: {addListener: (fn) => { listeners.alarm = fn; }},
  },
};
const bg = require('../browser-extension/background.js');

test('usage tab reloads, repurposed tab recreates, missing tab creates', () => {
  assert.equal(bg.decideRefresh(null), 'create');
  assert.equal(bg.decideRefresh({url: 'https://claude.ai/settings/usage'}), 'reload');
  assert.equal(bg.decideRefresh({url: 'https://claude.ai/new#settings/usage'}), 'reload');
  assert.equal(bg.decideRefresh({url: 'https://example.com/'}), 'recreate');
  assert.equal(bg.decideRefresh({url: 'chrome://newtab/'}), 'recreate');
});

test('login wall is droppable, user destinations are not', () => {
  assert.equal(bg.isLoginWall('https://claude.ai/login?from=logout&reauth=1'), true);
  assert.equal(bg.isLoginWall('https://claude.ai/settings/usage'), false);
  assert.equal(bg.isLoginWall('https://claude.ai/new'), false);
  assert.equal(bg.isLoginWall('https://example.com/'), false);
  assert.equal(bg.isLoginWall('not a url'), false);
});

test('sample validation keeps numbers only', () => {
  const good = {rate_limits: {
    five_hour: {used_percentage: 13, resets_at: 2000003600},
    seven_day: {used_percentage: 88, resets_at: 2000172800}}};
  assert.deepEqual(bg.validateSample(good), good);
  assert.equal(bg.validateSample({rate_limits: {}}), null);
  const bad = structuredClone(good);
  bad.rate_limits.five_hour.used_percentage = 101;
  assert.equal(bg.validateSample(bad), null);
  const evil = {...structuredClone(good), secret: 'NEVER'};
  assert.ok(!('secret' in bg.validateSample(evil)));
});

test('parse_state listener is registered alongside quota', () => {
  assert.equal(typeof listeners.message, 'function');
});

test('missing alarm is recreated, existing alarm is untouched', async () => {
  globalThis.chrome.alarms._existing = null;
  globalThis.chrome.alarms._created = 0;
  globalThis.chrome.alarms._lastOptions = null;
  await bg.ensureAlarm();
  assert.equal(globalThis.chrome.alarms._created, 1);
  globalThis.chrome.alarms._existing = {name: 'usage-refresh'};
  await bg.ensureAlarm();
  assert.equal(globalThis.chrome.alarms._created, 1);
});

test('alarm requests cross-session persistence without duplicating', async () => {
  globalThis.chrome.alarms._existing = null;
  globalThis.chrome.alarms._created = 0;
  globalThis.chrome.alarms._lastOptions = null;
  await bg.ensureAlarm();
  await bg.ensureAlarm();
  assert.equal(globalThis.chrome.alarms._created, 1);
  assert.equal(globalThis.chrome.alarms._lastOptions.persistAcrossSessions, true);
  assert.equal(globalThis.chrome.alarms._lastOptions.periodInMinutes, 5);
});
