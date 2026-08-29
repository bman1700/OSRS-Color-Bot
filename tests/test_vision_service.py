import numpy as np
import cv2
from pathlib import Path

from utilities.hsv_color import HSVColorProfile
from utilities.zones import Zone
from vision import VisionService
from utilities.hsv_color import find_regions


class ImageRectangle:
    left = 100
    top = 200
    width = 20
    height = 20

    def screenshot(self):
        image = np.zeros((20, 20, 3), dtype=np.uint8)
        image[3:7, 4:9] = (0, 255, 255)
        return image


class Zones:
    game_view = Zone("game_view", ImageRectangle)


def test_vision_service_returns_screen_relative_hsv_point():
    profile = HSVColorProfile.from_rgb("cyan", (255, 255, 0), tolerance=(2, 10, 10))
    point = VisionService(Zones()).random_hsv_point("game_view", profile)

    assert point is not None
    assert 104 <= point[0] < 109 and 203 <= point[1] < 207


def test_vision_service_returns_structured_detection_results():
    profile = HSVColorProfile.from_rgb("cyan", (255, 255, 0), tolerance=(2, 10, 10))
    results = VisionService(Zones()).detect_hsv("game_view", profile)

    assert len(results) == 1
    assert results[0].found
    assert results[0].source == "cyan"
    assert results[0].suggested_point == results[0].center
    assert results[0].metadata["zone"] == "game_view"
    assert results[0].metadata["screen_bounds"]["left"] == 104


def test_vision_service_adapts_image_search_to_structured_result():
    template = np.zeros((2, 2, 3), dtype=np.uint8)
    template[:] = (0, 255, 255)
    result = VisionService(Zones()).find_image("game_view", template)

    assert result.found
    assert result.source.startswith("image:")
    assert result.bounds.width == 2
    assert result.metadata["zone"] == "game_view"
    assert result.bounds.height == 2


def test_captured_runelite_fixture_contains_tagged_tree_regions():
    image = cv2.imread(str(Path(__file__).parent / "fixtures" / "runelite_client.png"))
    assert image is not None
    assert image.shape[:2] == (844, 1279)
    profile = HSVColorProfile.from_rgb("tagged_tree", (255, 0, 231), tolerance=(5, 50, 50), min_area=4)

    assert find_regions(image, profile)
