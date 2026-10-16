(() => {
  // The hash route is required because Chrome match patterns cannot match hashes.
  if (!(location.pathname === '/settings/usage' || (location.pathname === '/new' && location.hash === '#settings/usage'))) return;
  let sent = false;
  let sending = false;
  let timer;
  async function collect() {
    if (!(location.pathname === '/settings/usage' || (location.pathname === '/new' && location.hash === '#settings/usage'))) return;
    const sample = UsageMonitorParser.parseRows(UsageMonitorParser.readRows(document));
    if (!sample || sent || sending) return;
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
