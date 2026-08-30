import threading
import time

import pytest

from model.bot import Bot, BotStatus, BotThread
from runtime import ActionTimeoutError, BotCancelled, CancellationToken, wait_for


def test_cancellation_token_interrupts_wait_promptly():
    token = CancellationToken()
    result = []

    def sleeper():
        try:
            token.wait(10)
        except BotCancelled:
            result.append("cancelled")

    thread = threading.Thread(target=sleeper)
    thread.start()
    token.cancel("test stop")
    thread.join(timeout=0.5)

    assert not thread.is_alive()
    assert result == ["cancelled"]


def test_wait_for_has_named_deadline():
    with pytest.raises(ActionTimeoutError, match="client idle"):
        wait_for(lambda: False, timeout=0.02, interval=0.01, cancellation=CancellationToken(), action="client idle")


def test_bot_thread_stop_is_cooperative_not_async_exception():
    token = CancellationToken()
    observed = []

    def worker():
        try:
            token.wait(10)
        except BotCancelled:
            observed.append("cleaned up")

    thread = BotThread(worker, token)
    thread.start()
    thread.stop("button clicked")
    thread.join(timeout=0.5)

    assert not thread.is_alive()
    assert observed == ["cleaned up"]


class _Runtime:
    def __init__(self):
        self.events = type("Events", (), {"emit": lambda *_: None})()
        self.stop_calls = 0

    def emit(self, *_):
        pass

    def stop(self):
        self.stop_calls += 1


class _FailingBot(Bot):
    def __init__(self):
        window = type("Window", (), {"zones": object()})()
        Bot.__init__(self, "test", "test", "test", window)
        self.runtime = _Runtime()

    def main_loop(self):
        raise ActionTimeoutError("target did not change")

    def create_options(self):
        pass

    def save_options(self, options):
        pass


def test_timeout_transitions_bot_to_fail_safe_and_cleans_runtime():
    bot = _FailingBot()
    bot.set_status(BotStatus.RUNNING)

    bot._run_main_loop()

    assert bot.status is BotStatus.FAILED_SAFE
    assert bot.should_stop()
    assert bot.runtime.stop_calls == 1
