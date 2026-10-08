import json
import settings


def test_string_input_saved_as_numbers(tmp_path, monkeypatch):
    target = tmp_path/'settings.json'
    monkeypatch.setattr(settings, 'path', lambda: target)
    assert settings.save('30', '15') is None
    saved = json.loads(target.read_text())
    assert isinstance(saved['warn_at'], float)
    assert isinstance(saved['crit_at'], float)
    assert settings.load() == {'warn_at': 30.0, 'crit_at': 15.0}
