(() => {
  // The hash route is required because Chrome match patterns cannot match hashes.
  if (!(location.pathname === '/settings/usage' || (location.pathname === '/new' && location.hash === '#settings/usage'))) return;
  let sent = false;
  let sending = false;
  let timer;
  let lastFailureReport = 0;
  let lastFailureReason = '';
  async function reportFailure(reason) {
    const now = Date.now();
    if (reason === lastFailureReason && now - lastFailureReport < 60000) return;
    lastFailureReason = reason;
    lastFailureReport = now;
    await chrome.runtime.sendMessage({type: 'parse_state', ok: false, reason}).catch(() => null);
  }
  async function collect() {
    if (!(location.pathname === '/settings/usage' || (location.pathname === '/new' && location.hash === '#settings/usage'))) return;
    const rows = UsageMonitorParser.readRows(document);
    const sample = UsageMonitorParser.parseRows(rows);
    if (!sample) {
      if (!sent && !sending) await reportFailure(rows.length ? 'parse_null' : 'no_rows');
      return;
    }
    if (sent || sending) return;
    sending = true;
    const response = await chrome.runtime.sendMessage({type: 'quota', sample}).catch(() => null);
    sending = false;
    if (response?.ok) {
      sent = true;
      observer.disconnect();
      clearInterval(timer);
    }
  }
  const observer = new MutationObserver(() => { collect(); });
  observer.observe(document.documentElement, {subtree: true, childList: true, attributes: true, attributeFilter: ['aria-valuenow']});
  timer = setInterval(collect, 10000);
  collect();
})();
