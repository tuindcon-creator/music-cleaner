"""Real Windows handle lacking FILE_SHARE_DELETE, for progress-race regression."""
import ctypes
from contextlib import contextmanager
from ctypes import wintypes
import os

@contextmanager
def deny_delete_share(path):
    if os.name != "nt":
        raise RuntimeError("This regression requires Windows file sharing semantics.")
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    create = kernel.CreateFileW
    create.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                       wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    create.restype = wintypes.HANDLE
    close = kernel.CloseHandle
    close.argtypes = [wintypes.HANDLE]
    close.restype = wintypes.BOOL
    # Allow concurrent readers/writers but disallow rename/delete of this target.
    handle = create(str(path), 0x80000000, 0x00000001 | 0x00000002, None, 3, 0x80, None)
    if handle == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        yield
    finally:
        if not close(handle):
            raise ctypes.WinError(ctypes.get_last_error())
