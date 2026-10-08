"""Credential-free boundary for documented Claude Code statusline quota JSON."""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import time

WINDOWS = {'five_hour': 'five_hour', 'seven_day': 'seven_day'}


def path(home: Path | None = None) -> Path:
    if home is not None:
        return home / '.claude' / 'usage-monitor-quota.json'
    return Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'usage-monitor' / 'claude-quota.json'


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def export(data: dict, target: Path, now: float | None = None) -> None:
    """Whitelist numbers only; never persist the input JSON or credentials."""
    result = {'observed_at': time.time() if now is None else now, 'windows': {}}
    limits = data.get('rate_limits') if isinstance(data, dict) else None
    if isinstance(limits, dict):
        for key in WINDOWS:
            window = limits.get(key)
            if not isinstance(window, dict):
                continue
            used, reset = window.get('used_percentage'), window.get('resets_at')
            if _number(used) and 0 <= used <= 100 and _number(reset) and reset > 0:
                result['windows'][key] = {'utilization': float(used), 'resets_at': float(reset)}
    target.parent.mkdir(parents=True, exist_ok=True)
    import tempfile
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=target.parent,
                                     prefix=target.name + '.', suffix='.tmp', delete=False) as stream:
        temp = Path(stream.name)
        stream.write(json.dumps(result, allow_nan=False))
    try:
        temp.replace(target)
    finally:
        # Only remove our unique staging file in the verified destination directory.
        if temp.parent.resolve() == target.parent.resolve():
            temp.unlink(missing_ok=True)


def read(target: Path) -> dict:
    try:
        data = json.loads(target.read_text(encoding='utf-8'))
        observed = data.get('observed_at')
        if not _number(observed) or observed <= 0:
            return {'status': 'missing_token'}
        windows = data.get('windows') or {}
        result = {'status': 'ok', 'observed_at': observed}
        for key in WINDOWS:
            window = windows.get(key)
            if not isinstance(window, dict):
                continue
            used, reset = window.get('utilization'), window.get('resets_at')
            if _number(used) and 0 <= used <= 100 and _number(reset) and reset > 0:
                # Existing renderers accept ISO reset times.
                from datetime import datetime, timezone
                result[key] = {'utilization': used, 'resets_at': datetime.fromtimestamp(reset, timezone.utc).isoformat()}
        return result if any(key in result for key in WINDOWS) else {'status': 'missing_token'}
    except (OSError, ValueError, TypeError, AttributeError, OverflowError):
        return {'status': 'missing_token'}


def main() -> None:
    import sys
    try:
        export(json.load(sys.stdin), path())
    except (OSError, ValueError, TypeError):
        pass  # Never print session input/errors into a user's statusline.


if __name__ == '__main__':
    main()
