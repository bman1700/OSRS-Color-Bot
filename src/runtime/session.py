"""Opt-in session and break planning for bot scripts.

The planner deliberately never sleeps, stops a bot, or changes script flow on
its own. A script must call ``decide`` or ``break_if_due`` explicitly.
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass
from enum import Enum
from typing import Callable

from runtime.cancellation import BotCancelled, CancellationToken
from runtime.events import RuntimeEventBus


@dataclass(frozen=True)
class SessionBudget:
    """Optional upper bound for elapsed session time, in seconds."""

    max_session_seconds: float | None = None

    def __post_init__(self) -> None:
        if self.max_session_seconds is not None and self.max_session_seconds <= 0:
            raise ValueError("max_session_seconds must be positive when configured")


@dataclass(frozen=True)
class BreakPolicy:
    """Ranges from which the next break and its duration are sampled."""

    min_interval_seconds: float
    max_interval_seconds: float
    min_duration_seconds: float
    max_duration_seconds: float

    def __post_init__(self) -> None:
        if self.min_interval_seconds <= 0 or self.min_duration_seconds <= 0:
            raise ValueError("break intervals and durations must be positive")
        if self.min_interval_seconds > self.max_interval_seconds:
            raise ValueError("min_interval_seconds cannot exceed max_interval_seconds")
        if self.min_duration_seconds > self.max_duration_seconds:
            raise ValueError("min_duration_seconds cannot exceed max_duration_seconds")


class SessionDecision(str, Enum):
    CONTINUE = "continue"
    TAKE_BREAK = "take_break"
    STOP_SESSION = "stop_session"


class SessionPlanner:
    """Own session timing while leaving all behaviour decisions to scripts."""

    def __init__(self, budget: SessionBudget | None = None, break_policy: BreakPolicy | None = None, *,
                 events: RuntimeEventBus | None = None, clock: Callable[[], float] = time.monotonic,
                 uniform: Callable[[float, float], float] = random.uniform) -> None:
        self.budget = budget or SessionBudget()
        self.break_policy = break_policy
        self._events, self._clock, self._uniform = events, clock, uniform
        self._started_at: float | None = None
        self._next_break_at: float | None = None
        self._break_due_announced = self._budget_announced = False

    @property
    def started(self) -> bool:
        return self._started_at is not None

    @property
    def next_break_at(self) -> float | None:
        return self._next_break_at

    def start(self) -> None:
        """Start/reset a session. This does not cause a wait."""
        now = self._clock()
        self._started_at, self._next_break_at = now, self._schedule_break(now)
        self._break_due_announced = self._budget_announced = False
        self._emit("session_started", {"started_at": now, "next_break_at": self._next_break_at})

    def decide(self) -> SessionDecision:
        """Return a suggestion for the caller; do not alter bot flow."""
        if not self.started:
            self.start()
        now = self._clock()
        assert self._started_at is not None
        maximum = self.budget.max_session_seconds
        if maximum is not None and now - self._started_at >= maximum:
            if not self._budget_announced:
                self._emit("session_budget_reached", {"elapsed_seconds": now - self._started_at, "budget_seconds": maximum})
                self._budget_announced = True
            return SessionDecision.STOP_SESSION
        if self._next_break_at is not None and now >= self._next_break_at:
            if not self._break_due_announced:
                self._emit("session_break_due", {"due_at": self._next_break_at})
                self._break_due_announced = True
            return SessionDecision.TAKE_BREAK
        return SessionDecision.CONTINUE

    def break_if_due(self, cancellation: CancellationToken) -> SessionDecision:
        """Explicitly take a due break using an interruptible wait, then reschedule."""
        decision = self.decide()
        if decision is not SessionDecision.TAKE_BREAK:
            return decision
        duration = self._sample_duration()
        self._emit("session_break_started", {"duration_seconds": duration})
        try:
            cancellation.wait(duration)
        except BotCancelled:
            self._emit("session_break_cancelled", {"duration_seconds": duration})
            raise
        self._next_break_at = self._schedule_break(self._clock())
        self._break_due_announced = False
        self._emit("session_break_completed", {"duration_seconds": duration, "next_break_at": self._next_break_at})
        return SessionDecision.CONTINUE

    def _schedule_break(self, now: float) -> float | None:
        if self.break_policy is None:
            return None
        return now + self._uniform(self.break_policy.min_interval_seconds, self.break_policy.max_interval_seconds)

    def _sample_duration(self) -> float:
        if self.break_policy is None:
            raise RuntimeError("Cannot take a break without a BreakPolicy")
        return self._uniform(self.break_policy.min_duration_seconds, self.break_policy.max_duration_seconds)

    def _emit(self, name: str, payload: dict[str, float | None]) -> None:
        if self._events is not None:
            self._events.emit(name, payload)
