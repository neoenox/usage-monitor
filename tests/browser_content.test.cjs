const {test} = require('node:test');
const assert = require('node:assert/strict');

// browser-extension/content.js のテスト。
//
// content.js は拡張機能で唯一テストが無かったモジュール (ルート判定 /
// 一度だけ送るガード / 同じ理由の失敗レポートの60秒抑止)。IIFEで即実行され
// 何もexportしないため、chrome・MutationObserver・setInterval をスタブして
// 観測した挙動で固定する。ページ読み取りは本物の parser.js を通すので、
// 未テストだった readRows もここで動く (parseRows 単体は browser_parser.test.cjs)。
const CONTENT = require.resolve('../browser-extension/content.js');
const PARSER = require('../browser-extension/parser.js');
const REAL_DATE_NOW = Date.now;

// --- 小さなDOMスタブ -------------------------------------------------------
// readRows が見るのはこれだけ: [role="meter"][aria-valuenow] / aria-labelledby
// が指すラベル要素 / meter.parentElement / その中の [role="meter"] 件数と span。
function meter(id, label, value, reset) {
  const meterNode = {
    getAttribute: (name) => (name === 'aria-labelledby' ? id
      : name === 'aria-valuenow' ? String(value) : null),
    parentElement: null,
  };
  meterNode.parentElement = {
    querySelectorAll: (selector) =>
      (selector === '[role="meter"]' ? [meterNode] : [{textContent: reset}]),
    parentElement: null,
  };
  return {meterNode, id, label};
}

// リセット時刻は「今から1時間後」を24時間表記で書く (parser の許容範囲内)。
// 週次の行は曜日が必須 (parseRows が曜日を要求する) なので、その日の曜日を付ける。
function resetText({weekly = false} = {}) {
  const days = ['日', '月', '火', '水', '木', '金', '土'];
  const t = new Date(REAL_DATE_NOW() + 60 * 60 * 1000);
  const clock = `${String(t.getHours()).padStart(2, '0')}:${String(t.getMinutes()).padStart(2, '0')}`;
  return weekly ? `${days[t.getDay()]}曜日に${clock}にリセット` : `${clock}にリセット`;
}

const fiveHour = () => meter('lbl-5h', '現在のセッション', 20, resetText());
const week = () => meter('lbl-wk', '今週', 40, resetText({weekly: true}));

// --- content.js のロード ---------------------------------------------------
// スタブは全テストで load() 経由で入れ替える。timer のスタブは load 後に戻さ
// ない: content.js は成功時に clearInterval(timer) を後から呼ぶため、本物の
// clearInterval にダミーハンドルを渡すと例外になる。
async function flush() {
  await new Promise((resolve) => setImmediate(resolve));
  await new Promise((resolve) => setImmediate(resolve));
}

function load({pathname = '/settings/usage', hash = '', meters = [],
               respond = async () => ({ok: true}), now} = {}) {
  const messages = [];
  const seen = {observed: 0, disconnected: 0, intervals: 0, cleared: 0, intervalMs: null};
  let mutationCallback = null;

  globalThis.location = {pathname, hash};
  // 配列を直接見るので、テストが後から行を追加するとDOMも追随する。
  globalThis.document = {
    documentElement: {},
    querySelectorAll: () => meters.map((m) => m.meterNode),
    getElementById: (id) => {
      const entry = meters.find((m) => m.id === id);
      return entry ? {textContent: entry.label} : null;
    },
  };
  globalThis.UsageMonitorParser = PARSER;
  globalThis.chrome = {
    runtime: {
      sendMessage: async (message) => {
        messages.push(message);
        return respond(message);
      },
    },
  };
  globalThis.MutationObserver = class {
    constructor(callback) { mutationCallback = callback; }
    observe() { seen.observed++; }
    disconnect() { seen.disconnected++; }
  };
  globalThis.setInterval = (fn, ms) => { seen.intervals++; seen.intervalMs = ms; return {fake: true}; };
  globalThis.clearInterval = () => { seen.cleared++; };
  Date.now = typeof now === 'function' ? now : (now === undefined ? REAL_DATE_NOW : () => now);

  delete require.cache[CONTENT];
  require(CONTENT);
  return {messages, seen, trigger: () => mutationCallback()};
}

// --- ルート判定 -------------------------------------------------------------

test('a page without the usage route never reports or polls', async () => {
  const ctx = load({pathname: '/new', hash: ''});
  await flush();

  assert.deepEqual(ctx.messages, []);
  assert.equal(ctx.seen.observed, 0);    // observer も作られない
  assert.equal(ctx.seen.intervals, 0);   // interval も張られない
  assert.equal(ctx.seen.cleared, 0);
});

test('the usage route is accepted directly and through the hash route', async () => {
  const direct = load({pathname: '/settings/usage', meters: [fiveHour(), week()]});
  await flush();
  assert.equal(direct.messages.length, 1);
  assert.equal(direct.messages[0].type, 'quota');
  assert.deepEqual(Object.keys(direct.messages[0].sample.rate_limits).sort(),
    ['five_hour', 'seven_day']);

  const hashed = load({pathname: '/new', hash: '#settings/usage', meters: [fiveHour(), week()]});
  await flush();
  assert.equal(hashed.messages.length, 1);
  assert.equal(hashed.messages[0].type, 'quota');
});

test('navigating away from the usage route stops the collection', async () => {
  const ctx = load({meters: [fiveHour(), week()], respond: async () => ({ok: false})});
  await flush();
  assert.equal(ctx.messages.length, 1);

  globalThis.location = {pathname: '/dashboard', hash: ''};
  ctx.trigger();
  await flush();
  assert.equal(ctx.messages.length, 1);  // ルートを外れたら何も送らない
});

// --- 一度だけ送る -----------------------------------------------------------

test('a successful send stops polling and never repeats', async () => {
  const ctx = load({meters: [fiveHour(), week()]});
  await flush();
  assert.equal(ctx.messages.length, 1);
  assert.equal(ctx.seen.observed, 1);
  assert.equal(ctx.seen.intervalMs, 10000);  // 10秒ポーリング
  assert.equal(ctx.seen.disconnected, 1);
  assert.equal(ctx.seen.cleared, 1);

  ctx.trigger();                             // 観測コールバックからの再収集
  await flush();
  assert.equal(ctx.messages.length, 1);
});

test('a response that is not ok leaves the sender free to retry', async () => {
  let ok = false;
  const ctx = load({meters: [fiveHour(), week()],
    respond: async () => (ok ? {ok: true} : {ok: false})});
  await flush();
  assert.equal(ctx.messages.length, 1);

  ok = true;
  ctx.trigger();
  await flush();
  assert.equal(ctx.messages.length, 2);      // 失敗応答では sent が立たない
  assert.equal(ctx.seen.disconnected, 1);    // 2回目で成功して停止
});

test('an in-flight send is not duplicated', async () => {
  let release;
  const pending = new Promise((resolve) => { release = resolve; });
  const ctx = load({meters: [fiveHour(), week()], respond: () => pending});
  await flush();
  assert.equal(ctx.messages.length, 1);

  ctx.trigger();
  await flush();
  assert.equal(ctx.messages.length, 1);      // sending 中は再送しない

  release({ok: true});
  await flush();
  assert.equal(ctx.seen.disconnected, 1);
});

test('a rejected sendMessage is tolerated and retried later', async () => {
  let fail = true;
  const ctx = load({meters: [fiveHour(), week()],
    respond: async () => {
      if (fail) throw new Error('receiving end does not exist');
      return {ok: true};
    }});
  await flush();
  assert.equal(ctx.messages.length, 1);
  assert.equal(ctx.seen.disconnected, 0);

  fail = false;
  ctx.trigger();
  await flush();
  assert.equal(ctx.messages.length, 2);
  assert.equal(ctx.seen.disconnected, 1);
});

// --- 失敗レポート -----------------------------------------------------------

test('a page without rows reports no_rows once and throttles for a minute', async () => {
  const ctx = load({meters: [], now: REAL_DATE_NOW()});
  await flush();
  assert.deepEqual(ctx.messages, [{type: 'parse_state', ok: false, reason: 'no_rows'}]);

  ctx.trigger();                             // 同じ理由を1分以内に再送しない
  await flush();
  assert.equal(ctx.messages.length, 1);
});

test('the same failure stays silent just inside the throttle window', async () => {
  let now = REAL_DATE_NOW();
  const ctx = load({meters: [], now: () => now});
  await flush();
  assert.equal(ctx.messages.length, 1);

  now += 59999;                              // 1分の直前はまだ黙っている
  ctx.trigger();
  await flush();
  assert.equal(ctx.messages.length, 1);
});

test('the same failure is reported again after the throttle window', async () => {
  let now = REAL_DATE_NOW();
  const ctx = load({meters: [], now: () => now});
  await flush();
  assert.equal(ctx.messages.length, 1);

  now += 60000;                              // 1分経過
  ctx.trigger();
  await flush();
  assert.equal(ctx.messages.length, 2);
  assert.deepEqual(ctx.messages[1], {type: 'parse_state', ok: false, reason: 'no_rows'});
});

test('a different failure reason is reported without waiting', async () => {
  const meters = [];
  const ctx = load({meters, now: REAL_DATE_NOW()});  // 時計は固定 = 同一理由なら抑止される
  await flush();
  assert.deepEqual(ctx.messages, [{type: 'parse_state', ok: false, reason: 'no_rows'}]);

  meters.push(fiveHour());                   // 週次の行が無い → parseRows は null
  ctx.trigger();
  await flush();
  assert.equal(ctx.messages.length, 2);
  assert.equal(ctx.messages[1].reason, 'parse_null');
});

test('a page that starts empty keeps polling until the sample parses', async () => {
  const meters = [];
  const ctx = load({meters});
  await flush();
  assert.equal(ctx.messages.length, 1);      // no_rows
  assert.equal(ctx.seen.cleared, 0);         // まだ停止していない
  assert.equal(ctx.seen.disconnected, 0);

  meters.push(fiveHour(), week());           // UI が描画された
  ctx.trigger();
  await flush();
  assert.equal(ctx.messages.length, 2);
  const quota = ctx.messages[1];
  assert.equal(quota.type, 'quota');
  assert.equal(quota.sample.rate_limits.five_hour.used_percentage, 20);
  assert.equal(quota.sample.rate_limits.seven_day.used_percentage, 40);
  assert.ok(quota.sample.rate_limits.five_hour.resets_at > 0);
  assert.equal(ctx.seen.disconnected, 1);
  assert.equal(ctx.seen.cleared, 1);
});
