// Only the usage settings DOM is read. No private API or cookie access.
(function (root) {
  function resetEpoch(text, weekly, now = new Date()) {
    const clock = text.match(/(\d{1,2}):(\d{2})/);
    if (!clock || !/リセット/.test(text)) return null;
    const hour = Number(clock[1]), minute = Number(clock[2]);
    if (hour > 23 || minute > 59) return null;
    const result = new Date(now);
    result.setHours(hour, minute, 0, 0);
    if (weekly) {
      const day = text.match(/([日月火水木金土])曜日/);
      if (!day) return null;
      const offset = ('日月火水木金土'.indexOf(day[1]) - result.getDay() + 7) % 7;
      result.setDate(result.getDate() + offset);
      if (result <= now) result.setDate(result.getDate() + 7);
      if (result - now > 7 * 86400000) return null;
    } else {
      if (result <= now) result.setDate(result.getDate() + 1);
      if (result - now > 5 * 3600000) return null;
    }
    return result.getTime() / 1000;
  }

  function parseRows(rows, now = new Date()) {
    const rate_limits = {};
    for (const [label, key, weekly] of [['現在のセッション', 'five_hour', false], ['今週', 'seven_day', true]]) {
      const matches = rows.filter(row => row.label === label);
      if (matches.length !== 1) return null;
      const row = matches[0];
      if (typeof row.used !== 'number' || !Number.isFinite(row.used) || row.used < 0 || row.used > 100) return null;
      const reset = resetEpoch(row.resetText, weekly, now);
      if (reset === null) return null;
      rate_limits[key] = {used_percentage: row.used, resets_at: reset};
    }
    return {rate_limits};
  }

  function readRows(doc) {
    const rows = [];
    for (const meter of doc.querySelectorAll('[role="meter"][aria-valuenow]')) {
      const label = doc.getElementById(meter.getAttribute('aria-labelledby'))?.textContent?.trim();
      if (!['現在のセッション', '今週'].includes(label)) continue;
      let row = meter.parentElement;
      for (let i = 0; row && i < 8; i++, row = row.parentElement) {
        if (row.querySelectorAll('[role="meter"]').length !== 1) break;
        const resetText = Array.from(row.querySelectorAll('span')).map(e => e.textContent.trim()).find(t => /リセット/.test(t));
        if (resetText) {
          const value = meter.getAttribute('aria-valuenow');
          rows.push({label, used: value === null || value.trim() === '' ? NaN : Number(value), resetText});
          break;
        }
      }
    }
    return rows;
  }
  const api = {resetEpoch, parseRows, readRows};
  if (typeof module !== 'undefined') module.exports = api;
  else root.UsageMonitorParser = api;
})(typeof globalThis === 'undefined' ? this : globalThis);
