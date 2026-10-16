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
chrome.runtime.onMessage.addListener((message, sender, reply) => {
  if (sender.id !== chrome.runtime.id || sender.frameId !== 0 || !isUsage(sender.url) || message?.type !== 'quota') return;
  const clean = {rate_limits: {}};
  for (const key of ['five_hour', 'seven_day']) {
    const w = message.sample?.rate_limits?.[key];
    if (!w || typeof w.used_percentage !== 'number' || !Number.isFinite(w.used_percentage) || w.used_percentage < 0 || w.used_percentage > 100
        || typeof w.resets_at !== 'number' || !Number.isFinite(w.resets_at) || w.resets_at <= 0 || w.resets_at > 253402300799) {
      reply({ok: false}); return;
    }
    clean.rate_limits[key] = {used_percentage: w.used_percentage, resets_at: w.resets_at};
  }
  chrome.runtime.sendNativeMessage(HOST, clean, response => {
    const error = chrome.runtime.lastError;
    const ok = !error && response?.ok === true;
    status(ok, ok ? `Usage Monitorへ反映済み ${new Date().toLocaleTimeString()}` : 'Usage Monitorのブラウザ連携を設定してください');
    reply({ok});
  });
  return true;
});
async function refreshUsage() {
  const {usageTabId} = await chrome.storage.local.get('usageTabId');
  if (Number.isInteger(usageTabId)) {
    const tab = await chrome.tabs.get(usageTabId).catch(() => null);
    if (tab && isUsage(tab.url)) {
      await chrome.tabs.reload(usageTabId); return;
    }
    if (tab) {
      // User navigated our tab elsewhere: never reload their new destination.
      await status(false, '使用状況タブを開くには拡張アイコンをクリックしてください');
      return;
    }
  }
  const tab = await chrome.tabs.create({url: USAGE_URL, active: false, pinned: true});
  await chrome.storage.local.set({usageTabId: tab.id});
  await status(false, 'Claude使用状況を確認中。ログイン画面の場合はログインしてください');
}
chrome.action.onClicked.addListener(async () => {
  await chrome.storage.local.remove('usageTabId');
  await refreshUsage();
});
chrome.runtime.onInstalled.addListener(async () => {
  await chrome.alarms.create('usage-refresh', {periodInMinutes: 5});
  await refreshUsage();
});
chrome.runtime.onStartup.addListener(refreshUsage);
chrome.alarms.onAlarm.addListener(alarm => { if (alarm.name === 'usage-refresh') refreshUsage(); });
