import numpy as np

from utilities.hsv_color import HSVColorProfile
from utilities.zones import Zone
from vision import VisionService


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
