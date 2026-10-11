"""Last successful quota values only; cached values are never fresh samples."""
from __future__ import annotations

import copy
import json
import math
import time
from pathlib import Path


def _windows(data, keys, field):
    result = {}
    if not isinstance(data, dict): return result
    for key in keys:
        window = data.get(key) or {}
        if not isinstance(window, dict): continue
        value = window.get(field)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 100:
            continue
        reset = window.get('resets_at')
        if reset is not None:
            import monitor as m
            epoch = m.iso_to_epoch(reset) if isinstance(reset, str) else reset
            if isinstance(epoch, bool) or not isinstance(epoch, (int, float)) or not math.isfinite(epoch) or not 0 < epoch <= 253402300799:
                continue
        result[key] = {field: value, 'resets_at': reset}
    return result


def apply(codex: dict, claude: dict, path: Path, now=None):
    codex, claude = copy.deepcopy(codex), copy.deepcopy(claude)
    now = time.time() if now is None else now
    try:
        saved = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(saved, dict): saved = {}
    except (OSError, ValueError):
        saved = {}
    dirty = False
    for name, data, source, keys, field, fresh in (
        ('codex', codex, 'rate_limits', ('primary', 'secondary'), 'used_percent', codex.get('has_rate') and codex.get('usage_status') == 'ok'),
        ('claude', claude, 'oauth', ('five_hour', 'seven_day', 'seven_day_opus', 'seven_day_sonnet'), 'utilization', (claude.get('oauth') or {}).get('status') == 'ok'),
    ):
        windows = _windows(data.get(source) or {}, keys, field)
        if data.get('quota_source') == 'statusline' and fresh:
            # Export observations are not a newly polled sample. Keep their time.
            continue
        if fresh and all(k in windows for k in keys[:2]):
            saved[name] = {'windows': windows, 'observed_at': now}
            data['observed_at'] = now
            dirty = True
        elif not fresh:
            previous = saved.get(name) or {}
            if not isinstance(previous, dict): continue
            old = _windows(previous.get('windows') or {}, keys, field)
            observed = previous.get('observed_at')
            if all(k in old for k in keys[:2]) and isinstance(observed, (int, float)) and math.isfinite(observed):
                failure = data.get(source) or {}
                data['quota_cached'] = True
                data['observed_at'] = observed
                data[source] = old
                if name == 'codex':
                    data['has_rate'] = True
                else:
                    data['quota_source'] = previous.get('quota_source', 'legacy_cache')
                    data['fetch_status'] = failure.get('status')
                    data['fetch_detail'] = failure.get('detail')
                    data[source]['status'] = 'ok'
    if dirty:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix('.tmp')
            temporary.write_text(json.dumps(saved), encoding='utf-8')
            temporary.replace(path)
        except OSError:
            pass
    return codex, claude


def label(used, reset, observed, source=None):
    import monitor as m
    epoch = m.iso_to_epoch(reset) if isinstance(reset, str) else reset
    expired = '・リセット前の参考値' if m.is_stale(epoch) else ''
    note = 'Claude Code利用時の観測値' if source == 'statusline' else '更新失敗'
    return f'残り{100-used:.0f}%（前回取得値{expired}）\n取得日時: {m.fmt_ts(observed)}・{note}'
