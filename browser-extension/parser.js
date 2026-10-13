// Only the usage settings DOM is read. No private API or cookie access.
// Labels and reset wording accept Japanese and English UI.
(function (root) {
  function normalizeLabel(text) {
    return (text || '').trim().toLowerCase().replace(/\s+/g, ' ');
  }
  function labelKey(label) {
    const t = normalizeLabel(label);
    if (/現在のセッション|current session/.test(t)) return 'five_hour';
    if (t === '今週' || /this week|weekly|seven[- ]day|\bweek\b/.test(t)) return 'seven_day';
    return null;
  }
  const WEEKDAYS = [
    ['sunday', 'sun', '日'],
    ['monday', 'mon', '月'],
    ['tuesday', 'tue', 'tues', '火'],
    ['wednesday', 'wed', '水'],
    ['thursday', 'thu', 'thur', 'thurs', '木'],
    ['friday', 'fri', '金'],
    ['saturday', 'sat', '土'],
  ];
  function weekdayIndex(text) {
    const t = normalizeLabel(text);
    const ja = t.match(/([日月火水木金土])曜日?/);
    if (ja) return '日月火水木金土'.indexOf(ja[1]);
    for (let i = 0; i < WEEKDAYS.length; i++) {
      for (const name of WEEKDAYS[i]) {
        if (new RegExp(`\\b${name}\\b`).test(t)) return i;
      }
    }
    return -1;
  }
  function resetEpoch(text, weekly, now = new Date()) {
    if (!/リセット|reset/i.test(text)) return null;
    const clock = text.match(/(\d{1,2}):(\d{2})\s*([AP]\.?M\.?)?/i);
    if (!clock) return null;
    let hour = Number(clock[1]);
    const minute = Number(clock[2]);
    const ampm = (clock[3] || '').replace(/\./g, '').toLowerCase();
    if (ampm === 'am' || ampm === 'pm') {
      if (hour < 1 || hour > 12 || minute > 59) return null;
      if (ampm === 'am') hour = hour % 12;
      else hour = (hour % 12) + 12;
    } else if (hour > 23 || minute > 59) return null;
    const result = new Date(now);
    result.setHours(hour, minute, 0, 0);
    if (weekly) {
      const day = weekdayIndex(text);
      if (day < 0) return null;
      const offset = (day - result.getDay() + 7) % 7;
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
    const byKey = {five_hour: [], seven_day: []};
    for (const row of rows) {
      const key = row.key || labelKey(row.label);
      if (key && byKey[key]) byKey[key].push(row);
    }
    for (const [key, weekly] of [['five_hour', false], ['seven_day', true]]) {
      if (byKey[key].length !== 1) return null;
      const row = byKey[key][0];
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
      const key = labelKey(label);
      if (!key) continue;
      let row = meter.parentElement;
      for (let i = 0; row && i < 8; i++, row = row.parentElement) {
        if (row.querySelectorAll('[role="meter"]').length !== 1) break;
        const resetText = Array.from(row.querySelectorAll('span')).map(e => e.textContent.trim()).find(t => /リセット|reset/i.test(t));
        if (resetText) {
          const value = meter.getAttribute('aria-valuenow');
          rows.push({key, label, used: value === null || value.trim() === '' ? NaN : Number(value), resetText});
          break;
        }
      }
    }
    return rows;
  }
  const api = {resetEpoch, parseRows, readRows, labelKey, normalizeLabel};
  if (typeof module !== 'undefined') module.exports = api;
  else root.UsageMonitorParser = api;
})(typeof globalThis === 'undefined' ? this : globalThis);
