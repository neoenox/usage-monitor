"""Explicit opt-in, reversible configuration of Claude's numeric export."""
from __future__ import annotations
import json
from pathlib import Path


def _load(target):
    if not target.exists():
        return {}
    data = json.loads(target.read_text(encoding='utf-8'))
    if not isinstance(data, dict):
        raise ValueError('設定JSONがオブジェクトではありません')
    return data


def _write(target, data):
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_suffix(target.suffix + '.tmp')
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    temp.replace(target)


def _backup(target):
    return target.with_name('usage-monitor-statusline-backup.json')


def install(target: Path, command: str, *, consent=False, replace_existing=False):
    if not consent:
        raise ValueError('使用率・リセット日時のローカル保存への同意が必要です')
    data = _load(target)
    backup = _backup(target)
    status = {'type': 'command', 'command': command}
    if backup.exists():
        if data.get('statusLine') == status:
            return
        record = _load(backup)
        unchanged = ('statusLine' in data) == record.get('had_statusline') and data.get('statusLine') == record.get('previous')
        if not unchanged or record.get('installed') != status:
            raise ValueError('保存済みの設定を復元してから再設定してください')
        # Previous write failed before installation; keep the original backup.
        if 'statusLine' in data and not replace_existing:
            raise ValueError('既存statuslineの置換同意が必要です')
        data['statusLine'] = status
        _write(target, data)
        return
    if 'statusLine' in data and not replace_existing:
        raise ValueError('既存statuslineがあります。明示的な置換同意が必要です')
    _write(backup, {'had_statusline': 'statusLine' in data, 'previous': data.get('statusLine'), 'installed': status})
    data['statusLine'] = status
    _write(target, data)


def restore(target: Path):
    backup = _backup(target)
    previous = _load(backup)
    if not previous:
        raise ValueError('復元用バックアップがありません')
    data = _load(target)
    unchanged = ('statusLine' in data) == previous['had_statusline'] and data.get('statusLine') == previous['previous']
    if data.get('statusLine') != previous['installed'] and not unchanged:
        raise ValueError('statuslineが後から変更されています。上書きしません')
    if previous['had_statusline']:
        data['statusLine'] = previous['previous']
    else:
        data.pop('statusLine', None)
    _write(target, data)
    # Verify exact target before removing only our restoration record.
    expected = target.parent.resolve() / 'usage-monitor-statusline-backup.json'
    if backup.resolve() != expected:
        raise ValueError('バックアップパスが一致しません')
    backup.unlink()
