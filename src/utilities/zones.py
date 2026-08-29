"""Live client zones built on the existing window rectangle model."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass
class Zone:
    """A named region whose rectangle is resolved at use time."""

    name: str
    rectangle_provider: Callable[[], Any]
    exclusions: list[dict[str, int]] | None = None

    def __post_init__(self) -> None:
        if self.exclusions is None:
            self.exclusions = []

    @property
    def rectangle(self) -> Any:
        rect = self.rectangle_provider()
        if rect is None:
            raise RuntimeError(f"Zone '{self.name}' has not been initialized")
        return rect

    def screenshot(self):
        image = self.rectangle.screenshot()
        if not self.exclusions:
            return image
        image = image.copy()
        for exclusion in self.exclusions:
            left = max(0, exclusion["left"])
            top = max(0, exclusion["top"])
            right = min(image.shape[1], left + exclusion["width"])
            bottom = min(image.shape[0], top + exclusion["height"])
            image[top:bottom, left:right] = 0
        return image

    def add_exclusion(self, left: int, top: int, width: int, height: int) -> None:
        if width < 0 or height < 0:
            raise ValueError("Zone exclusion dimensions must not be negative")
        self.exclusions.append({"left": int(left), "top": int(top), "width": int(width), "height": int(height)})

    def clear_exclusions(self) -> None:
        self.exclusions.clear()

    def contains_screen(self, point: tuple[int, int]) -> bool:
        rect = self.rectangle
        return rect.left <= point[0] < rect.left + rect.width and rect.top <= point[1] < rect.top + rect.height

    def contains_relative(self, point: tuple[int, int]) -> bool:
        rect = self.rectangle
        return 0 <= point[0] < rect.width and 0 <= point[1] < rect.height

    def relative_rectangle(self) -> dict[str, int]:
        """Return the current zone bounds in zone-local coordinates."""
        rect = self.rectangle
        return {"left": 0, "top": 0, "width": int(rect.width), "height": int(rect.height)}

    def screen_rectangle(self) -> dict[str, int]:
        """Return the current zone bounds in screen coordinates."""
        rect = self.rectangle
        return {"left": int(rect.left), "top": int(rect.top), "width": int(rect.width), "height": int(rect.height)}

    def detect(self, detector: Callable[[Any], Any]) -> Any:
        """Run a caller-supplied detector against this zone's current image."""
        return detector(self.screenshot())

    def to_screen(self, point: tuple[int, int]) -> tuple[int, int]:
        rect = self.rectangle
        return rect.left + int(point[0]), rect.top + int(point[1])

    def to_relative(self, point: tuple[int, int]) -> tuple[int, int]:
        rect = self.rectangle
        return int(point[0]) - rect.left, int(point[1]) - rect.top


class ZoneSet:
    """Standard RuneLite zones backed by a Window instance's current rectangles."""

    def __init__(self, window: Any) -> None:
        self.client = Zone("client", window.rectangle)
        self.game_view = Zone("game_view", lambda: window.game_view)
        self.inventory = Zone("inventory", lambda: window.control_panel)
        self.control_panel = self.inventory
        self.minimap = Zone("minimap", lambda: window.minimap)
        self.chat = Zone("chat", lambda: window.chat)
        self.mouseover = Zone("mouseover", lambda: window.mouseover)
