from collections import namedtuple

import numpy as np

from utilities.zones import ZoneSet
from vision import VisionDebugTools, VisionService


Point = namedtuple("Point", "x y")


class Rectangle:
    left = 10
    top = 20
    width = 20
    height = 20

    def screenshot(self):
        image = np.zeros((self.height, self.width, 3), dtype=np.uint8)
        image[2:6, 3:8] = (0, 255, 255)
        return image


class Window:
    def __init__(self):
        self.game_view = self.control_panel = self.minimap = self.chat = self.mouseover = Rectangle()
        self.zones = ZoneSet(self)

    def rectangle(self):
        return Rectangle()


class Runtime:
    def __init__(self):
        self.client = type("Client", (), {"zones": Window().zones})()
        self.vision = VisionService(self.client.zones)


def test_vision_debug_tools_manage_profiles_detections_and_exclusions(tmp_path):
    tools = VisionDebugTools(Runtime(), tmp_path / "profiles.json")
    profile = tools.profile("cyan", "28,245,245", "32,255,255", "4")

    assert len(tools.detect("game_view", profile)) == 1
    assert tools.zone_info("game_view")["bounds"] == {"left": 10, "top": 20, "width": 20, "height": 20}
    assert tools.add_exclusion("game_view", 1, 1, 2, 2)["exclusion_count"] == 1
    assert tools.clear_exclusions("game_view")["exclusion_count"] == 0

    tools.save_profile(profile)
    assert tools.profile_path.is_file()
