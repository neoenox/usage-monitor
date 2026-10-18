"""ビルド時に PyInstaller へ渡すWindowsバージョンリソース (#77)。

`monitor.__version__` からバージョンリソースを生成し、`--version-file` で
exe に埋め込む。エクスプローラーのプロパティや
`(Get-Item .\\usage-monitor.exe).VersionInfo` でリリース版を確認できる。
"""
from __future__ import annotations

import sys
from pathlib import Path

import monitor as m

DEFAULT_FILENAME = "usage-monitor.exe"

TEMPLATE = """\
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={numbers},
    prodvers={numbers},
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
    ),
  kids=[
    StringFileInfo(
      [
      StringTable(
        u'040904B0',
        [StringStruct(u'CompanyName', u'usage-monitor'),
        StringStruct(u'FileDescription', u'usage-monitor'),
        StringStruct(u'FileVersion', u'{version}'),
        StringStruct(u'InternalName', u'{filename_stem}'),
        StringStruct(u'OriginalFilename', u'{filename}'),
        StringStruct(u'ProductName', u'usage-monitor'),
        StringStruct(u'ProductVersion', u'{version}')])
      ]),
    VarFileInfo([VarStruct(u'Translation', [1033, 1200])])
  ]
)
"""


def version_tuple(version: str) -> tuple[int, int, int, int]:
    """`X.Y.Z` (または `X.Y.Z.W`) を4要素の整数タプルにする。"""
    parts = [int(part) for part in version.split(".")]
    if len(parts) not in (3, 4):
        raise ValueError(f"unsupported version: {version!r}")
    return tuple((parts + [0, 0, 0, 0])[:4])  # type: ignore[return-value]


def dotted(version: str) -> str:
    """バージョンリソースが返す固定情報形式 (`X.Y.Z.0`)。"""
    return ".".join(str(part) for part in version_tuple(version))


def build_version_resource(version: str = m.__version__, filename: str = DEFAULT_FILENAME) -> str:
    """PyInstaller `--version-file` に渡す `VSVersionInfo` テキスト。"""
    return TEMPLATE.format(
        numbers=version_tuple(version),
        version=version,
        filename=filename,
        filename_stem=Path(filename).stem,
    )


def read_file_version(path: str | Path) -> str | None:
    """exe に埋め込まれた固定バージョン情報を `X.Y.Z.0` で読む (Windowsのみ)。

    バージョンリソースが無い場合は None。ファイル内容は読み取って解析しない
    (Windows の version.dll が返すメタデータのみ)。
    """
    if sys.platform != "win32":
        return None
    import ctypes
    from ctypes import wintypes

    version_dll = ctypes.WinDLL("version")
    target = str(path)
    size = version_dll.GetFileVersionInfoSizeW(target, None)
    if not size:
        return None
    buf = ctypes.create_string_buffer(size)
    if not version_dll.GetFileVersionInfoW(target, 0, size, buf):
        return None
    value = ctypes.c_void_p()
    length = wintypes.UINT()
    if not version_dll.VerQueryValueW(buf, "\\", ctypes.byref(value), ctypes.byref(length)):
        return None
    if not value:
        return None
    # VS_FIXEDFILEINFO: dwSignature, dwStrucVersion, dwFileVersionMS, dwFileVersionLS, ...
    fields = ctypes.cast(value, ctypes.POINTER(ctypes.c_uint32 * 13)).contents
    ms, ls = fields[2], fields[3]
    return f"{ms >> 16}.{ms & 0xffff}.{ls >> 16}.{ls & 0xffff}"


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Windows version resource generator")
    parser.add_argument("--out", required=True, help="write the VSVersionInfo text here")
    parser.add_argument("--filename", default=DEFAULT_FILENAME, help="executable file name")
    parser.add_argument("--version", default=m.__version__, help="version to embed")
    args = parser.parse_args(argv)

    text = build_version_resource(args.version, args.filename)
    out = Path(args.out)
    if out.parent and not out.parent.exists():
        out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
