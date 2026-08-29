"""Client lifecycle wrapper around the existing Window implementation."""

from __future__ import annotations

from typing import Any


class RuneLiteClient:
    def __init__(self, window: Any) -> None:
        self.window = window

    @property
    def zones(self):
        return self.window.zones

    def initialize(self) -> tuple[int, int]:
        self.window.focus()
        self.window.initialize()
        origin = self.window.position()
        return origin.x, origin.y + self.window.padding_top
