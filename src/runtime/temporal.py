"""Temporal predicates for decisions based on successive sensor snapshots."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from runtime.cancellation import CancellationToken, wait_for
from runtime.sensors import SensorSnapshot

SnapshotSelector = str | Callable[[SensorSnapshot], Any]


def value_of(snapshot: SensorSnapshot, selector: SnapshotSelector) -> Any:
    """Read a snapshot field or call a snapshot selector."""
    if callable(selector):
        return selector(snapshot)
    try:
        return getattr(snapshot, selector)
    except AttributeError as error:
        raise ValueError(f"SensorSnapshot has no field {selector!r}") from error


class _ForTicks:
    def __init__(self, ticks: int) -> None:
        if ticks <= 0:
            raise ValueError("ticks must be positive")
        self.ticks, self._last_tick, self._count = ticks, None, 0

    def _new_tick(self, snapshot: SensorSnapshot) -> bool:
        # No tick means a generic source: each observation is meaningful.
        if snapshot.tick is None:
            return True
        if snapshot.tick == self._last_tick:
            return False
        self._last_tick = snapshot.tick
        return True


class Debounced(_ForTicks):
    """Return true after a predicate remains true for ``ticks`` observations."""
    def __init__(self, predicate: Callable[[SensorSnapshot], bool], ticks: int = 1) -> None:
        super().__init__(ticks)
        self.predicate = predicate

    def __call__(self, snapshot: SensorSnapshot) -> bool:
        if self._new_tick(snapshot):
            self._count = self._count + 1 if self.predicate(snapshot) else 0
        return self._count >= self.ticks


_UNSET = object()


class StableForTicks(_ForTicks):
    """Return true once a selected value has stayed unchanged for ``ticks``."""
    def __init__(self, selector: SnapshotSelector, ticks: int = 1) -> None:
        super().__init__(ticks)
        self.selector, self._value = selector, _UNSET

    def __call__(self, snapshot: SensorSnapshot) -> bool:
        if not self._new_tick(snapshot):
            return self._count >= self.ticks
        value = value_of(snapshot, self.selector)
        if value == self._value:
            self._count += 1
        else:
            self._value, self._count = value, 1
        return self._count >= self.ticks


class ChangedForTicks(_ForTicks):
    """Return true once a value differs from a baseline for ``ticks``."""
    def __init__(self, selector: SnapshotSelector, baseline: Any = _UNSET, ticks: int = 1) -> None:
        super().__init__(ticks)
        self.selector, self.baseline = selector, baseline

    def __call__(self, snapshot: SensorSnapshot) -> bool:
        if not self._new_tick(snapshot):
            return self._count >= self.ticks
        value = value_of(snapshot, self.selector)
        if self.baseline is _UNSET:
            self.baseline, self._count = value, 0
            return False
        self._count = self._count + 1 if value != self.baseline else 0
        return self._count >= self.ticks


class TemporalSensors:
    """Polling and stateful predicates for a snapshot provider.

    The provider is normally ``runtime.snapshot`` or ``runtime.sensors.snapshot``.
    All waits use the existing cooperative cancellation API.
    """
    def __init__(self, snapshot_provider: Callable[[], SensorSnapshot], *, stale_after: float | None = None) -> None:
        self.snapshot_provider, self.stale_after = snapshot_provider, stale_after
        self._last_snapshot: SensorSnapshot | None = None
        self._last_received_at: float | None = None

    def snapshot(self) -> SensorSnapshot:
        snapshot = self.snapshot_provider()
        if snapshot.tick is None or self._last_snapshot is None or snapshot.tick != self._last_snapshot.tick:
            self._last_received_at = time.monotonic()
        self._last_snapshot = snapshot
        return snapshot

    def is_stale(self, max_age: float | None = None, *, now: float | None = None) -> bool:
        age_limit = self.stale_after if max_age is None else max_age
        if age_limit is None:
            raise ValueError("max_age is required when stale_after is not configured")
        if age_limit < 0:
            raise ValueError("max_age must be non-negative")
        if self._last_received_at is None:
            return True
        return (time.monotonic() if now is None else now) - self._last_received_at > age_limit

    def wait_for(self, predicate: Callable[[SensorSnapshot], bool], *, timeout: float, cancellation: CancellationToken,
                 interval: float = 0.1, action: str = "sensor condition", reject_stale: bool = False) -> SensorSnapshot:
        confirmed: SensorSnapshot | None = None
        def observed() -> bool:
            nonlocal confirmed
            snapshot = self.snapshot()
            if (not reject_stale or not self.is_stale()) and predicate(snapshot):
                confirmed = snapshot
                return True
            return False
        wait_for(observed, timeout=timeout, cancellation=cancellation, interval=interval, action=action)
        assert confirmed is not None
        return confirmed

    def wait_for_stable(self, selector: SnapshotSelector, *, ticks: int, timeout: float, cancellation: CancellationToken,
                        interval: float = 0.1, action: str = "stable sensor value") -> SensorSnapshot:
        return self.wait_for(StableForTicks(selector, ticks), timeout=timeout, cancellation=cancellation, interval=interval, action=action)

    def wait_for_changed(self, selector: SnapshotSelector, *, baseline: Any = _UNSET, ticks: int = 1, timeout: float,
                         cancellation: CancellationToken, interval: float = 0.1, action: str = "sensor value change") -> SensorSnapshot:
        return self.wait_for(ChangedForTicks(selector, baseline, ticks), timeout=timeout, cancellation=cancellation, interval=interval, action=action)

    def wait_for_transition(self, selector: SnapshotSelector, expected: Any, *, previous: Any = _UNSET, ticks: int = 1,
                            timeout: float, cancellation: CancellationToken, interval: float = 0.1,
                            action: str = "expected sensor transition") -> SensorSnapshot:
        saw_previous = previous is _UNSET
        debounced = Debounced(lambda snapshot: value_of(snapshot, selector) == expected, ticks)
        def transitioned(snapshot: SensorSnapshot) -> bool:
            nonlocal saw_previous
            if not saw_previous and value_of(snapshot, selector) == previous:
                saw_previous = True
            return saw_previous and debounced(snapshot)
        return self.wait_for(transitioned, timeout=timeout, cancellation=cancellation, interval=interval, action=action)
