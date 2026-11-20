"""A shell item's icon on Windows, through IShellItemImageFactory (comtypes, no extra packages).

pywin32 doesn't wrap this interface, so it is declared here. ``name`` is anything the shell can
parse: a file path or ``shell:AppsFolder\\<app id>``.
"""

from __future__ import annotations

import ctypes
from _ctypes import COMError
from ctypes import POINTER, byref, c_void_p, wintypes
from typing import Any

import comtypes
from comtypes import COMMETHOD, GUID, HRESULT, IUnknown
from PIL import Image

SIIGBF_RESIZETOFIT = 0x0
SIIGBF_ICONONLY = 0x4


class SIZE(ctypes.Structure):
    _fields_ = (("cx", ctypes.c_long), ("cy", ctypes.c_long))


class IShellItemImageFactory(IUnknown):
    _iid_ = GUID("{bcc18b79-ba16-442f-80c4-8a59c30c463b}")  # type: ignore[no-untyped-call]
    _methods_ = [  # noqa: RUF012 - comtypes reads this exact class attribute
        COMMETHOD(
            [],
            HRESULT,
            "GetImage",
            (["in"], SIZE, "size"),
            (["in"], ctypes.c_int, "flags"),
            (["out"], POINTER(wintypes.HBITMAP), "phbm"),
        ),
    ]


def _create_item(name: str) -> c_void_p:
    shell32 = ctypes.windll.shell32
    shell32.SHCreateItemFromParsingName.argtypes = (
        wintypes.LPCWSTR,
        c_void_p,
        POINTER(GUID),
        POINTER(c_void_p),
    )
    shell32.SHCreateItemFromParsingName.restype = HRESULT
    pointer = c_void_p()
    shell32.SHCreateItemFromParsingName(
        name, None, byref(IShellItemImageFactory._iid_), byref(pointer)
    )
    return pointer


def shell_item_icon(name: str, size: int) -> Image.Image | None:
    """The item's icon (not a content thumbnail) as an RGBA image, or None."""
    import win32gui  # noqa: PLC0415 - Windows only
    import win32ui  # noqa: PLC0415

    # Worker threads start without COM. A thread that already has it (in another mode) is fine
    # as it is, and must not be uninitialised by us afterwards.
    try:
        comtypes.CoInitialize()  # type: ignore[no-untyped-call]
        owns_com = True
    except OSError:
        owns_com = False
    try:
        try:
            pointer = _create_item(name)
        except OSError:
            return None
        factory: Any = ctypes.cast(pointer, POINTER(IShellItemImageFactory))
        try:
            handle = factory.GetImage(SIZE(size, size), SIIGBF_RESIZETOFIT | SIIGBF_ICONONLY)
        except COMError:
            return None
        try:
            bitmap = win32ui.CreateBitmapFromHandle(handle)
            info = bitmap.GetInfo()  # type: ignore[no-untyped-call]
            return Image.frombuffer(
                "RGBA",
                (info["bmWidth"], info["bmHeight"]),
                bitmap.GetBitmapBits(True),
                "raw",
                "BGRA",
                0,
                1,
            ).copy()
        finally:
            win32gui.DeleteObject(handle)
    finally:
        if owns_com:
            comtypes.CoUninitialize()  # type: ignore[no-untyped-call]
