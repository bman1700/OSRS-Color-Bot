"""Transport-independent input contracts.

This module deliberately contains no desktop input calls.  It provides the
boundary that movement and action code will use once the RemoteInput native
extension is integrated.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
import ctypes
import os
from pathlib import Path
from typing import Any, Callable, Literal

MouseButton = Literal["left", "right", "middle"]


class InputProviderError(RuntimeError):
    """Raised when a provider cannot deliver an input event."""


class InputProvider(ABC):
    """Interface for input delivered to the game client."""

    @abstractmethod
    def connect(self) -> None:
        """Attach to the target client or raise :class:`InputProviderError`."""

    @abstractmethod
    def disconnect(self) -> None:
        """Release the provider's client connection."""

    @abstractmethod
    def is_connected(self) -> bool:
        """Return whether input can currently be delivered."""

    @abstractmethod
    def move_to(self, x: int, y: int) -> None:
        """Move the remote pointer to client-relative coordinates."""

    @abstractmethod
    def mouse_down(self, button: MouseButton = "left") -> None:
        """Press a remote mouse button."""

    @abstractmethod
    def mouse_up(self, button: MouseButton = "left") -> None:
        """Release a remote mouse button."""

    def click(self, button: MouseButton = "left") -> None:
        """Press and release a remote mouse button."""
        self.mouse_down(button)
        self.mouse_up(button)

    @abstractmethod
    def key_down(self, key: str) -> None:
        """Press a remote keyboard key."""

    @abstractmethod
    def key_up(self, key: str) -> None:
        """Release a remote keyboard key."""


@dataclass(frozen=True)
class InputEvent:
    """Recorded event used by tests and dry-run diagnostics."""

    name: str
    args: tuple[Any, ...]


class MockInputProvider(InputProvider):
    """In-memory provider that never sends OS or game-client input."""

    def __init__(self) -> None:
        self.events: list[InputEvent] = []
        self._connected = False

    def connect(self) -> None:
        self._connected = True
        self.events.append(InputEvent("connect", ()))

    def disconnect(self) -> None:
        self._connected = False
        self.events.append(InputEvent("disconnect", ()))

    def is_connected(self) -> bool:
        return self._connected

    def _record(self, name: str, *args: Any) -> None:
        if not self._connected:
            raise InputProviderError("Mock input provider is not connected")
        self.events.append(InputEvent(name, args))

    def move_to(self, x: int, y: int) -> None:
        self._record("move_to", int(x), int(y))

    def mouse_down(self, button: MouseButton = "left") -> None:
        self._record("mouse_down", button)

    def mouse_up(self, button: MouseButton = "left") -> None:
        self._record("mouse_up", button)

    def key_down(self, key: str) -> None:
        self._record("key_down", key)

    def key_up(self, key: str) -> None:
        self._record("key_up", key)


class RemoteInputProvider(InputProvider):
    """Native adapter for Brandon-T's RemoteInput DLL.

    The DLL injects into the target Java process and dispatches Java AWT input
    events. Coordinates are relative to the RuneLite canvas, not the desktop.
    """

    _BUTTON_CODES = {"left": 1, "right": 0, "middle": 2}
    _KEY_CODES = {
        "backspace": 0x08, "tab": 0x09, "enter": 0x0D, "return": 0x0D,
        "shift": 0x10, "ctrl": 0x11, "control": 0x11, "alt": 0x12,
        "esc": 0x1B, "escape": 0x1B, "space": 0x20,
        "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28,
        "delete": 0x2E, "home": 0x24, "end": 0x23,
        "pageup": 0x21, "pagedown": 0x22,
    }

    def __init__(
        self,
        process_id: int | None = None,
        dll_path: str | Path | None = None,
        library_loader: Callable[[str], Any] | None = None,
    ) -> None:
        self.process_id = process_id
        self.dll_path = Path(dll_path) if dll_path else Path(__file__).resolve().parents[3] / "libRemoteInput-x86_64.dll"
        self._library_loader = library_loader
        self._library: Any | None = None
        self._target: ctypes.c_void_p | None = None
        self._connected = False

    def connect(self) -> None:
        if self._connected:
            return
        if self.process_id is None or self.process_id <= 0:
            raise InputProviderError("A positive RuneLite Java process ID is required. Direct desktop input fallback is disabled.")
        if not self.dll_path.is_file():
            raise InputProviderError(f"RemoteInput DLL was not found: {self.dll_path}")
        try:
            self._library = self._load_library()
            self._configure_api(self._library)
            self._library.EIOS_Inject_PID(self.process_id)
            target = self._library.EIOS_RequestTarget(str(self.process_id).encode("ascii"))
            if not target:
                raise InputProviderError(f"RemoteInput could not attach to Java process {self.process_id}")
            self._target = ctypes.c_void_p(target)
            self._connected = True
        except (OSError, AttributeError, InputProviderError) as error:
            self.disconnect()
            if isinstance(error, InputProviderError):
                raise
            raise InputProviderError(f"Unable to load RemoteInput DLL: {error}") from error

    def disconnect(self) -> None:
        if self._library is not None and self._target is not None:
            self._library.EIOS_ReleaseTarget(self._target)
        self._target = None
        self._library = None
        self._connected = False

    def is_connected(self) -> bool:
        return self._connected

    def _require_connection(self) -> None:
        if not self._connected:
            raise InputProviderError("RemoteInput is not connected to a Java client")

    def _load_library(self) -> Any:
        if self._library_loader is not None:
            return self._library_loader(str(self.dll_path))
        if os.name != "nt":
            raise InputProviderError("This RemoteInput DLL adapter currently supports Windows only")
        return ctypes.WinDLL(str(self.dll_path))

    @staticmethod
    def _configure_api(library: Any) -> None:
        library.EIOS_RequestTarget.argtypes = [ctypes.c_char_p]
        library.EIOS_RequestTarget.restype = ctypes.c_void_p
        library.EIOS_Inject_PID.argtypes = [ctypes.c_int32]
        library.EIOS_ReleaseTarget.argtypes = [ctypes.c_void_p]
        library.EIOS_MoveMouse.argtypes = [ctypes.c_void_p, ctypes.c_int32, ctypes.c_int32]
        library.EIOS_HoldMouse.argtypes = [ctypes.c_void_p, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32]
        library.EIOS_ReleaseMouse.argtypes = [ctypes.c_void_p, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32]
        library.EIOS_HoldKey.argtypes = [ctypes.c_void_p, ctypes.c_int32]
        library.EIOS_ReleaseKey.argtypes = [ctypes.c_void_p, ctypes.c_int32]
        library.EIOS_GetTargetDimensions.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_int32), ctypes.POINTER(ctypes.c_int32)]

    @classmethod
    def _key_code(cls, key: str) -> int:
        normalized = key.lower()
        if normalized in cls._KEY_CODES:
            return cls._KEY_CODES[normalized]
        if len(key) == 1 and key.isascii():
            return ord(key.upper())
        raise InputProviderError(f"Unsupported RemoteInput key: {key!r}")

    def move_to(self, x: int, y: int) -> None:
        self._require_connection()
        self._library.EIOS_MoveMouse(self._target, int(x), int(y))

    def mouse_down(self, button: MouseButton = "left") -> None:
        self._require_connection()
        self._library.EIOS_HoldMouse(self._target, 0, 0, self._BUTTON_CODES[button])

    def mouse_up(self, button: MouseButton = "left") -> None:
        self._require_connection()
        self._library.EIOS_ReleaseMouse(self._target, 0, 0, self._BUTTON_CODES[button])

    def key_down(self, key: str) -> None:
        self._require_connection()
        self._library.EIOS_HoldKey(self._target, self._key_code(key))

    def key_up(self, key: str) -> None:
        self._require_connection()
        self._library.EIOS_ReleaseKey(self._target, self._key_code(key))

    def health_check(self) -> bool:
        """Verify that the attached client reports usable canvas dimensions."""
        if not self._connected:
            return False
        width = ctypes.c_int32()
        height = ctypes.c_int32()
        self._library.EIOS_GetTargetDimensions(self._target, ctypes.byref(width), ctypes.byref(height))
        if width.value <= 0 or height.value <= 0:
            self._connected = False
            return False
        return True
