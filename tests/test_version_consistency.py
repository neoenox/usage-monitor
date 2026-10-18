"""リリース表記の整合テスト。

公開済み exe の ``--version`` とウィンドウタイトルが実際のリリースから
ずれていた (v0.6.0/v0.6.1 なのに 0.5.2 と表示) ため、``monitor.__version__``
と CHANGELOG の最新リリースのドリフトを CI で検出する。
"""
from __future__ import annotations

import re
from pathlib import Path

import monitor as m

ROOT = Path(__file__).resolve().parent.parent
CHANGELOG = ROOT / "CHANGELOG.md"

# Keep a Changelog 形式のリリース見出し。新しい順に並ぶ契約。
RELEASE_HEADING = re.compile(r"^## \[v(\d+\.\d+\.\d+)\]", re.M)


def _changelog() -> str:
    return CHANGELOG.read_text(encoding="utf-8")


def _release_versions(text: str) -> list[str]:
    return RELEASE_HEADING.findall(text)


def _version_key(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def test_changelog_has_releases():
    assert _release_versions(_changelog()), "CHANGELOG.md に '## [vX.Y.Z]' 見出しがありません"


def test_version_matches_latest_changelog_release():
    latest = _release_versions(_changelog())[0]
    assert m.__version__ == latest, (
        f"monitor.__version__={m.__version__!r} が CHANGELOG 最新リリース "
        f"v{latest} と一致しません (リリース表記のドリフト)"
    )


def test_changelog_releases_are_newest_first():
    versions = _release_versions(_changelog())
    assert versions == sorted(versions, key=_version_key, reverse=True), (
        "CHANGELOG のリリース見出しは新しい順に並べてください"
    )


def test_latest_release_has_link_definitions():
    text = _changelog()
    latest = _release_versions(text)[0]
    assert re.search(rf"^\[v{re.escape(latest)}\]: \S+$", text, re.M), (
        f"v{latest} のリンク定義が CHANGELOG.md にありません"
    )
    assert re.search(r"^\[Unreleased\]: \S+$", text, re.M), (
        "[Unreleased] のリンク定義が CHANGELOG.md にありません"
    )
