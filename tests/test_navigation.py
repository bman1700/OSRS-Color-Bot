from __future__ import annotations

import random

from runtime.navigation import (
    CircularMinimapProjector, CompassRotation, MinimapNavigator, NavigationPolicy,
    NavigationStatus, NullPathProvider, SensorCompass, SnapshotTilePosition,
    Tile, WindowMinimapProjector,
)


class Clock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value

    def sleep(self, seconds: float) -> None:
        self.value += seconds


class Route:
    def __init__(self, tiles: list[Tile]) -> None:
        self.tiles = tiles
        self.calls = 0

    def path(self, start: Tile, destination: Tile) -> list[Tile]:
        self.calls += 1
        return self.tiles


def policy(**changes) -> NavigationPolicy:
    return NavigationPolicy(horizon_min=1, horizon_max=1, movement_timeout_seconds=1, arrival_timeout_seconds=1, poll_interval_seconds=.1, **changes)


def test_compass_rotation_and_circular_projection() -> None:
    north_up = CircularMinimapProjector((100, 100), 50, 4, compass=lambda: CompassRotation(0))
    east_up = CircularMinimapProjector((100, 100), 50, 4, compass=lambda: CompassRotation(90))
    assert north_up.project(Tile(0, 0), Tile(2, 3)) == (108, 88)
    assert east_up.project(Tile(0, 0), Tile(2, 3)) == (112, 108)
    assert north_up.project(Tile(0, 0), Tile(20, 0)) is None


def test_walks_horizon_and_verifies_movement_and_arrival() -> None:
    positions = iter([Tile(0, 0), Tile(0, 0), Tile(1, 0), Tile(2, 0)])
    clicks: list[tuple[int, int]] = []
    clock = Clock()
    navigator = MinimapNavigator(
        lambda: next(positions), Route([Tile(0, 0), Tile(2, 0)]),
        CircularMinimapProjector((100, 100), 50, 4), clicks.append,
        policy=policy(), rng=random.Random(5), clock=clock, sleep=clock.sleep,
    )
    result = navigator.walk_to(Tile(2, 0))
    assert result.status is NavigationStatus.ARRIVED
    assert result.clicks == 1
    assert clicks == [(108, 100)]


def test_replans_after_waypoint_and_stops_at_bound() -> None:
    # Each click moves to a waypoint but cannot ultimately reach the destination.
    positions = iter([Tile(0, 0), Tile(1, 0), Tile(1, 0), Tile(1, 0), Tile(2, 0), Tile(2, 0), Tile(2, 0), Tile(3, 0), Tile(3, 0), Tile(3, 0)])
    clock = Clock()
    class AdvancingRoute(Route):
        def path(self, start: Tile, destination: Tile) -> list[Tile]:
            self.calls += 1
            return [start, Tile(start.x + 1, start.y, start.plane)]

    route = AdvancingRoute([])
    navigator = MinimapNavigator(
        lambda: next(positions), route, CircularMinimapProjector((100, 100), 50, 4), lambda _: None,
        policy=policy(max_replans=2), clock=clock, sleep=clock.sleep,
    )
    result = navigator.walk_to(Tile(99, 0))
    assert result.status is NavigationStatus.REPLAN_LIMIT_REACHED
    assert result.replans == 2 and result.clicks == 3 and route.calls == 3


def test_fails_closed_when_click_does_not_produce_movement() -> None:
    clock = Clock()
    navigator = MinimapNavigator(
        lambda: Tile(0, 0), Route([Tile(1, 0)]), CircularMinimapProjector((100, 100), 50, 4), lambda _: None,
        policy=policy(), clock=clock, sleep=clock.sleep,
    )
    assert navigator.walk_to(Tile(1, 0)).status is NavigationStatus.MOVEMENT_NOT_CONFIRMED


class Rect:
    left, top, width, height = 10, 20, 100, 80


def test_window_projector_tracks_minimap_and_missing_minimap_fails_closed() -> None:
    window = type("Window", (), {"minimap": Rect()})()
    projector = WindowMinimapProjector(window, pixels_per_tile=4)
    assert projector.project(Tile(0, 0), Tile(1, 0)) == (64, 60)
    window.minimap = None
    assert projector.project(Tile(0, 0), Tile(1, 0)) is None


def test_sensor_adapters_accept_payload_variants_and_fall_back_safely() -> None:
    payload = {"playerPosition": {"x": 3200, "y": 3201, "plane": 1}, "minimap": {"heading": 450}}
    compass = SensorCompass(lambda: payload)
    assert compass().heading_degrees == 90
    assert SnapshotTilePosition(lambda: payload)() == Tile(3200, 3201, 1)
    assert SnapshotTilePosition(lambda: {})() is None
    assert SensorCompass(lambda: {"minimap": {"heading": "bad"}})().heading_degrees == 0
    assert NullPathProvider().path(Tile(0, 0), Tile(1, 1)) == ()
