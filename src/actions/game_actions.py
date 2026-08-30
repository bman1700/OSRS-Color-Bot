"""High-level game actions backed by the configured input provider."""

from __future__ import annotations

from utilities.input import InputProvider
from utilities.mouse import Mouse
from .verification import ActionResult, RetryPolicy, VerificationPredicate, perform_verified
from .transactional import InventoryDropOrder, RecoveryHook, click_until, drop_inventory, interact_then_wait


class GameActions:
    def __init__(self, mouse: Mouse, input_provider: InputProvider | None = None) -> None:
        self.mouse = mouse
        self.input_provider = input_provider

    def click_at(self, point: tuple[int, int], button: str = "left", **movement) -> None:
        self.mouse.move_to(point, **movement)
        self.mouse.click(button=button)

    def click_at_verified(
        self,
        point: tuple[int, int],
        verify: VerificationPredicate,
        button: str = "left",
        retry_policy: RetryPolicy | None = None,
        **movement,
    ) -> ActionResult:
        """Click a point and retry only when its requested state change is absent."""
        return perform_verified(
            lambda: self.click_at(point, button=button, **movement),
            verify=verify,
            retry_policy=retry_policy,
        )

    def click_until(
        self,
        point: tuple[int, int],
        verify: VerificationPredicate,
        *,
        button: str = "left",
        retry_policy: RetryPolicy | None = None,
        recovery: RecoveryHook | None = None,
        **movement,
    ) -> ActionResult:
        """Click a target until its immediate observable effect is present."""
        return click_until(
            lambda: self.click_at(point, button=button, **movement), verify, retry_policy=retry_policy, recovery=recovery
        )

    def interact_then_wait(
        self,
        interact,
        expected: VerificationPredicate,
        *,
        timeout: float,
        interval: float = 0.1,
        retry_policy: RetryPolicy | None = None,
        recovery: RecoveryHook | None = None,
    ) -> ActionResult:
        """Run an interaction and wait for the requested state transition."""
        return interact_then_wait(
            interact, expected, timeout=timeout, interval=interval, retry_policy=retry_policy, recovery=recovery
        )

    def drop_inventory(
        self,
        slots,
        *,
        skip_rows: int = 0,
        skip_slots=(),
        order: InventoryDropOrder | str = InventoryDropOrder.RANDOM,
    ) -> ActionResult:
        """Shift-drop inventory rectangles through the configured input path."""
        provider = self._provider()

        def move_and_click(slot) -> None:
            point = slot.random_point() if hasattr(slot, "random_point") else slot
            self.click_at((point[0], point[1]))

        return drop_inventory(
            slots,
            move_and_click=move_and_click,
            hold_shift=lambda: provider.key_down("shift"),
            release_shift=lambda: provider.key_up("shift"),
            skip_rows=skip_rows,
            skip_slots=skip_slots,
            order=order,
        )

    def click(self, button: str = "left") -> None:
        """Click at the current virtual-pointer position."""
        self.mouse.click(button=button)

    def move_to(self, point: tuple[int, int], **movement) -> None:
        self.mouse.move_to(point, **movement)

    def hold_key(self, key: str) -> None:
        self._provider().key_down(key)

    def release_key(self, key: str) -> None:
        self._provider().key_up(key)

    def _provider(self) -> InputProvider:
        if self.input_provider is None:
            raise RuntimeError("Game actions require a configured input provider")
        return self.input_provider
