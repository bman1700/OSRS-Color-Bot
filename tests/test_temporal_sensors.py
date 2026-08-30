import pytest

from runtime import ActionTimeoutError, CancellationToken, ChangedForTicks, Debounced, SensorService, StableForTicks, TemporalSensors


def snapshot(tick, animation=None):
    return SensorService().snapshot({"tick": tick, "attack": {"animationId": animation}})


def test_debounce_and_stability_require_distinct_ticks():
    idle = lambda tick: snapshot(tick, animation=-1)
    predicate = Debounced(lambda state: state.player_idle, ticks=2)
    assert not predicate(idle(1))
    assert not predicate(idle(1))  # polling twice in the same game tick is not confirmation
    assert predicate(idle(2))

    stable = StableForTicks("animation_id", ticks=2)
    assert not stable(snapshot(1, animation=42))
    assert stable(snapshot(2, animation=42))


def test_changed_for_ticks_captures_baseline_and_resets_on_revert():
    changed = ChangedForTicks("animation_id", ticks=2)
    assert not changed(snapshot(1, animation=10))
    assert not changed(snapshot(2, animation=11))
    assert not changed(snapshot(3, animation=10))
    assert not changed(snapshot(4, animation=11))
    assert changed(snapshot(5, animation=11))


def test_stale_data_detects_non_advancing_tick():
    states = iter([snapshot(7, animation=1), snapshot(7, animation=1)])
    sensors = TemporalSensors(lambda: next(states), stale_after=1)
    sensors.snapshot()
    first_time = sensors._last_received_at
    sensors.snapshot()
    assert sensors.is_stale(now=first_time + 1.01)


def test_expected_transition_waits_for_previous_then_debounced_target():
    states = iter([snapshot(1, animation=5), snapshot(2, animation=6), snapshot(3, animation=6)])
    sensors = TemporalSensors(lambda: next(states))
    result = sensors.wait_for_transition("animation_id", 6, previous=5, ticks=2, timeout=0.1,
                                         interval=0.001, cancellation=CancellationToken())
    assert result.tick == 3


def test_wait_can_reject_stale_data():
    sensors = TemporalSensors(lambda: snapshot(1, animation=6), stale_after=0)
    sensors.snapshot()
    sensors._last_received_at = 0
    with pytest.raises(ActionTimeoutError):
        sensors.wait_for(lambda _: True, timeout=0.01, interval=0.001, cancellation=CancellationToken(), reject_stale=True)
