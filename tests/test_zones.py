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


def test_zone_exclusions_are_respected_by_containment_helpers():
    zone = Zone("test", lambda: FakeRectangle(0, 0))
    zone.add_exclusion(2, 2, 3, 3)

    assert zone.is_excluded((2, 2))
    assert not zone.contains_relative((2, 2))
    assert zone.contains_rectangle({"left": 0, "top": 0, "width": 2, "height": 2})
    assert not zone.contains_rectangle({"left": 1, "top": 1, "width": 3, "height": 3})
    assert not zone.contains_rectangle({"left": 0, "top": 0, "width": 10, "height": 10})
    assert zone.contains_rectangle({"left": 0, "top": 0, "width": 10, "height": 10}, allow_excluded=True)


def test_zone_scales_reference_layout_coordinates_and_screen_exclusions():
    rectangle = FakeRectangle(100, 200)
    rectangle.width = 20
    rectangle.height = 30
    zone = Zone("test", lambda: rectangle)
    zone.set_reference_size(10, 15)

    assert zone.scale_relative((5, 10)) == (10, 20)
    assert zone.unscale_relative((10, 20)) == (5, 10)
    assert zone.reference_to_screen((5, 10)) == (110, 220)
    zone.add_screen_exclusion(112, 222, 2, 2)
    assert zone.is_excluded((12, 22))
