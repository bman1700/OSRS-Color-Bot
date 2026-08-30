"""Composable, bounded game-action mechanics.

These helpers keep the three parts of a game interaction together: delivering
input, observing the requested state transition, and making one explicit
recovery decision if that transition does not arrive.
"""

from __future__ import annotations

import random
import time
from collections.abc import Callable, Iterable, Sequence
from enum import Enum

from .verification import Action, ActionResult, RetryPolicy, VerificationPredicate


RecoveryHook = Callable[[ActionResult], None]
Slot = object


class InventoryDropOrder(str, Enum):
    """Traversal patterns for row-major inventory slot collections."""

    ROW_MAJOR = "row_major"
    RANDOM = "random"
    COLUMN_SERPENTINE = "column_serpentine"
    CENTER_OUT = "center_out"


def wait_for(
    predicate: VerificationPredicate,
    *,
    timeout: float,
    interval: float = 0.1,
    sleep: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
) -> ActionResult:
    """Poll a state predicate for a bounded period and return its observation.

    Unlike ``runtime.wait_for`` this is deliberately result-based, so a failed
    condition can participate in a retry/recovery transaction without using an
    exception as normal control flow.
    """
    if timeout < 0:
        raise ValueError("timeout must be non-negative")
    if interval <= 0:
        raise ValueError("interval must be positive")

    started = monotonic()
    observations = 0
    while True:
        observations += 1
        try:
            if predicate():
                return ActionResult(True, observations, "verified")
        except Exception as error:
            return ActionResult(False, observations, "verification_error", error)
        remaining = timeout - (monotonic() - started)
        if remaining <= 0:
            return ActionResult(False, observations, "verification_failed")
        sleep(min(interval, remaining))


def click_until(
    click: Action,
    verify: VerificationPredicate,
    *,
    retry_policy: RetryPolicy | None = None,
    recovery: RecoveryHook | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> ActionResult:
    """Click and immediately verify the result, with a finite retry budget."""
    policy = retry_policy or RetryPolicy()
    for attempt in range(1, policy.max_attempts + 1):
        try:
            click()
        except Exception as error:
            return _recover(ActionResult(False, attempt, "action_error", error), recovery)
        try:
            if verify():
                return ActionResult(True, attempt, "verified")
        except Exception as error:
            return _recover(ActionResult(False, attempt, "verification_error", error), recovery)
        if attempt < policy.max_attempts and policy.retry_delay_seconds:
            sleep(policy.retry_delay_seconds)
    return _recover(ActionResult(False, policy.max_attempts, "verification_failed"), recovery)


def interact_then_wait(
    interact: Action,
    expected: VerificationPredicate,
    *,
    timeout: float,
    interval: float = 0.1,
    retry_policy: RetryPolicy | None = None,
    recovery: RecoveryHook | None = None,
    sleep: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
) -> ActionResult:
    """Perform an interaction then wait for its expected state transition."""
    policy = retry_policy or RetryPolicy()
    for attempt in range(1, policy.max_attempts + 1):
        try:
            interact()
        except Exception as error:
            return _recover(ActionResult(False, attempt, "action_error", error), recovery)
        observed = wait_for(expected, timeout=timeout, interval=interval, sleep=sleep, monotonic=monotonic)
        if observed.succeeded:
            return ActionResult(True, attempt, "verified")
        if observed.reason == "verification_error":
            return _recover(ActionResult(False, attempt, observed.reason, observed.error), recovery)
        if attempt < policy.max_attempts and policy.retry_delay_seconds:
            sleep(policy.retry_delay_seconds)
    return _recover(ActionResult(False, policy.max_attempts, "verification_failed"), recovery)


def drop_inventory(
    slots: Sequence[Slot],
    *,
    move_and_click: Callable[[Slot], None],
    hold_shift: Action,
    release_shift: Action,
    skip_rows: int = 0,
    skip_slots: Iterable[int] = (),
    order: InventoryDropOrder | str = InventoryDropOrder.RANDOM,
    rng: random.Random | None = None,
) -> ActionResult:
    """Shift-drop chosen inventory slots using a selectable traversal pattern.

    ``slots`` are normally row-major inventory rectangles, but the function is
    intentionally UI-agnostic: ``move_and_click`` decides how a slot is
    targeted.  The shift key is always released, including after input errors.
    """
    if skip_rows < 0:
        raise ValueError("skip_rows cannot be negative")
    try:
        selected_order = InventoryDropOrder(order)
    except ValueError as error:
        raise ValueError(f"Unknown inventory drop order: {order!r}") from error

    skipped = set(skip_slots)
    skipped.update(range(skip_rows * 4))
    indexed_slots = [(index, slot) for index, slot in enumerate(slots) if index not in skipped]
    ordered = _order_slots(indexed_slots, selected_order, rng or random.Random())
    if not ordered:
        return ActionResult(True, 0, "delivered")

    attempts = 0
    error: Exception | None = None
    shift_held = False
    try:
        hold_shift()
        shift_held = True
        for _, slot in ordered:
            move_and_click(slot)
            attempts += 1
    except Exception as action_error:
        error = action_error
    finally:
        # A modifier stuck down is worse than a partially dropped inventory.
        if shift_held:
            try:
                release_shift()
            except Exception as release_error:
                if error is None:
                    error = release_error
    if error is not None:
        return ActionResult(False, attempts, "action_error", error)
    return ActionResult(True, attempts, "delivered")


def _recover(result: ActionResult, recovery: RecoveryHook | None) -> ActionResult:
    if result.succeeded or recovery is None:
        return result
    try:
        recovery(result)
    except Exception as error:
        return ActionResult(False, result.attempts, "recovery_error", error)
    return result


def _order_slots(
    slots: list[tuple[int, Slot]], order: InventoryDropOrder, rng: random.Random
) -> list[tuple[int, Slot]]:
    if order is InventoryDropOrder.ROW_MAJOR:
        return slots
    if order is InventoryDropOrder.RANDOM:
        ordered = list(slots)
        rng.shuffle(ordered)
        return ordered
    if order is InventoryDropOrder.COLUMN_SERPENTINE:
        return sorted(slots, key=lambda entry: (entry[0] % 4, entry[0] // 4 if (entry[0] % 4) % 2 == 0 else -(entry[0] // 4)))
    # Center-out avoids a mechanical top-left to bottom-right sweep.  Random
    # tie breaking retains variation for symmetrically placed slots.
    return sorted(slots, key=lambda entry: (abs(entry[0] // 4 - 3.5) + abs(entry[0] % 4 - 1.5), rng.random()))
