"""Windows display-coordinate helpers.

Windows reports window bounds and screen captures in different coordinate
spaces unless the process opts into per-monitor DPI awareness.  That mismatch
is most visible when a client is moved between monitors with different scale
settings.
"""

from __future__ import annotations

import ctypes
import sys


def enable_per_monitor_dpi_awareness() -> None:
    """Use physical virtual-desktop pixels for both Win32 and MSS operations.

    This is deliberately best-effort: a launcher may already have selected a
    DPI mode, and older Windows versions do not expose the newer API.
    """
    if sys.platform != "win32":
        return

    try:
        # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2
        if ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
            return
    except (AttributeError, OSError):
        pass

    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except (AttributeError, OSError):
        pass
