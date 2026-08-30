"""Bounded, in-memory diagnostics for reconstructing bot decisions.

The recorder deliberately has no persistence or background worker. Recording is
opt-in, bounded, and safe to leave attached in production runtimes.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass
from threading import Lock
import time
from types import MappingProxyType
from typing import Any


@dataclass(frozen=True)
class TelemetryRecord:
    """One diagnostic fact in the order the runtime observed it."""

    sequence: int
    timestamp: float
    kind: str
    action: str | None
    data: Mapping[str, Any]


class TelemetryRecorder:
    """A thread-safe ring buffer of optional bot-mechanics diagnostics."""

    def __init__(self, *, capacity: int = 512, enabled: bool = False) -> None:
        if capacity < 1:
            raise ValueError("capacity must be at least one")
        self.capacity = capacity
        self.enabled = enabled
        self._records: deque[TelemetryRecord] = deque(maxlen=capacity)
        self._sequence = 0
        self._lock = Lock()

    def record(self, kind: str, *, action: str | None = None, data: Mapping[str, Any] | None = None) -> TelemetryRecord | None:
        """Add a fact, returning it for event delivery, or ``None`` when disabled."""
        if not kind or not kind.strip():
            raise ValueError("kind must be non-empty")
        if action is not None and not action.strip():
            raise ValueError("action must be non-empty when supplied")
        frozen_data = MappingProxyType(dict(data or {}))
        with self._lock:
            if not self.enabled:
                return None
            self._sequence += 1
            record = TelemetryRecord(self._sequence, time.monotonic(), kind, action, frozen_data)
            self._records.append(record)
            return record

    def snapshot(self) -> tuple[TelemetryRecord, ...]:
        """Return a stable, oldest-to-newest replay view."""
        with self._lock:
            return tuple(self._records)

    def clear(self) -> None:
        with self._lock:
            self._records.clear()

    def set_enabled(self, enabled: bool) -> None:
        with self._lock:
            self.enabled = enabled

    def action_intent(self, action: str, *, target: Any = None, metadata: Mapping[str, Any] | None = None) -> TelemetryRecord | None:
        data = dict(metadata or {})
        if target is not None:
            data["target"] = target
        return self.record("action_intent", action=action, data=data)

    def detection(self, name: str, confidence: float | None, *, metadata: Mapping[str, Any] | None = None) -> TelemetryRecord | None:
        data = dict(metadata or {})
        data.update(name=name, confidence=confidence)
        return self.record("detection", data=data)

    def wait(self, predicate: str, elapsed_seconds: float, outcome: str, *, metadata: Mapping[str, Any] | None = None) -> TelemetryRecord | None:
        data = dict(metadata or {})
        data.update(predicate=predicate, elapsed_seconds=elapsed_seconds, outcome=outcome)
        return self.record("wait", data=data)

    def verification(self, action: str, *, succeeded: bool, attempts: int, reason: str, metadata: Mapping[str, Any] | None = None) -> TelemetryRecord | None:
        data = dict(metadata or {})
        data.update(succeeded=succeeded, attempts=attempts, reason=reason)
        return self.record("verification", action=action, data=data)

    def recovery(self, action: str, reason: str, *, metadata: Mapping[str, Any] | None = None) -> TelemetryRecord | None:
        data = dict(metadata or {})
        data["reason"] = reason
        return self.record("recovery", action=action, data=data)
