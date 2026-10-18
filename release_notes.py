"""Extract one release section from CHANGELOG.md for GitHub release notes.

Stdlib only. The release workflow feeds the output to ``gh release create
--notes-file`` so the published notes are always the changelog text itself and
never a hand-written summary that can drift from it.

``--check-unreleased`` is the release-time gate for the ``## [Unreleased]``
section: entries that accumulated there have to be moved into the new release
section before tagging, otherwise they silently never reach the published notes.

    python release_notes.py 0.6.4
    python release_notes.py v0.6.4 --out notes.md
    python release_notes.py --check-unreleased
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CHANGELOG_NAME = "CHANGELOG.md"

# Keep a Changelog headings: '## [vX.Y.Z] - date' (and '## [Unreleased]').
# The whole line is consumed so the date tail never leaks into the notes body.
_HEADING = re.compile(r"^## \[(?P<label>[^\]]+)\][^\n]*$", re.M)
# The link definitions that close the file; they are not release notes.
_LINK_DEFINITION = re.compile(r"^\[[^\]]+\]: \S+$", re.M)


def _body(text: str, label: str) -> tuple[bool, str]:
    """Return ``(found, body)`` for the ``## [label]`` section of *text*.

    The body stops at the next heading and never includes the trailing link
    definitions.
    """
    headings = list(_HEADING.finditer(text))
    for index, heading in enumerate(headings):
        if heading.group("label") != label:
            continue
        start = heading.end()
        end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
        closing = _LINK_DEFINITION.search(text, start)
        if closing is not None and closing.start() < end:
            end = closing.start()
        return True, text[start:end].strip()
    return False, ""


def section(version: str, text: str) -> str:
    """Return the body of the ``## [v<version>]`` section of *text*.

    Raises ``ValueError`` when the version has no section or an empty one.
    """
    wanted = f"v{version.lstrip('v')}"
    found, body = _body(text, wanted)
    if not found:
        raise ValueError(f"CHANGELOG.md has no '## [{wanted}]' section")
    if not body:
        raise ValueError(f"CHANGELOG.md has an empty '## [{wanted}]' section")
    return body


def unreleased(text: str) -> str:
    """Return the body of ``## [Unreleased]``, or ``''`` when it is empty or absent.

    Absent counts as empty: a changelog that predates the section (an older tag
    being dry-run, for instance) has nothing pending by definition.
    """
    found, body = _body(text, "Unreleased")
    return body if found else ""


def _console_safe(stream) -> None:
    """Let a legacy console code page (cp932 and friends) escape what it cannot encode.

    Turning a notes dump or an error report into a traceback is exactly the kind
    of failure this helper exists to describe.
    """
    try:
        stream.reconfigure(errors="backslashreplace")
    except (AttributeError, ValueError, OSError):
        pass


def _check_unreleased() -> int:
    """Exit 0 when nothing is pending under ``## [Unreleased]``, 1 when entries remain."""
    try:
        text = (ROOT / CHANGELOG_NAME).read_text(encoding="utf-8")
    except OSError as exc:
        print(f"release_notes: {exc}", file=sys.stderr)
        return 1
    body = unreleased(text)
    if not body:
        print("release_notes: nothing pending under '## [Unreleased]'")
        return 0
    _console_safe(sys.stderr)
    print("release_notes: '## [Unreleased]' still has entries; move them into the new "
          "release section before tagging:", file=sys.stderr)
    print(body, file=sys.stderr)
    return 1


USAGE = "usage: python release_notes.py <version> [--out FILE] | --check-unreleased"


def main(argv: list[str] | None = None) -> int:
    """Print (or write) the notes, or check the Unreleased section. Returns an exit code."""
    args = list(sys.argv[1:] if argv is None else argv)
    check = "--check-unreleased" in args
    if check:
        args.remove("--check-unreleased")
    out: str | None = None
    if "--out" in args:
        index = args.index("--out")
        try:
            out = args[index + 1]
        except IndexError:
            print("release_notes: --out needs a path", file=sys.stderr)
            return 2
        del args[index:index + 2]
    if check:
        if args or out is not None:
            print(USAGE, file=sys.stderr)
            return 2
        return _check_unreleased()
    if len(args) != 1:
        print(USAGE, file=sys.stderr)
        return 2
    try:
        body = section(args[0], (ROOT / CHANGELOG_NAME).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"release_notes: {exc}", file=sys.stderr)
        return 1
    if out is None:
        _console_safe(sys.stdout)
        print(body)
    else:
        Path(out).write_text(body + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
