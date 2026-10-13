const HOST = 'com.neoenox.usage_monitor';
const USAGE_URL = 'https://claude.ai/settings/usage';
function isUsage(url) {
  try {
    const u = new URL(url);
    return u.origin === 'https://claude.ai' && (u.pathname === '/settings/usage' || (u.pathname === '/new' && u.hash === '#settings/usage'));
  } catch { return false; }
}
async function status(ok, text) {
  await chrome.action.setBadgeText({text: ok ? 'OK' : '!'});
  await chrome.action.setBadgeBackgroundColor({color: ok ? '#207342' : '#a35b00'});
  await chrome.action.setTitle({title: text});
}
function validateSample(sample) {
  const clean = {rate_limits: {}};
  for (const key of ['five_hour', 'seven_day']) {
    const w = sample?.rate_limits?.[key];
    if (!w || typeof w.used_percentage !== 'number' || !Number.isFinite(w.used_percentage) || w.used_percentage < 0 || w.used_percentage > 100
        || typeof w.resets_at !== 'number' || !Number.isFinite(w.resets_at) || w.resets_at <= 0 || w.resets_at > 253402300799) {
      return null;
    }
    clean.rate_limits[key] = {used_percentage: w.used_percentage, resets_at: w.resets_at};
  }
  return clean;
}
function isLoginWall(url) {
  // Our own dead-end: the tracked tab bounced to the login page. Safe to drop,
  // unlike an arbitrary user destination which must be left alone.
  try {
    const u = new URL(url);
    return u.origin === 'https://claude.ai' && u.pathname === '/login';
  } catch { return false; }
}
function decideRefresh(tab) {
  // Pure decision for tests: never reload a repurposed destination.
  if (!tab) return 'create';
  if (isUsage(tab.url)) return 'reload';
  return 'recreate';
}
chrome.runtime.onMessage.addListener((message, sender, reply) => {
  if (sender.id !== chrome.runtime.id || sender.frameId !== 0 || !isUsage(sender.url)) return;
  if (message?.type === 'parse_state') {
    if (message.ok) return;
    status(false, `使用状況を読み取れません(${message.reason || 'unknown'}) ${new Date().toLocaleTimeString()}`);
    reply({ok: true});
    return;
  }
  if (message?.type !== 'quota') return;
  const clean = validateSample(message.sample);
  if (!clean) { reply({ok: false}); return; }
  chrome.runtime.sendNativeMessage(HOST, clean, response => {
    const error = chrome.runtime.lastError;
    const ok = !error && response?.ok === true;
    status(ok, ok ? `Usage Monitorへ反映済み ${new Date().toLocaleTimeString()}` : 'Usage Monitorのブラウザ連携を設定してください');
    reply({ok});
  });
  return true;
});
async function openFreshUsageTab() {
  const tab = await chrome.tabs.create({url: USAGE_URL, active: false, pinned: true});
  await chrome.storage.local.set({usageTabId: tab.id});
  await status(false, 'Claude使用状況を確認中。ログイン画面の場合はログインしてください');
}
async function refreshUsage() {
  const {usageTabId} = await chrome.storage.local.get('usageTabId');
  if (Number.isInteger(usageTabId)) {
    const tab = await chrome.tabs.get(usageTabId).catch(() => null);
    const action = decideRefresh(tab);
    if (action === 'reload') {
      await chrome.tabs.reload(usageTabId); return;
    }
    if (action === 'recreate') {
      // User repurposed our tab: leave their destination alone, track a new one.
      // Only our own login-wall dead-end is closed to avoid pinned-tab pileup.
      if (isLoginWall(tab.url)) {
        await chrome.tabs.remove(usageTabId).catch(() => null);
      }
      await chrome.storage.local.remove('usageTabId');
    }
  }
  await openFreshUsageTab();
}
chrome.action.onClicked.addListener(async () => {
  await chrome.storage.local.remove('usageTabId');
  await refreshUsage();
});
async function ensureAlarm() {
  // Alarms may not survive sessions alone; re-check on every worker start.
  try {
    const existing = await chrome.alarms.get('usage-refresh');
    if (!existing) await chrome.alarms.create('usage-refresh', {periodInMinutes: 5});
  } catch {}
}
chrome.runtime.onInstalled.addListener(async () => {
  await ensureAlarm();
  await refreshUsage();
});
chrome.runtime.onStartup.addListener(async () => {
  await ensureAlarm();
  await refreshUsage();
});
ensureAlarm();
chrome.alarms.onAlarm.addListener(alarm => { if (alarm.name === 'usage-refresh') refreshUsage(); });
if (typeof module !== 'undefined') module.exports = {isUsage, isLoginWall, validateSample, decideRefresh, ensureAlarm};
