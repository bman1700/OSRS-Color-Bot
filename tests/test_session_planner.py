import threading
import time

import pytest

from runtime import BotCancelled, BreakPolicy, CancellationToken, RuntimeEventBus, SessionBudget, SessionDecision, SessionPlanner


class Clock:
    def __init__(self, now=100.0): self.now = now
    def __call__(self): return self.now


def test_planner_is_inert_until_a_script_explicitly_uses_it():
    planner = SessionPlanner()
    assert not planner.started and planner.next_break_at is None


def test_planner_reports_due_break_and_emits_lifecycle_events():
    clock, events, bus = Clock(), [], RuntimeEventBus()
    for name in ("session_started", "session_break_due", "session_break_started", "session_break_completed"):
        bus.subscribe(name, events.append)
    planner = SessionPlanner(break_policy=BreakPolicy(10, 10, 2, 2), events=bus, clock=clock, uniform=lambda low, high: low)
    assert planner.decide() is SessionDecision.CONTINUE
    clock.now += 10
    assert planner.decide() is SessionDecision.TAKE_BREAK
    assert planner.break_if_due(CancellationToken()) is SessionDecision.CONTINUE
    assert [event.name for event in events] == ["session_started", "session_break_due", "session_break_started", "session_break_completed"]
    assert planner.next_break_at == 120


def test_budget_is_a_script_decision_and_does_not_cancel_token():
    clock, events, bus = Clock(), [], RuntimeEventBus()
    bus.subscribe("session_budget_reached", events.append)
    planner = SessionPlanner(SessionBudget(5), events=bus, clock=clock)
    token = CancellationToken()
    planner.start(); clock.now += 5
    assert planner.decide() is SessionDecision.STOP_SESSION
    assert not token.is_cancelled and events[0].payload["budget_seconds"] == 5


def test_due_break_wait_is_interrupted_by_cancellation_and_reported():
    clock, events, bus = Clock(), [], RuntimeEventBus()
    bus.subscribe("session_break_cancelled", events.append)
    planner = SessionPlanner(break_policy=BreakPolicy(1, 1, 20, 20), events=bus, clock=clock, uniform=lambda low, high: low)
    planner.start(); clock.now += 1
    token, errors = CancellationToken(), []
    def take_break():
        try: planner.break_if_due(token)
        except BotCancelled as error: errors.append(error)
    thread = threading.Thread(target=take_break); thread.start()
    time.sleep(0.02); token.cancel("test stop"); thread.join(timeout=0.5)
    assert not thread.is_alive() and errors
    assert [event.name for event in events] == ["session_break_cancelled"]


def test_invalid_session_configuration_is_rejected():
    with pytest.raises(ValueError): SessionBudget(0)
    with pytest.raises(ValueError): BreakPolicy(2, 1, 1, 1)
    with pytest.raises(ValueError): BreakPolicy(1, 1, 2, 1)
