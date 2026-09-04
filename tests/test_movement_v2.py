import numpy as np

from model import OSRSMovementV2
from runtime import Tile


def test_movement_v2_exposes_route_options():
    bot = OSRSMovementV2()

    assert bot.bot_title == "Movement V2"
    assert bot.options_set is True
    assert bot.ARRIVAL_DISTANCE_TILES == 0
    assert bot.tile_points == [Tile(3162, 3486, 0), Tile(3157, 3459, 0)]

    bot.create_options()

    assert set(bot.options_builder.options) == {"round_trips", "tile_points"}


def test_movement_v2_parses_multiple_route_points():
    points = OSRSMovementV2._parse_tile_points("3200, 3201; 3202,3203,0\n3204, 3205")

    assert points == [Tile(3200, 3201), Tile(3202, 3203), Tile(3204, 3205)]


def test_movement_v2_rejects_invalid_routes():
    bot = OSRSMovementV2()

    bot.save_options({"round_trips": 1, "tile_points": "3200,3200"})

    assert bot.options_set is False


def test_movement_v2_bounds_long_corridor_targets():
    target = OSRSMovementV2._bounded_corridor_target(Tile(1000, 1000), Tile(1030, 1040), 10)

    assert target == Tile(1006, 1008)
    assert Tile(1000, 1000).distance_to(target) <= 10.1


def test_movement_v2_projects_north_up_tiles_inside_safe_minimap():
    bot = OSRSMovementV2()
    bot.win.minimap = type("Minimap", (), {"left": 100, "top": 200, "width": 160, "height": 160})()

    assert bot._project_minimap_tile(Tile(3200, 3200), Tile(3205, 3204)) == (200, 264)
    assert bot._project_minimap_tile(Tile(3200, 3200), Tile(3240, 3200)) is None


def test_movement_v2_motion_score_distinguishes_static_and_changed_frames():
    first = np.zeros((20, 20), dtype=np.uint8)
    changed = first.copy()
    changed[:, :10] = 255

    assert OSRSMovementV2._motion_score(first, first) == 0
    assert OSRSMovementV2._motion_score(first, changed) == 0.5


def test_movement_v2_consensus_rejects_single_ocr_outlier():
    readings = [
        ((1, 1), Tile(3153, 3459)),
        ((2, 2), Tile(3156, 3459)),
        ((3, 3), Tile(3156, 3459)),
    ]

    assert OSRSMovementV2._select_consensus_reading(readings)[1] == Tile(3156, 3459)


def test_movement_v2_iteratively_corrects_game_view_projection(monkeypatch):
    bot = OSRSMovementV2()
    bot.win.game_view = type(
        "GameView", (), {"left": 0, "top": 0, "width": 1000, "height": 800}
    )()
    bot.win.minimap_area = None
    bot.win.chat = None
    bot._last_player_point = (500, 500)
    moves = []
    readings = iter((Tile(1000, 1000), Tile(1001, 1000)))
    monkeypatch.setattr(bot.runtime.actions, "move_to", moves.append)
    monkeypatch.setattr(bot.mouse, "position", lambda: moves[-1])
    monkeypatch.setattr(bot, "wait", lambda _seconds: None)
    monkeypatch.setattr(bot, "_marker_avoidance_areas", lambda **_kwargs: [])
    monkeypatch.setattr(bot, "_capture_motion_frame", lambda: None)
    monkeypatch.setattr(bot, "_click_verified_walk_here", lambda **_kwargs: True)
    monkeypatch.setattr(bot, "_OSRSWoodcutter__read_cursor_tile", lambda _point: next(readings))

    clicked, _ = bot._click_game_view_tile(Tile(1000, 1000), Tile(1001, 1000))

    assert clicked is True
    assert moves == [(535, 500), (570, 500)]


def test_movement_v2_uses_short_exact_step_when_destination_is_partly_offscreen():
    bot = OSRSMovementV2()
    bot.win.game_view = type(
        "GameView", (), {"left": 0, "top": 0, "width": 1000, "height": 570}
    )()
    bot.win.minimap_area = None
    bot.win.chat = None
    bot._last_player_point = (500, 520)

    target = bot._farthest_visible_game_view_tile(Tile(1000, 1010), Tile(1000, 1004))

    assert target == Tile(1000, 1009)


def test_movement_v2_finds_clear_pixel_on_same_exact_tile(monkeypatch):
    bot = OSRSMovementV2()
    bot.win.game_view = type(
        "GameView", (), {"left": 0, "top": 0, "width": 1000, "height": 800}
    )()
    bot.win.minimap_area = None
    bot.win.chat = None
    bot._last_player_point = (500, 500)
    moves = []
    force_context = []
    monkeypatch.setattr(bot.runtime.actions, "move_to", moves.append)
    monkeypatch.setattr(bot.mouse, "position", lambda: moves[-1])
    monkeypatch.setattr(bot, "wait", lambda _seconds: None)
    monkeypatch.setattr(
        bot,
        "_marker_avoidance_areas",
        lambda **_kwargs: [(530, 495, 540, 505)],
    )
    monkeypatch.setattr(bot, "_capture_motion_frame", lambda: None)
    monkeypatch.setattr(
        bot,
        "_click_verified_walk_here",
        lambda **kwargs: force_context.append(kwargs["force_context"]) or True,
    )
    monkeypatch.setattr(
        bot,
        "_OSRSWoodcutter__read_cursor_tile",
        lambda _point: Tile(1001, 1000),
    )

    clicked, _ = bot._click_game_view_tile(Tile(1000, 1000), Tile(1001, 1000))

    assert clicked is True
    assert force_context == [False]
    assert moves[-1] == (528, 500)


def test_movement_v2_context_walk_selects_visible_menu_entry(monkeypatch):
    bot = OSRSMovementV2()
    entry = object()
    clicks = []
    monkeypatch.setattr(bot, "wait", lambda _seconds: None)
    monkeypatch.setattr(
        bot.runtime.actions,
        "click",
        lambda *args, **kwargs: clicks.append(kwargs.get("button", "left")),
    )
    monkeypatch.setattr(bot.runtime.actions, "click_within", clicks.append)
    monkeypatch.setattr("model.osrs.movement_v2.ocr.find_text", lambda *_args, **_kwargs: [entry])

    assert bot._click_verified_walk_here(force_context=True) is True
    assert clicks == ["right", entry]


def test_movement_v2_accepts_blank_hover_only_after_exact_coordinate_approval(monkeypatch):
    bot = OSRSMovementV2()
    clicks = []
    monkeypatch.setattr(bot, "mouseover_text", lambda: "")
    monkeypatch.setattr(bot.runtime.actions, "click", lambda **kwargs: clicks.append(kwargs))

    assert bot._click_verified_walk_here(coordinate_verified=True) is True
    assert clicks == [{}]


def test_movement_v2_never_falls_back_to_minimap_inside_precision_zone(monkeypatch):
    bot = OSRSMovementV2()
    minimap_calls = []
    monkeypatch.setattr(bot, "_maximum_minimap_tiles", lambda: 15)
    monkeypatch.setattr(bot, "_click_game_view_tile", lambda *_args: (False, None))
    monkeypatch.setattr(
        bot,
        "_click_minimap_tile",
        lambda *_args: minimap_calls.append(True) or (True, None),
    )

    assert bot._walk_corridor(Tile(1000, 1000), Tile(1002, 1000)) is False
    assert minimap_calls == []
