import random

from actions import InventoryDropOrder, RetryPolicy, click_until, drop_inventory, interact_then_wait, wait_for


def test_wait_for_reports_an_eventual_state_change():
    polls = []

    result = wait_for(lambda: (polls.append(1) or len(polls) == 2), timeout=1, interval=0.01)

    assert result.succeeded
    assert result.attempts == 2
    assert result.reason == "verified"


def test_click_until_runs_recovery_after_its_bounded_retry_budget():
    clicks = []
    recovered = []

    result = click_until(
        lambda: clicks.append("click"),
        lambda: False,
        retry_policy=RetryPolicy(max_attempts=2),
        recovery=lambda failure: recovered.append((failure.reason, failure.attempts)),
    )

    assert not result.succeeded
    assert clicks == ["click", "click"]
    assert recovered == [("verification_failed", 2)]


def test_interact_then_wait_retries_only_after_a_missing_transition():
    interactions = []

    result = interact_then_wait(
        lambda: interactions.append("tree"),
        lambda: len(interactions) == 2,
        timeout=0,
        retry_policy=RetryPolicy(max_attempts=2),
    )

    assert result.succeeded
    assert result.attempts == 2


def test_drop_inventory_skips_slots_uses_selected_order_and_releases_shift_on_failure():
    events = []

    result = drop_inventory(
        list(range(8)),
        move_and_click=lambda slot: events.append(("drop", slot)) if slot != 6 else (_ for _ in ()).throw(OSError("lost input")),
        hold_shift=lambda: events.append(("key", "down")),
        release_shift=lambda: events.append(("key", "up")),
        skip_rows=1,
        skip_slots=[5],
        order=InventoryDropOrder.ROW_MAJOR,
    )

    assert not result.succeeded
    assert result.attempts == 1
    assert events == [("key", "down"), ("drop", 4), ("key", "up")]


def test_drop_inventory_random_order_is_selectable_and_seedable():
    delivered = []

    result = drop_inventory(
        list(range(6)),
        move_and_click=delivered.append,
        hold_shift=lambda: None,
        release_shift=lambda: None,
        order="random",
        rng=random.Random(3),
    )

    assert result.succeeded
    assert sorted(delivered) == list(range(6))
    assert delivered != list(range(6))
