"""LapRemote agent - turns a phone into a control panel for this laptop."""

import sys

__version__ = "1.0.0"

if sys.platform == "win32" and "comtypes" not in sys.modules:
    # pycaw (volume) uses comtypes, which would otherwise make the main thread a
    # single-threaded COM apartment. The asyncio loop never pumps Windows messages,
    # so WinRT async calls (media sessions) would then hang. Multithreaded COM
    # avoids that. This must run before comtypes is first imported.
    sys.coinit_flags = 0  # type: ignore[attr-defined]
