"""Unicode-native shell links; avoid WScript.Shell's ANSI path conversion."""
import ctypes
from ctypes import wintypes
import uuid


def create(path, target=None, arguments=None, working=None):
    """Create a link, or inspect an existing one when target is omitted."""
    ole = ctypes.OleDLL('ole32')
    ole.CoInitialize.argtypes = [ctypes.c_void_p]
    ole.CoCreateInstance.argtypes = [ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p, ctypes.c_void_p]
    initialized = ole.CoInitialize(None) >= 0
    link = ctypes.c_void_p()
    persist = ctypes.c_void_p()
    def guid(value):
        return ctypes.create_string_buffer(uuid.UUID(value).bytes_le)
    def call(obj, slot, argtypes, *args):
        table = ctypes.cast(obj, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
        fn = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, *argtypes)(table[slot])
        result = fn(obj, *args)
        if result < 0:
            raise OSError(f'Shell link HRESULT {result & 0xffffffff:08x}')
    try:
        result = ole.CoCreateInstance(guid('00021401-0000-0000-c000-000000000046'), None, 1,
                                     guid('000214f9-0000-0000-c000-000000000046'), ctypes.byref(link))
        if result < 0:
            raise OSError(f'Create shell link HRESULT {result & 0xffffffff:08x}')
        call(link, 0, [ctypes.c_void_p, ctypes.c_void_p], guid('0000010b-0000-0000-c000-000000000046'), ctypes.byref(persist))
        if target is None:
            call(persist, 5, [wintypes.LPCWSTR, wintypes.DWORD], str(path), 0)
            fields = []
            for slot in (3, 10, 8):
                buf = ctypes.create_unicode_buffer(32768)
                if slot == 3:
                    call(link, slot, [wintypes.LPWSTR, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD], buf, len(buf), None, 0)
                else:
                    call(link, slot, [wintypes.LPWSTR, ctypes.c_int], buf, len(buf))
                fields.append(buf.value)
            return dict(zip(('target', 'args', 'working'), fields))
        call(link, 20, [wintypes.LPCWSTR], str(target))
        call(link, 11, [wintypes.LPCWSTR], str(arguments))
        call(link, 9, [wintypes.LPCWSTR], str(working))
        call(persist, 6, [wintypes.LPCWSTR, wintypes.BOOL], str(path), True)
    finally:
        for obj in (persist, link):
            if obj.value:
                call(obj, 2, [])
        if initialized:
            ole.CoUninitialize()
