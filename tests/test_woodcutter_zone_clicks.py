import cv2
import numpy as np

from model.osrs.woodcutter import OSRSWoodcutter
from model.osrs.movement import OSRSMovement
from runtime import Tile


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


def test_player_tile_detection_accepts_perspective_skewed_cyan_tile():
    """The GE's low camera pitch makes a valid cyan tile less rectangular."""
    image = np.zeros((140, 180, 3), dtype=np.uint8)
    # This quadrilateral has the same 64%-filled bounding-box geometry as
    # the player tile in the reported RuneLite screenshot.
    cv2.fillConvexPoly(image, np.array(((62, 40), (60, 71), (107, 85), (105, 54))), (255, 255, 0))

    class GameView:
        left = 100
        top = 200

        @staticmethod
        def screenshot():
            return image

    point = OSRSWoodcutter._OSRSWoodcutter__find_player_tile(GameView())

    assert point == (184, 263)


def test_movement_diagnostic_requires_marker_clearance_approval(monkeypatch):
    bot = OSRSMovement()
    clicks = []

    monkeypatch.setattr(bot.runtime.actions, "click", lambda: clicks.append(True))
    monkeypatch.setattr(bot.mouse, "position", lambda: (1, 2))
    monkeypatch.setattr(bot, "wait", lambda _: None)
    monkeypatch.setattr(bot, "mouseover_text", lambda: "")

    assert bot._OSRSWoodcutter__click_walk_here() is False
    assert clicks == []

    bot._approved_walk_point = (1, 2)
    assert bot._OSRSWoodcutter__click_walk_here() is True
    assert clicks == [True]

    monkeypatch.setattr(bot, "mouseover_text", lambda: "Bank Banker")
    assert bot._OSRSWoodcutter__click_walk_here() is False
    assert clicks == [True]


def test_fluid_movement_projects_from_the_live_cursor_tile():
    project = OSRSMovement._OSRSMovement__project_cursor_target

    point = project(
        (100, 100),
        Tile(0, 0),
        Tile(2, 4),
        ((60, 0), (0, -90), (2, 0), (0, 4)),
        (0, 0, 200, 200),
    )

    assert point == (160, 10)


def test_fluid_movement_reports_unprojectable_direction_at_canvas_edge():
    project = OSRSMovement._OSRSMovement__project_cursor_target

    point = project(
        (100, 0),
        Tile(0, 0),
        Tile(0, 4),
        ((60, 0), (0, -90), (2, 0), (0, 4)),
        (0, 0, 200, 200),
    )

    assert point is None


def test_fluid_movement_requires_an_unclipped_projection_for_final_clicks():
    project = OSRSMovement._OSRSMovement__project_cursor_target

    point = project(
        (100, 100),
        Tile(0, 0),
        Tile(0, 20),
        ((60, 0), (0, -90), (2, 0), (0, 4)),
        (0, 0, 200, 200),
        allow_clip=False,
    )

    assert point is None


def test_fluid_movement_rejects_reversed_or_excessive_calibration_axes():
    accepts = OSRSMovement._OSRSMovement__is_fluid_calibration

    assert accepts(((60, 0), (0, -90), (2, 0), (0, 4)))
    assert accepts(((60, 0), (0, -90), (2, 2), (2, 4)))
    assert not accepts(((60, 0), (0, -60), (2, 0), (20, -2)))
    assert not accepts(((60, 0), (0, -90), (-2, 0), (0, 4)))


def test_fluid_movement_accepts_clear_left_and_down_calibration_probes():
    accepts = OSRSMovement._OSRSMovement__is_fluid_calibration

    assert accepts(((-60, 0), (0, 90), (-2, 0), (0, -4)))


def test_fluid_movement_limits_each_stride_without_changing_direction():
    limit = OSRSMovement._OSRSMovement__limited_stride_target

    assert limit(Tile(10, 10), Tile(30, 20), 8) == Tile(18, 14)
    assert limit(Tile(10, 10), Tile(12, 14), 8) == Tile(12, 14)


def test_fluid_calibration_fits_all_valid_probe_samples():
    fit = OSRSMovement._OSRSMovement__fit_probe_axis

    fitted = fit([((60, 0), (2, 0)), ((-60, 0), (-2, 0)), ((45, 0), (1, 0))], 0)

    assert 0.02 < fitted[0] < 0.04
    assert fitted[1] == 0


def test_fluid_movement_projects_with_world_units_per_pixel_calibration():
    project = OSRSMovement._OSRSMovement__project_cursor_target
    calibration = (
        (1.0, 0.0),
        (0.0, 1.0),
        (0.028, 0.0),
        (-0.0038461538461538464, -0.03461538461538462),
    )

    point = project((1068, 347), Tile(3164, 3510), Tile(3163, 3502), calibration, (677, 112, 1460, 583))

    assert point is not None


def test_movement_uses_immediate_north_up_projection():
    calibration = OSRSMovement._OSRSMovement__north_up_tile_map()
    project = OSRSMovement._OSRSMovement__project_cursor_target

    point = project((500, 500), Tile(1000, 1000), Tile(1002, 1004), calibration, (0, 0, 1000, 1000))

    assert point == (570, 380)


def test_movement_settings_parse_configurable_start_and_end_tiles():
    parse = OSRSMovement._OSRSMovement__parse_tile_option

    assert parse("3200, 3201, 1") == Tile(3200, 3201, 1)
    assert parse("3200, 3201") == Tile(3200, 3201, 0)


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
