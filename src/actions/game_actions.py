"""High-level game actions backed by the configured input provider."""

from __future__ import annotations

from utilities.input import InputProvider
from utilities.mouse import Mouse


class GameActions:
    def __init__(self, mouse: Mouse, input_provider: InputProvider | None = None) -> None:
        self.mouse = mouse
        self.input_provider = input_provider

    def click_at(self, point: tuple[int, int], button: str = "left", **movement) -> None:
        self.mouse.move_to(point, **movement)
        self.mouse.click(button=button)

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
