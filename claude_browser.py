"""Numeric-only import and Chrome native messaging boundary; no auth access."""
from __future__ import annotations

import json
from pathlib import Path
import struct
import sys

import claude_export

HOST = 'com.neoenox.usage_monitor'
MAX_MESSAGE = 4096
DEFAULT_EXTENSION_ID = 'eobplfaccjbfdlolmdjnalbedehgljjl'
_CHROME_EPOCH_OFFSET = 11644473600  # seconds between 1601-01-01 and 1970-01-01


def _chrome_time_to_unix(value):
    """Convert a Chrome/WebKit timestamp (µs since 1601) to Unix seconds."""
    try:
        return int(value) / 1_000_000 - _CHROME_EPOCH_OFFSET
    except (TypeError, ValueError):
        return None


def path(home: Path | None = None) -> Path:
    return claude_export.path(home).with_name('claude-browser-quota.json')


def import_usage(data, target: Path, now=None):
    limits = data.get('rate_limits') if isinstance(data, dict) else None
    if not isinstance(limits, dict):
        raise ValueError('Missing rate limits')
    clean = {}
    for key in claude_export.WINDOWS:
        window = limits.get(key)
        if not isinstance(window, dict):
            raise ValueError('Both windows required')
        used, reset = window.get('used_percentage'), window.get('resets_at')
        if (not claude_export._number(used) or not 0 <= used <= 100
                or not claude_export._number(reset) or not 0 < reset <= 253402300799):
            raise ValueError('Invalid numeric quota')
        clean[key] = {'used_percentage': used, 'resets_at': reset}
    claude_export.export({'rate_limits': clean}, target, now=now)


def latest(home=None):
    candidates = [(claude_export.read(claude_export.path(home)), 'statusline'),
                  (claude_export.read(path(home)), 'browser')]
    return max(candidates, key=lambda item: item[0].get('observed_at', 0))


def _read_exact(stream, size):
    chunks = bytearray()
    while len(chunks) < size:
        chunk = stream.read(size - len(chunks))
        if not chunk:
            raise ValueError('Incomplete native message')
        chunks.extend(chunk)
    return bytes(chunks)


def serve(source, destination, target: Path):
    try:
        length = struct.unpack('<I', _read_exact(source, 4))[0]
        if not 0 < length <= MAX_MESSAGE:
            raise ValueError('Native message too large')
        data = json.loads(_read_exact(source, length))
        import_usage(data, target)
        reply = {'ok': True}
    except (OSError, ValueError, TypeError, OverflowError):
        reply = {'ok': False, 'error': '使用率データを取り込めませんでした'}
    encoded = json.dumps(reply, ensure_ascii=True).encode('utf-8')
    destination.write(struct.pack('<I', len(encoded)) + encoded)
    destination.flush()


def main():
    if len(sys.argv) == 3 and sys.argv[1] == '--register':
        register(sys.argv[2])
        return
    if len(sys.argv) == 3 and sys.argv[1] == '--import':
        import_usage(json.loads(Path(sys.argv[2]).read_text(encoding='utf-8')), path())
        return
    # Chrome passes the allowed extension origin as argv[1]. The registered
    # manifest restricts the caller to our extension; no command execution API.
    if len(sys.argv) < 2 or not sys.argv[1].startswith('chrome-extension://'):
        raise SystemExit('Launch through the browser extension or use --import FILE')
    if sys.platform == 'win32':
        import msvcrt
        import os
        msvcrt.setmode(sys.stdin.fileno(), os.O_BINARY)
        msvcrt.setmode(sys.stdout.fileno(), os.O_BINARY)
    serve(sys.stdin.buffer, sys.stdout.buffer, path())


def extension_id() -> str:
    """Pinned extension ID; the manifest key keeps it stable across reloads."""
    try:
        here = Path(__file__).resolve().parent / 'browser-extension' / 'extension-id.txt'
        value = here.read_text(encoding='utf-8').strip()
        if value:
            return value
    except OSError:
        pass
    return DEFAULT_EXTENSION_ID


def host_exe() -> Path:
    """Locate the browser-host executable for the current run mode."""
    import sys
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).resolve().parent / 'usage-monitor-browser-host.exe'
    return Path(__file__).resolve().parent / 'dist' / 'usage-monitor-browser-host.exe'


def chrome_user_data() -> Path | None:
    """Default Chrome profile root. Overridable in tests via monkeypatch."""
    import os
    base = os.environ.get('LOCALAPPDATA')
    if not base:
        return None
    root = Path(base) / 'Google' / 'Chrome' / 'User Data'
    return root if root.exists() else None


def extension_state() -> dict:
    """Read-only check of our extension in local Chrome profiles.

    Reads only extension metadata (presence, disable reasons, last load
    time) from the browser's own settings files. Never touches cookies or
    credentials. Returns {'present': bool, 'disabled': bool, 'profiles': [...],
    'updated_at': unix|None} or {'present': None, ...} when Chrome data is
    unavailable. ``updated_at`` is when Chrome last loaded the extension, so a
    value older than a recent extension update means a reload is still pending.
    """
    import os
    result: dict = {'present': None, 'disabled': None, 'profiles': [], 'updated_at': None}
    try:
        root = chrome_user_data()
        if root is None:
            return result
        wanted = extension_id()
        present, disabled, profiles = False, False, []
        latest = None
        for profile in ('Default', 'Profile 2', 'Profile 3'):
            try:
                data = json.loads((root / profile / 'Secure Preferences').read_bytes().decode('utf-8'))
            except (OSError, ValueError):
                continue
            try:
                entry = (data.get('extensions') or {}).get('settings', {}).get(wanted)
            except AttributeError:
                continue
            if isinstance(entry, dict):
                present = True
                profiles.append(profile)
                reasons = entry.get('disable_reasons') or []
                if reasons:
                    disabled = True
                updated = _chrome_time_to_unix(entry.get('last_update_time'))
                if updated is not None:
                    latest = updated if latest is None else max(latest, updated)
        result.update(present=present, disabled=disabled if present else False,
                      profiles=profiles, updated_at=latest)
        return result
    except Exception:
        return result


def chrome_running() -> bool | None:
    """Best-effort check whether Chrome is running. None when unknown."""
    import subprocess
    try:
        if sys.platform == 'win32':
            out = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq chrome.exe', '/FO', 'CSV'],
                                 capture_output=True, text=True, timeout=10,
                                 creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            return 'chrome.exe' in (out.stdout or '').lower()
        return None
    except Exception:
        return None


def diagnose(home=None) -> dict:
    """Local-only health check for the browser quota path. Never raises."""
    import time
    result: dict = {'extension_id': extension_id(), 'chrome_running': chrome_running()}
    try:
        result['extension'] = extension_state()
    except Exception:
        result['extension'] = {'present': None, 'disabled': None, 'profiles': []}
    try:
        manifest = path().parent / 'browser-native-host.json'
        result['manifest_exists'] = manifest.exists()
        try:
            data = json.loads(manifest.read_text(encoding='utf-8')) if result['manifest_exists'] else {}
        except (OSError, ValueError):
            data = {}
        result['manifest_path'] = data.get('path') if isinstance(data, dict) else None
        result['manifest_path_exists'] = bool(result['manifest_path']) and Path(str(result['manifest_path'])).exists()
        result['manifest_origin_ok'] = (isinstance(data, dict) and
                                        data.get('allowed_origins') == [f'chrome-extension://{result["extension_id"]}/'])
    except Exception:
        result.update(manifest_exists=False, manifest_path=None,
                      manifest_path_exists=False, manifest_origin_ok=False)
    try:
        if sys.platform == 'win32':
            import winreg
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                    rf'Software\Google\Chrome\NativeMessagingHosts\{HOST}') as key:
                    value, _ = winreg.QueryValueEx(key, '')
                    result['registry_ok'] = True
                    result['registry_value'] = value
            except OSError:
                result['registry_ok'] = False
                result['registry_value'] = None
        else:
            result['registry_ok'] = None
            result['registry_value'] = None
    except Exception:
        result['registry_ok'] = False
        result['registry_value'] = None
    try:
        target = path(home)
        result['quota_exists'] = target.exists()
        if result['quota_exists']:
            data = json.loads(target.read_text(encoding='utf-8'))
            observed = data.get('observed_at')
            result['observed_at'] = observed if isinstance(observed, (int, float)) else None
        else:
            result['observed_at'] = None
    except (OSError, ValueError):
        result['quota_exists'] = False
        result['observed_at'] = None
    try:
        observed = result.get('observed_at')
        result['age_hours'] = (time.time() - float(observed)) / 3600 if observed else None
    except (TypeError, ValueError):
        result['age_hours'] = None
    return result


def diagnose_text(d: dict) -> str:
    """One-glance summary for the settings tab."""
    parts = []
    parts.append('manifest: ' + ('OK' if d.get('manifest_exists') and d.get('manifest_origin_ok') else '未登録'))
    reg = d.get('registry_ok')
    parts.append('registry: ' + ('OK' if reg else '未登録' if reg is False else '-'))
    ext = d.get('extension') or {}
    if ext.get('present') is True:
        if ext.get('disabled'):
            parts.append('拡張: 無効')
        else:
            label = '拡張: 有効'
            stamp = ext.get('updated_at')
            if isinstance(stamp, (int, float)):
                import time as _time
                label += f"（最終読込 {_time.strftime('%Y-%m-%d', _time.localtime(stamp))}）"
            parts.append(label)
    elif ext.get('present') is False:
        parts.append('拡張: 未導入')
    chrome = d.get('chrome_running')
    parts.append('Chrome: ' + ('起動中' if chrome else '停止中?' if chrome is False else '不明'))
    age = d.get('age_hours')
    if age is None:
        parts.append('観測: なし')
    elif age < 1 / 6:
        parts.append('観測: たった今')
    elif age < 1:
        parts.append(f'観測: 約{age * 60:.0f}分前')
    else:
        parts.append(f'観測: 約{age:.1f}時間前')
    return ' / '.join(parts)


def register(extension_id):
    """Explicit installer action, restricted to one extension and current user."""
    import re
    import winreg
    if not re.fullmatch('[a-p]{32}', extension_id) or not getattr(sys, 'frozen', False):
        raise ValueError('Use the built host executable and a valid extension ID')
    manifest = path().parent / 'browser-native-host.json'
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps({
        'name': HOST, 'description': 'Usage Monitor numeric quota receiver',
        'path': str(Path(sys.executable).resolve()), 'type': 'stdio',
        'allowed_origins': [f'chrome-extension://{extension_id}/'],
    }), encoding='utf-8')
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER,
                         rf'Software\Google\Chrome\NativeMessagingHosts\{HOST}') as key:
        winreg.SetValueEx(key, '', 0, winreg.REG_SZ, str(manifest.resolve()))
    print('Browser host registered for this extension only.')


if __name__ == '__main__':
    main()
