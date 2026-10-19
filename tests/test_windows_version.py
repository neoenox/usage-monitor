"""バージョンリソース生成と `--version` の入口テスト (#77)。"""
from __future__ import annotations

import ctypes
import os
import sys
from pathlib import Path

import pytest

import monitor as m
import windows_version as wv

ROOT = Path(__file__).resolve().parent.parent


def test_resource_fields_follow_monitor_version():
    text = wv.build_version_resource()
    assert f"filevers={wv.version_tuple(m.__version__)}" in text
    assert f"prodvers={wv.version_tuple(m.__version__)}" in text
    assert f"StringStruct(u'FileVersion', u'{m.__version__}')" in text
    assert f"StringStruct(u'ProductVersion', u'{m.__version__}')" in text
    assert "StringStruct(u'OriginalFilename', u'usage-monitor.exe')" in text


def test_resource_filename_applies_to_browser_host():
    text = wv.build_version_resource(filename="usage-monitor-browser-host.exe")
    assert "StringStruct(u'OriginalFilename', u'usage-monitor-browser-host.exe')" in text
    assert "StringStruct(u'InternalName', u'usage-monitor-browser-host')" in text


def test_version_tuple_forms():
    assert wv.version_tuple("0.6.2") == (0, 6, 2, 0)
    assert wv.version_tuple("1.2.3.4") == (1, 2, 3, 4)
    assert wv.dotted("0.6.2") == "0.6.2.0"
    with pytest.raises(ValueError):
        wv.version_tuple("0.6")


def test_generator_writes_resource_file(tmp_path):
    out = tmp_path / "version-info.txt"
    assert wv.main(["--out", str(out)]) == 0
    text = out.read_text(encoding="utf-8")
    assert text.startswith("VSVersionInfo(")
    assert f"u'{m.__version__}'" in text


def test_gui_version_flag_exits_without_window(run_process):
    """`--version` はウィンドウを作らず即終了し、コンソールがあれば表示する。"""
    proc = run_process([sys.executable, "gui.py", "--version"], cwd=ROOT)
    assert m.__version__ in proc.stdout


def test_generator_creates_a_missing_output_directory(tmp_path):
    """`--out` の親ディレクトリが無くても書ける (build.ps1 と同じ CLI)。"""
    out = tmp_path / "version-file" / "usage-monitor.txt"
    assert wv.main(["--out", str(out), "--filename", "usage-monitor.exe"]) == 0
    assert out.read_text(encoding="utf-8").startswith("VSVersionInfo(")


def test_generator_cli_runs_as_a_script(run_process, tmp_path):
    """build.ps1 が呼ぶ形 (`python windows_version.py --out ...`) がそのまま動く。"""
    out = tmp_path / "version-info.txt"
    run_process([sys.executable, "windows_version.py", "--out", str(out),
                 "--filename", "usage-monitor-browser-host.exe"], cwd=ROOT)
    text = out.read_text(encoding="utf-8")
    assert text.startswith("VSVersionInfo(")
    assert "StringStruct(u'OriginalFilename', u'usage-monitor-browser-host.exe')" in text


def test_read_file_version_is_none_off_windows(monkeypatch, tmp_path):
    """非Windowsでは version.dll に触れる前に None (Linux CI でも走る)。"""
    monkeypatch.setattr(sys, "platform", "linux")

    def boom(name):  # pragma: no cover - 呼ばれたら失敗する
        raise AssertionError(f"非Windowsで {name}.dll を読みにいった")

    monkeypatch.setattr("ctypes.WinDLL", boom, raising=False)
    assert wv.read_file_version(tmp_path / "usage-monitor.exe") is None


@pytest.mark.skipif(os.name != "nt", reason="Windows version resource")
def test_read_file_version_is_none_without_a_version_resource(tmp_path):
    """リソースの無いファイル (PEですらない) と存在しないパスは None。"""
    plain = tmp_path / "plain.txt"
    plain.write_text("not a PE file\n", encoding="utf-8")
    assert wv.read_file_version(plain) is None
    assert wv.read_file_version(tmp_path / "missing.exe") is None


@pytest.mark.skipif(os.name != "nt", reason="Windows version resource")
@pytest.mark.parametrize("size,info,query,pointer", [
    (0, 1, 1, True),    # GetFileVersionInfoSizeW が 0
    (8, 0, 1, True),    # GetFileVersionInfoW が 0
    (8, 1, 0, True),    # VerQueryValueW が 0
    (8, 1, 1, False),   # VerQueryValueW は成功するが値が NULL
])
def test_read_file_version_returns_none_when_the_version_api_fails(
        monkeypatch, tmp_path, size, info, query, pointer):
    """version.dll が失敗を返す経路は例外にせず None を返す。

    擬似DLLは常に「有効な VS_FIXEDFILEINFO へのポインタ」を返せるようにしてある。
    そうしないと、どの防御が働いて None になったのか区別できず、防御を1つ外しても
    別の防御が拾ってテストが通ってしまう (実際に最初はそうなっていた)。
    """
    class FakeVersion:
        def __init__(self):
            fixed = (ctypes.c_uint32 * 13)()
            fixed[0] = 0xFEEF04BD          # dwSignature
            self.buffer = ctypes.create_string_buffer(bytes(fixed), ctypes.sizeof(fixed))

        def GetFileVersionInfoSizeW(self, target, handle):
            return size

        def GetFileVersionInfoW(self, *args):
            return info

        def VerQueryValueW(self, buf, name, value_ref, length_ref):
            if pointer:
                value = getattr(value_ref, "_obj", None)
                assert value is not None, "c_void_p への byref を期待"
                value.value = ctypes.addressof(self.buffer)
            return query

    monkeypatch.setattr("ctypes.WinDLL", lambda name: FakeVersion())
    assert wv.read_file_version(tmp_path / "any.exe") is None


@pytest.mark.skipif(os.name != "nt", reason="Windows version resource")
def test_read_file_version_reads_a_real_resource():
    """実在するリソース付きバイナリから読み、フィールドの位置まで検証する。

    形状 (4つの数字) だけでは dwFileVersionMS / dwFileVersionLS のオフセット違いを
    見抜けないので、CPython の慣習どおり major.minor が実行中のインタプリタと
    一致することまで確かめる。
    """
    value = wv.read_file_version(sys.executable)
    assert value is not None, f"{sys.executable} にバージョンリソースがある前提"
    parts = [int(part) for part in value.split(".")]
    assert len(parts) == 4, value
    assert tuple(parts[:2]) == tuple(sys.version_info[:2]), (
        f"read_file_version={value!r} が実行中の Python {sys.version_info[0]}.{sys.version_info[1]} "
        "と一致しません (VS_FIXEDFILEINFO のオフセット?)")
