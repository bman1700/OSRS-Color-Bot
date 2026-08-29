import random

import cv2
import numpy as np

from utilities.hsv_color import DetectionResult, HSVColorProfile, HSVProfileStore, find_regions, rgb_to_hsv


def test_rgb_profile_finds_region_and_random_point(tmp_path):
    image = np.zeros((20, 30, 3), dtype=np.uint8)
    image[5:10, 8:15] = (0, 255, 255)  # BGR cyan
    profile = HSVColorProfile.from_rgb("cyan", (255, 255, 0), tolerance=(2, 10, 10), min_area=5)
    regions = find_regions(image, profile)

    assert len(regions) == 1
    assert regions[0].area == 35
    point = regions[0].random_point(random.Random(1))
    assert 8 <= point[0] < 15 and 5 <= point[1] < 10


def test_profile_store_round_trip(tmp_path):
    path = tmp_path / "colors.json"
    profile = HSVColorProfile("ore", (20, 40, 50), (30, 255, 255), min_area=4)
    store = HSVProfileStore()
    store.save(path, [profile])

    assert store.load(path) == [profile]


def test_rgb_to_hsv_uses_opencv_ranges():
    assert rgb_to_hsv((255, 0, 0)) == (0, 255, 255)


def test_red_profile_preserves_hue_wrap():
    profile = HSVColorProfile.from_rgb("red", (255, 0, 0), tolerance=(5, 10, 10))
    assert profile.lower[0] > profile.upper[0]


def test_detection_result_exposes_structured_and_legacy_fields():
    region = find_regions(np.full((4, 4, 3), (0, 0, 0), dtype=np.uint8), HSVColorProfile("none", (1, 1, 1), (1, 1, 1)))
    result = DetectionResult(None, "none")
    assert not result.found
    assert result.center is None
