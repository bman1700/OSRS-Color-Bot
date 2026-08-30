"""Fail-closed recognition of the RuneLite red click marker."""

from __future__ import annotations

from collections.abc import Callable

import numpy as np


def has_red_click_marker(
    image: np.ndarray,
    screen_point: tuple[int, int],
    screenshot_origin: tuple[int, int],
    radius: int = 10,
    minimum_pixels: int = 3,
) -> bool:
    """Return whether a BGR/BGRA screenshot contains marker-red near a point.

    The image is sampled only in a compact, bounds-checked neighbourhood.  It
    deliberately requires several saturated red pixels, avoiding a positive
    result from a single noisy or unrelated pixel.
    """
    if radius < 0 or minimum_pixels < 1:
        raise ValueError("radius must be non-negative and minimum_pixels positive")
    if not isinstance(image, np.ndarray) or image.ndim != 3 or image.shape[2] < 3:
        return False
    x = int(screen_point[0] - screenshot_origin[0])
    y = int(screen_point[1] - screenshot_origin[1])
    height, width = image.shape[:2]
    left, right = max(0, x - radius), min(width, x + radius + 1)
    top, bottom = max(0, y - radius), min(height, y + radius + 1)
    if left >= right or top >= bottom:
        return False

    region = image[top:bottom, left:right, :3].astype(np.int16)
    blue, green, red = region[:, :, 0], region[:, :, 1], region[:, :, 2]
    saturated_red = (red >= 150) & (red >= green + 60) & (red >= blue + 60)
    return int(np.count_nonzero(saturated_red)) >= minimum_pixels


class RedClickVerifier:
    """Capture and inspect a screenshot after a click, failing closed on capture errors."""

    def __init__(self, screenshot: Callable[[], np.ndarray], screenshot_origin: tuple[int, int]) -> None:
        self._screenshot = screenshot
        self._screenshot_origin = screenshot_origin

    def __call__(self, screen_point: tuple[int, int]) -> bool:
        try:
            return has_red_click_marker(self._screenshot(), screen_point, self._screenshot_origin)
        except (OSError, RuntimeError, ValueError):
            return False
