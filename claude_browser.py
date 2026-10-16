"""Numeric-only import and Chrome native messaging boundary; no auth access."""
from __future__ import annotations

import json
from pathlib import Path
import struct
import sys

import claude_export

HOST = 'com.neoenox.usage_monitor'
MAX_MESSAGE = 4096


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
