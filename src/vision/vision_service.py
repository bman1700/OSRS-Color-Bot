"""Vision facade that scopes HSV detection to named client zones."""

from __future__ import annotations

import random
from typing import Any

from utilities.hsv_color import ColorRegion, HSVColorProfile, find_regions


class VisionService:
    def __init__(self, zones: Any) -> None:
        self.zones = zones

    def find_hsv(self, zone_name: str, profile: HSVColorProfile) -> list[ColorRegion]:
        return find_regions(getattr(self.zones, zone_name).screenshot(), profile)

    def random_hsv_point(self, zone_name: str, profile: HSVColorProfile, rng: random.Random | None = None) -> tuple[int, int] | None:
        regions = self.find_hsv(zone_name, profile)
        if not regions:
            return None
        zone = getattr(self.zones, zone_name)
        return zone.to_screen(regions[0].random_point(rng))
