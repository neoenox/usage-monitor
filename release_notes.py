"""Extract one release section from CHANGELOG.md for GitHub release notes.

Stdlib only. The release workflow feeds the output to ``gh release create
--notes-file`` so the published notes are always the changelog text itself and
never a hand-written summary that can drift from it.

    python release_notes.py 0.6.4
    python release_notes.py v0.6.4 --out notes.md
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


def section(version: str, text: str) -> str:
    """Return the body of the ``## [v<version>]`` section of *text*.

    The body stops at the next heading and never includes the trailing link
    definitions. Raises ``ValueError`` when the version has no section.
    """
    wanted = f"v{version.lstrip('v')}"
    headings = list(_HEADING.finditer(text))
    for index, heading in enumerate(headings):
        if heading.group("label") != wanted:
            continue
        start = heading.end()
        end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
        closing = _LINK_DEFINITION.search(text, start)
        if closing is not None and closing.start() < end:
            end = closing.start()
        body = text[start:end].strip()
        if not body:
            raise ValueError(f"CHANGELOG.md has an empty '## [{wanted}]' section")
        return body
    raise ValueError(f"CHANGELOG.md has no '## [{wanted}]' section")


def main(argv: list[str] | None = None) -> int:
    """Print (or write) the notes. Returns a process exit code."""
    args = list(sys.argv[1:] if argv is None else argv)
    out: str | None = None
    if "--out" in args:
        index = args.index("--out")
        try:
            out = args[index + 1]
        except IndexError:
            print("release_notes: --out needs a path", file=sys.stderr)
            return 2
        del args[index:index + 2]
    if len(args) != 1:
        print("usage: python release_notes.py <version> [--out FILE]", file=sys.stderr)
        return 2
    try:
        body = section(args[0], (ROOT / CHANGELOG_NAME).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"release_notes: {exc}", file=sys.stderr)
        return 1
    if out is None:
        print(body)
    else:
        Path(out).write_text(body + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
