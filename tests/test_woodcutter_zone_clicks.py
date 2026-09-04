import cv2
import numpy as np

import model.osrs.woodcutter as woodcutter_module
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

    monkeypatch.setattr(
        bot.runtime.actions,
        "click",
        lambda *args, **kwargs: clicks.append(kwargs.get("button", "left")),
    )
    monkeypatch.setattr(woodcutter_module.ocr, "find_text", lambda *args, **kwargs: [])
    monkeypatch.setattr(bot.mouse, "position", lambda: (1, 2))
    monkeypatch.setattr(bot, "wait", lambda _: None)
    monkeypatch.setattr(bot, "mouseover_text", lambda: "Walk here")

    assert bot._OSRSWoodcutter__click_walk_here() is False
    assert clicks == []

    bot._approved_walk_point = (1, 2)
    assert bot._OSRSWoodcutter__click_walk_here() is True
    assert clicks == ["left"]

    monkeypatch.setattr(bot, "mouseover_text", lambda: "Bank Banker")
    assert bot._OSRSWoodcutter__click_walk_here() is False
    assert clicks == ["left", "right"]


def test_movement_uses_verified_context_walk_when_hover_ocr_is_blank(monkeypatch):
    bot = OSRSMovement()
    clicks = []
    menu_entry = object()

    bot._approved_walk_point = (1, 2)
    monkeypatch.setattr(bot.mouse, "position", lambda: (1, 2))
    monkeypatch.setattr(bot, "wait", lambda _: None)
    monkeypatch.setattr(bot, "mouseover_text", lambda: "")
    monkeypatch.setattr(bot.runtime.actions, "click", lambda *args, **kwargs: clicks.append(kwargs.get("button")))
    monkeypatch.setattr(bot.runtime.actions, "click_within", lambda entry: clicks.append(entry))
    monkeypatch.setattr(woodcutter_module.ocr, "find_text", lambda *args, **kwargs: [menu_entry])

    assert bot._OSRSWoodcutter__click_walk_here() is True
    assert clicks == ["right", menu_entry]


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


def test_exact_finish_does_not_reanchor_from_implausible_cursor_ocr(monkeypatch):
    bot = OSRSMovement()
    destination = Tile(3162, 3488, 0)
    projected_from = []
    readings = iter((Tile(3162, 3487, 0), Tile(3162, 3468, 0), destination))

    def project(anchor_point, anchor_tile, *_args, **_kwargs):
        projected_from.append((anchor_point, anchor_tile))
        return (anchor_point[0], anchor_point[1] - 30)

    monkeypatch.setattr(bot, "_OSRSMovement__project_cursor_target", project)
    monkeypatch.setattr(bot.runtime.actions, "move_to", lambda _point: None)
    monkeypatch.setattr(bot, "wait", lambda _seconds: None)
    monkeypatch.setattr(bot, "_OSRSWoodcutter__read_cursor_tile", lambda _point: next(readings))
    monkeypatch.setattr(bot, "_OSRSMovement__has_marker_clearance", lambda _point: True)
    monkeypatch.setattr(bot, "_OSRSWoodcutter__click_walk_here", lambda: True)
    monkeypatch.setattr(bot, "_OSRSMovement__wait_for_player_stop", lambda: ((100, 100), destination))

    finish = bot._OSRSMovement__finish_at_exact_tile
    assert finish(((100, 100), Tile(3162, 3486, 0)), destination, "start point", None, (0, 0, 500, 500), 0)
    assert projected_from[1] == projected_from[2]


def test_movement_settings_parse_configurable_start_and_end_tiles():
    bot = OSRSMovement()
    parse = OSRSMovement._OSRSMovement__parse_tile_option

    assert bot.start_point == Tile(3162, 3486, 0)
    assert parse("3200, 3201, 1") == Tile(3200, 3201, 1)
    assert parse("3200, 3201") == Tile(3200, 3201, 0)


def test_player_tile_detection_recovers_tooltip_occluded_cyan_outline_from_prior_point():
    image = np.zeros((140, 180, 3), dtype=np.uint8)
    # Coordinate tooltip coverage can leave only the lower U of the outline.
    cv2.line(image, (60, 75), (60, 88), (255, 255, 0), 3)
    cv2.line(image, (60, 88), (109, 88), (255, 255, 0), 3)
    cv2.line(image, (109, 88), (109, 75), (255, 255, 0), 3)

    class GameView:
        left = 100
        top = 200

        @staticmethod
        def screenshot():
            return image

    find = OSRSWoodcutter._OSRSWoodcutter__find_player_tile

    assert find(GameView(), preferred_point=(185, 280)) == (185, 282)
    assert find(GameView()) is None


def test_coordinate_tooltip_ocr_tries_tight_below_cursor_crop_first(monkeypatch):
    bot = OSRSWoodcutter()
    client = type("Client", (), {"left": 100, "top": 200, "width": 1000, "height": 700})()
    monkeypatch.setattr(bot.win, "rectangle", lambda: client)
    captures = []

    class CaptureRectangle:
        def __init__(self, left, top, width, height):
            self.bounds = (left, top, width, height)

        def screenshot(self):
            captures.append(self.bounds)
            return self.bounds

    monkeypatch.setattr(woodcutter_module, "Rectangle", CaptureRectangle)
    monkeypatch.setattr(woodcutter_module, "coordinate_ocr_available", lambda: True)
    monkeypatch.setattr(woodcutter_module, "read_tile_coordinates", lambda _: (3161, 3481, 0))

    tile = bot._OSRSWoodcutter__read_coordinate_tooltip((525, 516))

    assert tile == Tile(3161, 3481, 0)
    assert captures == [(500, 531, 190, 70)]


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
