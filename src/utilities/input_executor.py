"""Serialized, paced delivery of remote input commands.

The executor deliberately owns *when* native input calls are made.  Path
generation remains synchronous and deterministic, while delivery happens on
one worker so concurrent bot code cannot interleave movements and clicks.
"""

from __future__ import annotations

import queue
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, TypeVar


T = TypeVar("T")


class InputCancelledError(RuntimeError):
    """Raised when a queued or in-progress input action is cancelled."""


class InputCancellationToken:
    """A cooperative cancellation signal for one input action."""

    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()


class _InputSession:
    def __init__(self, executor: "InputExecutor", token: InputCancellationToken) -> None:
        self._executor = executor
        self._token = token

    def call(self, command: Callable[..., T], *args, **kwargs) -> T:
        """Deliver one native command, respecting cadence and cancellation."""
        self._executor._deliver(command, self._token, *args, **kwargs)
        return None  # Native input commands do not currently return a value.


@dataclass
class _Task:
    action: Callable[[_InputSession], T]
    token: InputCancellationToken
    completed: threading.Event = field(default_factory=threading.Event)
    result: object | None = None
    error: BaseException | None = None


class InputExecutor:
    """Run ordered input actions on one worker at a bounded command cadence.

    ``execute`` intentionally waits for completion, preserving the existing
    synchronous mouse API.  The worker is still valuable because every action
    shares a single ordering point, including calls initiated by different
    threads.
    """

    def __init__(self, cadence_hz: float = 60.0) -> None:
        if cadence_hz <= 0:
            raise ValueError("cadence_hz must be positive")
        self.cadence_hz = cadence_hz
        self._interval = 1.0 / cadence_hz
        self._tasks: queue.Queue[_Task | None] = queue.Queue()
        self._shutdown = threading.Event()
        self._last_delivery: float | None = None
        self._active_token: InputCancellationToken | None = None
        self._active_lock = threading.Lock()
        self._worker = threading.Thread(target=self._run, name="input-executor", daemon=True)
        self._worker.start()

    def execute(self, action: Callable[[_InputSession], T], cancellation: InputCancellationToken | None = None) -> T:
        """Queue an action and wait for its ordered, paced delivery."""
        if self._shutdown.is_set():
            raise RuntimeError("Input executor has been shut down")
        task = _Task(action, cancellation or InputCancellationToken())
        self._tasks.put(task)
        while not task.completed.wait(0.05):
            if task.token.cancelled:
                # The worker checks the same token before every command.
                continue
        if task.error is not None:
            raise task.error
        return task.result  # type: ignore[return-value]

    def cancel_pending(self) -> None:
        """Cooperatively cancel the active action and queued actions."""
        with self._active_lock:
            if self._active_token is not None:
                self._active_token.cancel()
        # Queue entries own their tokens; drain/requeue is intentionally avoided
        # so FIFO ordering remains deterministic for callers already waiting.
        drained: list[_Task | None] = []
        while True:
            try:
                item = self._tasks.get_nowait()
            except queue.Empty:
                break
            if item is not None:
                item.token.cancel()
            drained.append(item)
        for item in drained:
            self._tasks.put(item)

    def shutdown(self) -> None:
        self._shutdown.set()
        self.cancel_pending()
        self._tasks.put(None)
        self._worker.join(timeout=1.0)

    def _run(self) -> None:
        while True:
            task = self._tasks.get()
            if task is None:
                return
            try:
                with self._active_lock:
                    self._active_token = task.token
                self._check_cancelled(task.token)
                task.result = task.action(_InputSession(self, task.token))
            except BaseException as error:
                task.error = error
            finally:
                with self._active_lock:
                    self._active_token = None
                task.completed.set()

    def _deliver(self, command: Callable[..., T], token: InputCancellationToken, *args, **kwargs) -> T:
        self._check_cancelled(token)
        if self._last_delivery is not None:
            delay = self._interval - (time.monotonic() - self._last_delivery)
            while delay > 0:
                self._check_cancelled(token)
                time.sleep(min(delay, 0.01))
                delay = self._interval - (time.monotonic() - self._last_delivery)
        self._check_cancelled(token)
        result = command(*args, **kwargs)
        self._last_delivery = time.monotonic()
        return result

    @staticmethod
    def _check_cancelled(token: InputCancellationToken) -> None:
        if token.cancelled:
            raise InputCancelledError("Input action was cancelled")
