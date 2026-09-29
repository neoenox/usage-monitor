#!/usr/bin/env python3
"""Windowsタスクトレイ (ctypesのみ・依存ゼロ)。

左クリック/ダブルクリック → ウィンドウを開く
右クリック → メニュー (開く/更新/終了)
ホバー → ツールチップ / バルーン通知対応
"""
from __future__ import annotations

import ctypes
import os
import threading
from ctypes import wintypes
from pathlib import Path


def _debug(msg: str) -> None:
    try:
        d = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "usage-monitor"
        d.mkdir(parents=True, exist_ok=True)
        with open(d / "tray-debug.log", "a", encoding="utf-8") as f:
            import datetime

            f.write(f"{datetime.datetime.now():%H:%M:%S} {msg}\n")
    except Exception:
        pass

WM_USER = 0x0400
WM_TRAY = WM_USER + 20
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
WM_LBUTTONDBLCLK = 0x0203
WM_RBUTTONUP = 0x0205
WM_COMMAND = 0x0111
WM_CLOSE = 0x0010
WM_DESTROY = 0x0002
WM_QUIT = 0x0012

NIM_ADD = 0x00000000
NIM_MODIFY = 0x00000001
NIM_DELETE = 0x00000002

NIF_MESSAGE = 0x00000001
NIF_ICON = 0x00000002
NIF_TIP = 0x00000004
NIF_INFO = 0x00000010

NIIF_INFO = 0x00000001
NIIF_WARNING = 0x00000002

IMAGE_ICON = 1
LR_LOADFROMFILE = 0x00000010

TPM_RIGHTBUTTON = 0x0002
TPM_BOTTOMALIGN = 0x0020

ID_OPEN = 1001
ID_REFRESH = 1002
ID_QUIT = 1003

user32 = ctypes.windll.user32
shell32 = ctypes.windll.shell32
kernel32 = ctypes.windll.kernel32


class NOTIFYICONDATA(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("hWnd", wintypes.HWND),
        ("uID", wintypes.UINT),
        ("uFlags", wintypes.UINT),
        ("uCallbackMessage", wintypes.UINT),
        ("hIcon", wintypes.HICON),
        ("szTip", wintypes.WCHAR * 128),
        ("dwState", wintypes.DWORD),
        ("dwStateMask", wintypes.DWORD),
        ("szInfo", wintypes.WCHAR * 256),
        ("uTimeout", wintypes.UINT),
        ("szInfoTitle", wintypes.WCHAR * 64),
        ("dwInfoFlags", wintypes.DWORD),
        ("guidItem", ctypes.c_byte * 16),
        ("hBalloonIcon", wintypes.HICON),
    ]


WNDPROCTYPE = ctypes.WINFUNCTYPE(
    wintypes.LPARAM, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM
)

_HCURSOR = getattr(wintypes, "HCURSOR", None) or getattr(wintypes, "HICON", ctypes.c_void_p)


class WNDCLASS(ctypes.Structure):
    _fields_ = [
        ("style", wintypes.UINT),
        ("lpfnWndProc", WNDPROCTYPE),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HICON),
        ("hCursor", _HCURSOR),
        ("hbrBackground", wintypes.HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
    ]


user32.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASS)]
user32.RegisterClassW.restype = wintypes.ATOM
user32.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR,
                                   wintypes.DWORD, ctypes.c_int, ctypes.c_int,
                                   ctypes.c_int, ctypes.c_int, wintypes.HWND,
                                   wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID]
user32.CreateWindowExW.restype = wintypes.HWND
shell32.Shell_NotifyIconW.argtypes = [wintypes.DWORD, ctypes.POINTER(NOTIFYICONDATA)]
shell32.Shell_NotifyIconW.restype = wintypes.BOOL
user32.LoadImageW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT,
                              ctypes.c_int, ctypes.c_int, wintypes.UINT]
user32.LoadImageW.restype = wintypes.HANDLE
user32.DestroyIcon.argtypes = [wintypes.HICON]
user32.DestroyIcon.restype = wintypes.BOOL
user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.DefWindowProcW.restype = wintypes.LPARAM
user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
user32.GetMessageW.restype = wintypes.BOOL
user32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
user32.TranslateMessage.restype = wintypes.BOOL
user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
user32.DispatchMessageW.restype = wintypes.LPARAM
user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.PostMessageW.restype = wintypes.BOOL
user32.PostQuitMessage.argtypes = [ctypes.c_int]
user32.PostQuitMessage.restype = None
user32.CreatePopupMenu.argtypes = []
user32.CreatePopupMenu.restype = wintypes.HMENU
user32.AppendMenuW.argtypes = [wintypes.HMENU, wintypes.UINT, ctypes.c_size_t, wintypes.LPCWSTR]
user32.AppendMenuW.restype = wintypes.BOOL
user32.TrackPopupMenu.argtypes = [wintypes.HMENU, wintypes.UINT, ctypes.c_int, ctypes.c_int,
                                  ctypes.c_int, wintypes.HWND, ctypes.c_void_p]
user32.TrackPopupMenu.restype = wintypes.BOOL
user32.DestroyMenu.argtypes = [wintypes.HMENU]
user32.DestroyMenu.restype = wintypes.BOOL
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.SetForegroundWindow.restype = wintypes.BOOL
user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
user32.GetCursorPos.restype = wintypes.BOOL
user32.DestroyWindow.argtypes = [wintypes.HWND]
user32.DestroyWindow.restype = wintypes.BOOL


class Win32Tray:
    _registered = False

    def __init__(self, tooltip: str, on_open, on_refresh, on_quit) -> None:
        self.tooltip = tooltip
        self.on_open = on_open
        self.on_refresh = on_refresh
        self.on_quit = on_quit
        self.hwnd = None
        self.hicon = None
        self._wndproc = WNDPROCTYPE(self._proc)

    def _create(self) -> None:
        # 注意: LPCWSTRフィールドへのstr代入は一時バッファで垂れ下がるため
        # create_unicode_bufferを保持して使うこと (E2EでAVを検出済)。
        self._cls_name_buf = ctypes.create_unicode_buffer("UsageMonitorTray")
        if not Win32Tray._registered:
            cls = WNDCLASS()
            cls.lpfnWndProc = self._wndproc
            cls.hInstance = kernel32.GetModuleHandleW(None)
            cls.lpszClassName = ctypes.cast(self._cls_name_buf, wintypes.LPCWSTR)
            if not user32.RegisterClassW(ctypes.byref(cls)):
                if ctypes.GetLastError() != 1410:  # not already-exists
                    raise RuntimeError("RegisterClass failed")
            Win32Tray._registered = True
        self.hwnd = user32.CreateWindowExW(
            0, self._cls_name_buf, "UsageMonitorTray", 0,
            0, 0, 0, 0, None, None, kernel32.GetModuleHandleW(None), None,
        )
        self._add(self.tooltip)

    def _nid(self, flags, **kw) -> NOTIFYICONDATA:
        nid = NOTIFYICONDATA()
        nid.cbSize = ctypes.sizeof(NOTIFYICONDATA)
        nid.hWnd = self.hwnd
        nid.uID = 1
        nid.uFlags = flags
        nid.uCallbackMessage = WM_TRAY
        for k, v in kw.items():
            setattr(nid, k, v)
        if self.hicon:
            nid.hIcon = self.hicon
            nid.uFlags |= NIF_ICON
        return nid

    def _add(self, tooltip: str) -> None:
        nid = self._nid(NIF_MESSAGE | NIF_TIP, szTip=tooltip[:127])
        ok = shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(nid))
        _debug(f"NIM_ADD hwnd={self.hwnd} ok={bool(ok)}")

    def set_tooltip(self, text: str) -> None:
        nid = self._nid(NIF_TIP, szTip=text[:127])
        shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(nid))

    def set_icon(self, ico_path: str) -> None:
        new = user32.LoadImageW(None, ico_path, IMAGE_ICON, 64, 64, LR_LOADFROMFILE)
        if not new:
            return
        old = self.hicon
        self.hicon = new
        nid = self._nid(NIF_ICON)
        shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(nid))
        if old:
            user32.DestroyIcon(old)

    def balloon(self, title: str, msg: str, warn: bool = False) -> None:
        nid = self._nid(
            NIF_INFO, szInfo=msg[:255], szInfoTitle=title[:63],
            dwInfoFlags=NIIF_WARNING if warn else NIIF_INFO, uTimeout=10,
        )
        shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(nid))

    def _menu(self) -> None:
        menu = user32.CreatePopupMenu()
        user32.AppendMenuW(menu, 0, ID_OPEN, "開く")
        user32.AppendMenuW(menu, 0, ID_REFRESH, "更新")
        user32.AppendMenuW(menu, 0, ID_QUIT, "終了")
        pos = wintypes.POINT()
        user32.GetCursorPos(ctypes.byref(pos))
        user32.SetForegroundWindow(self.hwnd)
        user32.TrackPopupMenu(menu, TPM_RIGHTBUTTON | TPM_BOTTOMALIGN,
                              pos.x, pos.y, 0, self.hwnd, None)
        user32.PostMessageW(self.hwnd, 0, 0, 0)
        user32.DestroyMenu(menu)

    def _proc(self, hwnd, msg, wparam, lparam):
        if msg == WM_TRAY:
            _debug(f"tray msg lparam={lparam:#x}")
            if lparam in (WM_LBUTTONDOWN, WM_LBUTTONUP, WM_LBUTTONDBLCLK):
                try:
                    self.on_open()
                except Exception as e:
                    _debug(f"on_open error: {e}")
            elif lparam == WM_RBUTTONUP:
                self._menu()
            return 0
        if msg == WM_COMMAND:
            cmd = wparam & 0xFFFF
            if cmd == ID_OPEN:
                self.on_open()
            elif cmd == ID_REFRESH:
                self.on_refresh()
            elif cmd == ID_QUIT:
                self.on_quit()
            return 0
        if msg == WM_DESTROY:
            user32.PostQuitMessage(0)
            return 0
        if msg == WM_CLOSE:
            user32.DestroyWindow(hwnd)
            return 0
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def run(self) -> None:
        self._create()
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

    def stop(self) -> None:
        try:
            nid = self._nid(0)
            shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(nid))
        except Exception:
            pass
        if self.hicon:
            try:
                user32.DestroyIcon(self.hicon)
            except Exception:
                pass
            self.hicon = None
        if self.hwnd:
            # 所有スレッドで破棄するためWM_CLOSEをポスト (DestroyWindowは直接呼ばない)
            try:
                user32.PostMessageW(self.hwnd, WM_CLOSE, 0, 0)
            except Exception:
                pass
            self.hwnd = None


def run_threaded(tray: Win32Tray) -> threading.Thread:
    th = threading.Thread(target=tray.run, daemon=True)
    th.start()
    return th
