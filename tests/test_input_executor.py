import threading
import time

import pytest

from utilities.input_executor import InputCancellationToken, InputCancelledError, InputExecutor


def test_executor_preserves_command_order_and_cadence():
    executor = InputExecutor(cadence_hz=100)
    events = []
    delivered_at = []
    try:
        def append(value):
            events.append(value)
            delivered_at.append(time.monotonic())

        executor.execute(lambda session: (session.call(append, "first"), session.call(append, "second")))
        assert events == ["first", "second"]
        assert delivered_at[1] - delivered_at[0] >= 0.008
    finally:
        executor.shutdown()


def test_executor_cancels_before_delivery():
    executor = InputExecutor()
    token = InputCancellationToken()
    token.cancel()
    try:
        with pytest.raises(InputCancelledError):
            executor.execute(lambda session: session.call(lambda: None), token)
    finally:
        executor.shutdown()


def test_executor_serializes_actions_from_different_threads():
    executor = InputExecutor(cadence_hz=1000)
    events = []
    started = threading.Event()

    def first(session):
        session.call(events.append, "first-start")
        started.set()
        time.sleep(0.03)
        session.call(events.append, "first-end")

    try:
        thread = threading.Thread(target=lambda: executor.execute(first))
        thread.start()
        assert started.wait(1)
        executor.execute(lambda session: session.call(events.append, "second"))
        thread.join(1)
        assert events == ["first-start", "first-end", "second"]
    finally:
        executor.shutdown()
