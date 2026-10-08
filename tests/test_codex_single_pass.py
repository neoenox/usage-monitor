import builtins
from collections import Counter
import monitor as m


def test_each_session_opened_once(fake_home, monkeypatch):
    original = builtins.open
    opened = []
    def counted(path, *args, **kwargs):
        if str(path).endswith('.jsonl'):
            opened.append(str(path))
        return original(path, *args, **kwargs)
    monkeypatch.setattr(builtins, 'open', counted)
    result = m.scan_codex(fake_home)
    assert result['files'] == 2
    assert len(opened) == 2
    assert all(count == 1 for count in Counter(opened).values())
