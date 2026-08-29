"""Testable operations behind the OSRS Vision Debug UI."""

from __future__ import annotations

from pathlib import Path

from utilities.hsv_color import DetectionResult, HSVColorProfile, HSVProfileStore


class VisionDebugTools:
    def __init__(self, runtime, profile_path: str | Path) -> None:
        self.runtime = runtime
        self.profile_path = Path(profile_path)

    @staticmethod
    def profile(name: str, lower: str, upper: str, min_area: str | int) -> HSVColorProfile:
        parse = lambda value: tuple(int(component.strip()) for component in str(value).split(","))
        return HSVColorProfile(name=name.strip() or "debug", lower=parse(lower), upper=parse(upper), min_area=int(min_area))

    def detect(self, zone_name: str, profile: HSVColorProfile) -> list[DetectionResult]:
        return self.runtime.vision.detect_hsv(zone_name, profile)

    def zone_info(self, zone_name: str) -> dict:
        zone = getattr(self.runtime.client.zones, zone_name)
        return {"name": zone_name, "bounds": zone.screen_rectangle(), "exclusion_count": len(zone.exclusions)}

    def add_exclusion(self, zone_name: str, left: int, top: int, width: int, height: int) -> dict:
        zone = getattr(self.runtime.client.zones, zone_name)
        zone.add_exclusion(left, top, width, height)
        return self.zone_info(zone_name)

    def clear_exclusions(self, zone_name: str) -> dict:
        zone = getattr(self.runtime.client.zones, zone_name)
        zone.clear_exclusions()
        return self.zone_info(zone_name)

    def save_profile(self, profile: HSVColorProfile) -> None:
        store = HSVProfileStore()
        profiles = store.load(self.profile_path) if self.profile_path.is_file() else []
        store.save(self.profile_path, [item for item in profiles if item.name != profile.name] + [profile])
