"""Vision facade that scopes HSV detection to named client zones."""

from __future__ import annotations

import random
from pathlib import Path
from typing import Any

from utilities.hsv_color import ColorRegion, DetectionResult, HSVColorProfile, find_regions
from utilities.imagesearch import search_img_in_rect
import utilities.ocr as ocr
from utilities.runelite_cv import extract_objects


class _ZoneRectangle:
    """Rectangle-compatible view that preserves zone masking for legacy OCR."""

    def __init__(self, zone: Any) -> None:
        self.zone = zone
        rect = zone.rectangle
        self.left, self.top = rect.left, rect.top
        self.width, self.height = rect.width, rect.height

    def screenshot(self):
        return self.zone.screenshot()


class VisionService:
    def __init__(self, zones: Any) -> None:
        self.zones = zones

    def find_hsv(self, zone_name: str, profile: HSVColorProfile) -> list[ColorRegion]:
        return find_regions(getattr(self.zones, zone_name).screenshot(), profile)

    @staticmethod
    def _metadata(zone_name: str, zone: Any, bounds: ColorRegion, **extra: Any) -> dict[str, Any]:
        screen_left, screen_top = zone.to_screen((bounds.left, bounds.top))
        return {
            "zone": zone_name,
            "local_bounds": {"left": bounds.left, "top": bounds.top, "width": bounds.width, "height": bounds.height},
            "screen_bounds": {"left": screen_left, "top": screen_top, "width": bounds.width, "height": bounds.height},
            **extra,
        }

    def detect_hsv(self, zone_name: str, profile: HSVColorProfile) -> list[DetectionResult]:
        """Detect regions and return script-facing structured results."""
        zone = getattr(self.zones, zone_name)
        image = zone.screenshot()
        image_area = max(1, image.shape[0] * image.shape[1])
        return [
            DetectionResult(
                region,
                profile.name,
                min(1.0, region.area / image_area),
                self._metadata(zone_name, zone, region, pixel_count=region.area, fill_ratio=region.area / max(1, region.width * region.height)),
            )
            for region in find_regions(image, profile)
        ]

    def find_image(self, zone_name: str, template: str | Path | Any, confidence: float = 0.15) -> DetectionResult:
        """Find one template in a zone and return a structured result."""
        zone = getattr(self.zones, zone_name)
        found = search_img_in_rect(template, zone.screenshot(), confidence)
        if found is None:
            return DetectionResult(None, f"image:{template}", metadata={"zone": zone_name, "template": str(template)})
        bounds = ColorRegion(int(found.left), int(found.top), int(found.width), int(found.height), int(found.width * found.height))
        return DetectionResult(bounds, f"image:{template}", 1.0, self._metadata(zone_name, zone, bounds, template=str(template)))

    def find_objects(self, zone_name: str, image: Any | None = None) -> list[DetectionResult]:
        """Adapt legacy outline extraction to structured, zone-relative results."""
        zone = getattr(self.zones, zone_name)
        objects = extract_objects(image if image is not None else zone.screenshot())
        return [
            DetectionResult(
                ColorRegion(int(obj._x_min), int(obj._y_min), int(obj._width), int(obj._height), int(obj._axis.shape[0])),
                "outline",
                min(1.0, obj._axis.shape[0] / max(1, obj._width * obj._height)),
                self._metadata(
                    zone_name,
                    zone,
                    ColorRegion(int(obj._x_min), int(obj._y_min), int(obj._width), int(obj._height), int(obj._axis.shape[0])),
                    pixel_count=int(obj._axis.shape[0]),
                    kind="outline",
                ),
            )
            for obj in objects
        ]

    def find_text(self, zone_name: str, text: str | list[str], font: dict, color: Any) -> list[DetectionResult]:
        """Return structured OCR matches while retaining the legacy OCR engine."""
        zone = getattr(self.zones, zone_name)
        matches = ocr.find_text(text, _ZoneRectangle(zone), font, color)
        return [
            DetectionResult(
                ColorRegion(int(match.left - zone.rectangle.left), int(match.top - zone.rectangle.top), int(match.width), int(match.height), int(match.width * match.height)),
                f"ocr:{text}",
                1.0,
                self._metadata(
                    zone_name,
                    zone,
                    ColorRegion(int(match.left - zone.rectangle.left), int(match.top - zone.rectangle.top), int(match.width), int(match.height), int(match.width * match.height)),
                    kind="ocr",
                ),
            )
            for match in matches
        ]

    def random_hsv_point(self, zone_name: str, profile: HSVColorProfile, rng: random.Random | None = None) -> tuple[int, int] | None:
        regions = self.find_hsv(zone_name, profile)
        if not regions:
            return None
        zone = getattr(self.zones, zone_name)
        return zone.to_screen(regions[0].random_point(rng))
