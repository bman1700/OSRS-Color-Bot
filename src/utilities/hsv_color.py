"""Reusable HSV color profiles and region extraction helpers."""

from __future__ import annotations

import json
import random
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np


@dataclass(frozen=True)
class HSVColorProfile:
    name: str
    lower: tuple[int, int, int]
    upper: tuple[int, int, int]
    min_area: int = 1
    morphology_kernel: int = 0
    morphology_iterations: int = 1

    def __post_init__(self) -> None:
        if len(self.lower) != 3 or len(self.upper) != 3:
            raise ValueError("HSV bounds must contain H, S, and V")
        if any(value < 0 for value in self.lower + self.upper):
            raise ValueError("HSV bounds must not be negative")
        if self.lower[1] > 255 or self.upper[1] > 255 or self.lower[2] > 255 or self.upper[2] > 255:
            raise ValueError("HSV saturation and value must be at most 255")
        if self.lower[0] > 179 or self.upper[0] > 179:
            raise ValueError("OpenCV hue must be between 0 and 179")
        if self.min_area < 1 or self.morphology_kernel < 0 or self.morphology_iterations < 1:
            raise ValueError("Area must be positive and morphology values must be valid")

    @classmethod
    def from_rgb(cls, name: str, rgb: tuple[int, int, int], tolerance: tuple[int, int, int] = (5, 30, 30), **kwargs: Any) -> "HSVColorProfile":
        """Create a profile around an RGB target using OpenCV HSV ranges."""
        if any(not 0 <= value <= 255 for value in rgb):
            raise ValueError("RGB values must be between 0 and 255")
        pixel = np.uint8([[list(rgb[::-1])]])
        hue, saturation, value = map(int, cv2.cvtColor(pixel, cv2.COLOR_BGR2HSV)[0, 0])
        dh, ds, dv = tolerance
        return cls(name, (max(0, hue - dh), max(0, saturation - ds), max(0, value - dv)), (min(179, hue + dh), min(255, saturation + ds), min(255, value + dv)), **kwargs)


@dataclass(frozen=True)
class ColorRegion:
    left: int
    top: int
    width: int
    height: int
    area: int

    @property
    def center(self) -> tuple[int, int]:
        return self.left + self.width // 2, self.top + self.height // 2

    def random_point(self, rng: random.Random | None = None) -> tuple[int, int]:
        rng = rng or random.Random()
        return rng.randrange(self.left, self.left + self.width), rng.randrange(self.top, self.top + self.height)


def rgb_to_hsv(rgb: tuple[int, int, int]) -> tuple[int, int, int]:
    """Convert one RGB color to OpenCV's integer HSV representation."""
    profile = HSVColorProfile.from_rgb("conversion", rgb, tolerance=(0, 0, 0))
    return profile.lower


def hsv_mask(image_bgr: np.ndarray, profile: HSVColorProfile) -> np.ndarray:
    """Return a cleaned binary mask for a BGR image and profile."""
    hsv = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2HSV)
    lower = np.array(profile.lower, dtype=np.uint8)
    upper = np.array(profile.upper, dtype=np.uint8)
    if profile.lower[0] <= profile.upper[0]:
        mask = cv2.inRange(hsv, lower, upper)
    else:
        # Hue wraps at red (179 -> 0).
        first = cv2.inRange(hsv, lower, np.array([179, profile.upper[1], profile.upper[2]], dtype=np.uint8))
        second = cv2.inRange(hsv, np.array([0, profile.lower[1], profile.lower[2]], dtype=np.uint8), upper)
        mask = cv2.bitwise_or(first, second)
    if profile.morphology_kernel:
        kernel = np.ones((profile.morphology_kernel, profile.morphology_kernel), dtype=np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=profile.morphology_iterations)
    return mask


def regions_from_mask(mask: np.ndarray, min_area: int = 1) -> list[ColorRegion]:
    """Extract connected regions from a binary mask."""
    count, _, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    regions = []
    for index in range(1, count):
        left, top, width, height, area = map(int, stats[index])
        if area >= min_area:
            regions.append(ColorRegion(left, top, width, height, area))
    return regions


def find_regions(image_bgr: np.ndarray, profile: HSVColorProfile) -> list[ColorRegion]:
    return regions_from_mask(hsv_mask(image_bgr, profile), profile.min_area)


class HSVProfileStore:
    """JSON persistence for named HSV profiles."""

    def save(self, path: str | Path, profiles: list[HSVColorProfile]) -> None:
        Path(path).write_text(json.dumps([asdict(profile) for profile in profiles], indent=2), encoding="utf-8")

    def load(self, path: str | Path) -> list[HSVColorProfile]:
        records = json.loads(Path(path).read_text(encoding="utf-8"))
        return [HSVColorProfile(name=item["name"], lower=tuple(item["lower"]), upper=tuple(item["upper"]), min_area=item.get("min_area", 1), morphology_kernel=item.get("morphology_kernel", 0), morphology_iterations=item.get("morphology_iterations", 1)) for item in records]
