const {test} = require('node:test');
const assert = require('node:assert/strict');
const p = require('../browser-extension/parser.js');
const now = new Date(2026, 9, 11, 9, 0);
const rows = [
  {label:'現在のセッション',used:13,resetText:'13:30にリセットされます'},
  {label:'今週',used:88,resetText:'6:00 (火曜日)にリセット'},
  {label:'Claude Code',used:100,resetText:''},
];
test('observed Japanese usage page, not product breakdown', () => {
  const result = p.parseRows(rows, now).rate_limits;
  assert.equal(result.five_hour.used_percentage, 13);
  assert.equal(result.seven_day.used_percentage, 88);
  assert.equal(result.five_hour.resets_at, new Date(2026,9,11,13,30).getTime()/1000);
  assert.equal(result.seven_day.resets_at, new Date(2026,9,13,6).getTime()/1000);
});
test('night rollover and same weekday next week', () => {
  assert.equal(p.resetEpoch('1:00にリセット',false,new Date(2026,9,11,23)),new Date(2026,9,12,1).getTime()/1000);
  assert.equal(p.resetEpoch('6:00 (日曜日)にリセット',true,now),new Date(2026,9,18,6).getTime()/1000);
});
test('loading, duplicate and changed UI fail closed', () => {
  assert.equal(p.parseRows([],now),null);
  assert.equal(p.parseRows([...rows,rows[0]],now),null);
  assert.equal(p.parseRows([{...rows[0],used:NaN},rows[1]],now),null);
  assert.equal(p.resetEpoch('課金13:30',false,now),null);
  assert.equal(p.resetEpoch('23:99にリセット',false,now),null);
  assert.equal(p.resetEpoch('20:00にリセット',false,now),null);
  assert.equal(p.resetEpoch('6:00にリセット',true,now),null);
});
