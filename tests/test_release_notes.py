"""リリースノート抽出の契約テスト。

公開ノートは CHANGELOG そのものでなければならないため、節の切り出しが
「次の見出しで止まる」「末尾のリンク定義を含まない」ことを固定する。
"""
from __future__ import annotations

import io
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


FAKE_WITH_UNRELEASED = """# Changelog

## [Unreleased]

### Changed

- pending thing

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


def test_release_section_is_unaffected_by_a_pending_unreleased_section():
    """未リリース項目が公開ノートに混ざらない (混ざると移し忘れに気づけない)。"""
    body = release_notes.section('1.2.0', FAKE_WITH_UNRELEASED)
    assert 'new thing' in body
    assert 'pending thing' not in body
    assert 'Unreleased' not in body


def test_unreleased_is_empty_without_or_before_the_section():
    assert release_notes.unreleased(FAKE) == ''
    empty = ('# Changelog\n\n## [Unreleased]\n\n## [v1.2.0] - 2026-10-18\n\n- x\n')
    assert release_notes.unreleased(empty) == ''


def test_unreleased_returns_only_the_pending_entries():
    body = release_notes.unreleased(FAKE_WITH_UNRELEASED)
    assert body == '### Changed\n\n- pending thing'
    assert 'new thing' not in body
    assert 'https://example.invalid' not in body


def test_main_check_unreleased_passes_when_nothing_is_pending(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(release_notes, 'ROOT', tmp_path)
    changelog = tmp_path / release_notes.CHANGELOG_NAME

    changelog.write_text(FAKE, encoding='utf-8')                      # 節そのものが無い
    assert release_notes.main(['--check-unreleased']) == 0
    assert 'nothing pending' in capsys.readouterr().out

    changelog.write_text('# Changelog\n\n## [Unreleased]\n\n## [v1.2.0] - 2026-10-18\n\n- x\n',
                         encoding='utf-8')                            # 節はあるが空
    assert release_notes.main(['--check-unreleased']) == 0


def test_main_check_unreleased_fails_and_prints_the_pending_entries(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(release_notes, 'ROOT', tmp_path)
    (tmp_path / release_notes.CHANGELOG_NAME).write_text(FAKE_WITH_UNRELEASED, encoding='utf-8')

    assert release_notes.main(['--check-unreleased']) == 1
    err = capsys.readouterr().err
    assert 'still has entries' in err
    assert 'pending thing' in err


def test_main_check_unreleased_is_a_standalone_mode(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(release_notes, 'ROOT', tmp_path)
    (tmp_path / release_notes.CHANGELOG_NAME).write_text(FAKE, encoding='utf-8')

    assert release_notes.main(['--check-unreleased', '1.2.0']) == 2
    assert release_notes.main(['--check-unreleased', '--out', str(tmp_path / 'x.md')]) == 2
    assert 'usage' in capsys.readouterr().err
    assert not (tmp_path / 'x.md').exists()


def test_main_check_unreleased_reports_a_missing_changelog(tmp_path, monkeypatch, capsys):
    """CHANGELOG が読めない場合も traceback にせず理由を出す。"""
    monkeypatch.setattr(release_notes, 'ROOT', tmp_path)

    assert release_notes.main(['--check-unreleased']) == 1
    assert 'CHANGELOG.md' in capsys.readouterr().err


def test_console_safe_ignores_a_stream_without_reconfigure():
    """reconfigure を持たないストリーム (テストの捕捉など) でも落ちない。"""
    release_notes._console_safe(io.StringIO())


def test_check_unreleased_survives_a_legacy_console_codepage(run_process, tmp_path):
    """pending 項目に em dash があっても cp932 コンソールで traceback にしない (#87 の経路)。"""
    import os
    import shutil
    import sys

    shutil.copy(release_notes.__file__, tmp_path / 'release_notes.py')
    (tmp_path / release_notes.CHANGELOG_NAME).write_text(
        FAKE_WITH_UNRELEASED.replace('pending thing', 'pending thing \u2014 em dash'),
        encoding='utf-8')

    proc = run_process(
        [sys.executable, 'release_notes.py', '--check-unreleased'], cwd=tmp_path, timeout=60,
        env=dict(os.environ, PYTHONIOENCODING='cp932'), expect=None)
    assert proc.returncode == 1
    assert 'pending thing' in proc.stdout + proc.stderr
    assert 'Traceback' not in proc.stderr
