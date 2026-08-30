"""Small, reusable primitives for actions whose outcome must be observed."""

from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Callable


VerificationPredicate = Callable[[], bool]
Action = Callable[[], None]


@dataclass(frozen=True)
class RetryPolicy:
    """Bound retries for an action; a failed verification never loops forever."""

    max_attempts: int = 1
    retry_delay_seconds: float = 0.0

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be at least one")
        if self.retry_delay_seconds < 0:
            raise ValueError("retry_delay_seconds cannot be negative")


@dataclass(frozen=True)
class ActionResult:
    """The observable result of a bounded action attempt."""

    succeeded: bool
    attempts: int
    reason: str
    error: Exception | None = None


def perform_verified(
    action: Action,
    verify: VerificationPredicate | None = None,
    retry_policy: RetryPolicy | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> ActionResult:
    """Run *action* until it verifies or its bounded retry policy is exhausted.

    With no verifier, successful delivery of the action is the result.  Predicate
    exceptions fail closed and are returned to the caller rather than initiating
    additional input.
    """
    policy = retry_policy or RetryPolicy()
    for attempt in range(1, policy.max_attempts + 1):
        try:
            action()
        except Exception as error:
            return ActionResult(False, attempt, "action_error", error)

        if verify is None:
            return ActionResult(True, attempt, "delivered")
        try:
            if verify():
                return ActionResult(True, attempt, "verified")
        except Exception as error:
            return ActionResult(False, attempt, "verification_error", error)

        if attempt < policy.max_attempts and policy.retry_delay_seconds:
            sleep(policy.retry_delay_seconds)
    return ActionResult(False, policy.max_attempts, "verification_failed")
