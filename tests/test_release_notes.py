"""リリースノート抽出の契約テスト。

公開ノートは CHANGELOG そのものでなければならないため、節の切り出しが
「次の見出しで止まる」「末尾のリンク定義を含まない」ことを固定する。
"""
from __future__ import annotations

from pathlib import Path

import pytest

import monitor as m
import release_notes

FAKE = """# Changelog

## [v1.2.0] - 2026-10-18

### Added

- new thing

## [v1.1.0] - 2026-10-01

### Fixed

- old thing

[Unreleased]: https://example.invalid/compare/v1.2.0...HEAD
[v1.2.0]: https://example.invalid/compare/v1.1.0...v1.2.0
[v1.1.0]: https://example.invalid/releases/tag/v1.1.0
"""


def test_section_stops_at_the_next_release():
    body = release_notes.section('1.2.0', FAKE)
    assert '### Added' in body
    assert 'new thing' in body
    assert 'old thing' not in body
    assert '## [v1.1.0]' not in body


def test_section_accepts_the_v_prefix_and_drops_link_definitions():
    body = release_notes.section('v1.1.0', FAKE)
    assert body == release_notes.section('1.1.0', FAKE)
    assert 'old thing' in body
    assert 'https://example.invalid' not in body
    assert '[v1.1.0]:' not in body


def test_section_rejects_an_unknown_version():
    with pytest.raises(ValueError):
        release_notes.section('9.9.9', FAKE)


def test_section_rejects_an_empty_release():
    with pytest.raises(ValueError):
        release_notes.section('2.0.0', '# Changelog\n\n## [v2.0.0] - 2026-10-18\n\n## [v1.0.0] - 2026-01-01\n\n- x\n')


def test_main_prints_writes_and_reports_errors(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(release_notes, 'ROOT', tmp_path)
    (tmp_path / release_notes.CHANGELOG_NAME).write_text(FAKE, encoding='utf-8')

    assert release_notes.main(['1.2.0']) == 0
    assert 'new thing' in capsys.readouterr().out

    target = tmp_path / 'notes.md'
    assert release_notes.main(['v1.1.0', '--out', str(target)]) == 0
    assert 'old thing' in target.read_text(encoding='utf-8')

    assert release_notes.main(['9.9.9']) == 1
    assert 'no' in capsys.readouterr().err

    assert release_notes.main([]) == 2
    assert release_notes.main(['1.2.0', '--out']) == 2


def test_stdout_survives_a_legacy_console_codepage(run_process, tmp_path):
    """cp932 などのコンソールでも標準出力で例外にしない。

    実際に落ちた経路 (Windows の日本語コンソール) を子プロセスで再現する。
    """
    import os
    import shutil
    import sys

    shutil.copy(release_notes.__file__, tmp_path / 'release_notes.py')
    (tmp_path / release_notes.CHANGELOG_NAME).write_text(
        FAKE.replace('new thing', 'new thing \u2014 em dash'), encoding='utf-8')

    proc = run_process(
        [sys.executable, 'release_notes.py', '1.2.0'], cwd=tmp_path, timeout=60,
        env=dict(os.environ, PYTHONIOENCODING='cp932'))
    assert 'new thing' in proc.stdout


def test_real_changelog_yields_notes_for_the_current_version():
    """リポジトリの CHANGELOG が現在のバージョンのノートを生成できる。"""
    text = (Path(release_notes.ROOT) / release_notes.CHANGELOG_NAME).read_text(encoding='utf-8')
    body = release_notes.section(m.__version__, text)
    assert body
    assert body.startswith('###')
    assert 'compare/' not in body
    assert not body.startswith('[')
