from utilities.zones import Zone, ZoneSet


class FakeRectangle:
    def __init__(self, left, top):
        self.left = left
        self.top = top
        self.width = 10
        self.height = 10

    def screenshot(self):
        return "capture"


class FakeWindow:
    def __init__(self):
        self.game_view = FakeRectangle(100, 200)
        self.control_panel = FakeRectangle(600, 200)
        self.minimap = FakeRectangle(700, 50)
        self.chat = FakeRectangle(100, 550)
        self.mouseover = FakeRectangle(100, 200)

    def rectangle(self):
        return FakeRectangle(90, 170)


def test_zone_transforms_and_capture():
    zone = Zone("test", lambda: FakeRectangle(100, 200))

    assert zone.to_screen((3, 5)) == (103, 205)
    assert zone.to_relative((103, 205)) == (3, 5)
    assert zone.contains_screen((100, 200))
    assert zone.contains_relative((4, 3))
    assert zone.screen_rectangle() == {"left": 100, "top": 200, "width": 10, "height": 10}
    assert zone.screenshot() == "capture"


def test_zone_set_resolves_window_regions_live():
    window = FakeWindow()
    zones = ZoneSet(window)

    assert zones.game_view.to_screen((0, 0)) == (100, 200)
    window.game_view = FakeRectangle(120, 220)
    assert zones.game_view.to_screen((0, 0)) == (120, 220)


def test_zone_exclusion_masks_relative_area():
    class ImageRectangle(FakeRectangle):
        def screenshot(self):
            import numpy as np
            return np.ones((4, 5, 3), dtype=np.uint8)

    zone = Zone("test", lambda: ImageRectangle(0, 0))
    zone.add_exclusion(1, 1, 2, 2)
    image = zone.screenshot()
    assert image[1, 1].tolist() == [0, 0, 0]
    assert image[0, 0].tolist() == [1, 1, 1]
