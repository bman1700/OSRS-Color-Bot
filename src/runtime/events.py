"""Lightweight runtime event delivery for UI and other observers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class RuntimeEvent:
    name: str
    payload: Any = None


class RuntimeEventBus:
    def __init__(self) -> None:
        self._listeners: dict[str, list[Callable[[RuntimeEvent], None]]] = {}
        self._dispatcher: Callable[[Callable[[], None]], None] | None = None

    def set_dispatcher(self, dispatcher: Callable[[Callable[[], None]], None] | None) -> None:
        """Set an optional dispatcher, such as a Tk ``after`` callback."""
        self._dispatcher = dispatcher

    def subscribe(self, name: str, listener: Callable[[RuntimeEvent], None]) -> Callable[[], None]:
        self._listeners.setdefault(name, []).append(listener)

        def unsubscribe() -> None:
            listeners = self._listeners.get(name, [])
            if listener in listeners:
                listeners.remove(listener)

        return unsubscribe

    def emit(self, name: str, payload: Any = None) -> None:
        event = RuntimeEvent(name, payload)
        for listener in tuple(self._listeners.get(name, ())):
            callback = lambda listener=listener: listener(event)
            if self._dispatcher is None:
                callback()
            else:
                self._dispatcher(callback)
