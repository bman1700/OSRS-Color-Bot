import cv2
import numpy as np

from model.osrs.woodcutter import OSRSWoodcutter


def test_woodcutter_defaults_to_live_mode_and_ge_bank():
    bot = OSRSWoodcutter()
    assert bot.running_time == 10
    assert bot.test_mode is False
    assert bot.start_tile.x == 3157
    assert bot.start_tile.y == 3459
    assert bot.bank_location_name == "GE West Side"


def test_player_tile_detection_accepts_green_tile():
    image = np.zeros((140, 180, 3), dtype=np.uint8)
    cv2.rectangle(image, (60, 40), (109, 89), (0, 255, 0), 3)

    class GameView:
        left = 100
        top = 200

        @staticmethod
        def screenshot():
            return image

    point = OSRSWoodcutter._OSRSWoodcutter__find_player_tile(GameView())

    assert point == (185, 265)


def test_banker_candidate_points_cover_distinct_interior_locations():
    points = OSRSWoodcutter._OSRSWoodcutter__banker_candidate_points(
        {"left": -900, "top": 300, "width": 80, "height": 100}
    )

    assert points[0] == (-860, 350)
    assert len(points) == 5
    assert all(-900 <= x < -820 and 300 <= y < 400 for x, y in points)


def test_recent_confirmed_tile_survives_independent_ocr_sampling_state():
    bot = OSRSWoodcutter()
    tile = bot.start_tile
    bot._OSRSWoodcutter__remember_confirmed_tile(tile)
    bot._last_player_tile = None

    assert bot._OSRSWoodcutter__recent_confirmed_tile() == tile


def test_bank_navigation_stops_before_the_crowded_destination_tile(monkeypatch):
    bot = OSRSWoodcutter()
    bank = type("Bank", (), {"name": "Test bank", "tile": bot.start_tile})()
    bot.runtime.bank_locations = type("Locations", (), {"find": lambda _, __: bank})()
    calls = []
    monkeypatch.setattr(bot, "_OSRSWoodcutter__navigate_to_tile", lambda *args, **kwargs: calls.append(kwargs) or True)
    monkeypatch.setattr(bot, "_OSRSWoodcutter__bank_interface_visible", lambda: True)
    monkeypatch.setattr(bot, "_OSRSWoodcutter__find_template_rect", lambda *args, **kwargs: None)

    assert bot._OSRSWoodcutter__bank_inventory() is False
    assert calls[0]["arrival_distance"] == 6.0


def test_calibration_allows_perspective_cross_axis_motion_but_rejects_outliers():
    accepts = OSRSWoodcutter._OSRSWoodcutter__is_calibration_delta

    assert accepts((60, 0), (2, -30))
    assert accepts((0, -90), (2, 4))
    assert accepts((0, -90), (0, -27))
    assert not accepts((60, 0), (2, -100))
