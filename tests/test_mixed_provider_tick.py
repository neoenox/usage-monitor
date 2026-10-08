from types import SimpleNamespace
import time
import gui


class Label:
    def __init__(self):
        self.text = ''
    def config(self, **kwargs):
        self.text = kwargs.get('text', self.text)


def test_claude_observation_does_not_skip_fresh_codex_tick(monkeypatch):
    codex = {'has_rate': True, 'usage_status': 'ok', 'rate_limits': {
        'primary': {'used_percent': 25, 'resets_at': time.time()+3600},
        'secondary': {'used_percent': 30, 'resets_at': time.time()+86400}}}
    claude = {'quota_cached': True, 'quota_source': 'statusline', 'observed_at': time.time(),
              'oauth': {'status': 'ok', 'five_hour': {'utilization': 40, 'resets_at': '2030-01-01T00:00:00+00:00'}}}
    app = SimpleNamespace(_last=(codex, claude), lbl5=Label(), lblW=Label(),
                          cl_lbl5=Label(), cl_lblW=Label(), freshness=Label(),
                          _schedule_tick=lambda: None, _codex_label=gui.App._codex_label)
    monkeypatch.setattr(gui.h, 'recent', lambda *args: [])
    gui.App._tick(app)
    assert '残り75%' in app.lbl5.text
    assert 'Claude Code利用時' in app.cl_lbl5.text
    assert '予測' not in app.cl_lbl5.text
