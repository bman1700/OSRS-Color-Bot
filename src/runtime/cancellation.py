"""Cooperative cancellation and deadline helpers for bot scripts.

Python cannot safely terminate an arbitrary thread.  Scripts use these helpers at
their natural polling/wait points so a stop request is deterministic and leaves
input/runtime cleanup to the owning :class:`model.bot.Bot`.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable


class BotCancelled(RuntimeError):
    """Raised inside a script when its owning bot has been stopped."""


class ActionTimeoutError(TimeoutError):
    """Raised when a bounded action does not reach its expected condition."""


class CancellationToken:
    """Thread-safe cancellation signal shared by a bot and its script thread."""

    def __init__(self) -> None:
        self._event = threading.Event()
        self._reason: str | None = None

    @property
    def reason(self) -> str | None:
        return self._reason

    @property
    def is_cancelled(self) -> bool:
        return self._event.is_set()

    def cancel(self, reason: str = "Stop requested") -> None:
        self._reason = reason
        self._event.set()

    def raise_if_cancelled(self) -> None:
        if self.is_cancelled:
            raise BotCancelled(self.reason or "Stop requested")

    def wait(self, seconds: float) -> bool:
        """Wait interruptibly; return ``True`` only when the full wait elapsed."""
        self.raise_if_cancelled()
        cancelled = self._event.wait(max(0.0, seconds))
        if cancelled:
            raise BotCancelled(self.reason or "Stop requested")
        return True


def wait_for(
    predicate: Callable[[], bool],
    *,
    timeout: float,
    cancellation: CancellationToken,
    interval: float = 0.1,
    action: str = "action",
) -> None:
    """Wait for ``predicate`` or raise a clear cancellation/timeout exception."""
    if timeout < 0:
        raise ValueError("timeout must be non-negative")
    if interval <= 0:
        raise ValueError("interval must be positive")

    deadline = time.monotonic() + timeout
    while True:
        cancellation.raise_if_cancelled()
        if predicate():
            return
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ActionTimeoutError(f"Timed out waiting for {action} after {timeout:.2f}s")
        cancellation.wait(min(interval, remaining))
