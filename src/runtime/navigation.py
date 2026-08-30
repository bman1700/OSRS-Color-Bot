"""Generic, provider-agnostic minimap navigation primitives.

The navigator deliberately does not know how a client obtains paths or sends
input.  A DAX-backed provider, a locally computed provider, and test doubles
can all satisfy the small protocols below.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
import random
import time
from typing import Any, Callable, Protocol, Sequence


@dataclass(frozen=True, order=True)
class Tile:
    """A world tile; positive ``y`` is north and plane is the OSRS height level."""

    x: int
    y: int
    plane: int = 0

    def distance_to(self, other: "Tile") -> float:
        if self.plane != other.plane:
            return math.inf
        return math.hypot(self.x - other.x, self.y - other.y)


class PathProvider(Protocol):
    """Supplies a route inclusive of zero or more waypoints toward a goal."""

    def path(self, start: Tile, destination: Tile) -> Sequence[Tile]: ...


class MinimapProjector(Protocol):
    """Converts a world tile into a safe, screen-space minimap click point."""

    def project(self, current: Tile, target: Tile) -> tuple[int, int] | None: ...


@dataclass(frozen=True)
class CompassRotation:
    """Camera heading in clockwise degrees from north.

    ``rotate`` returns minimap-relative pixels: right is positive x and down
    is positive y.  It is intentionally separate from vision so a future
    compass reader only has to construct this value.
    """

    heading_degrees: float = 0.0

    def rotate(self, east_tiles: float, north_tiles: float) -> tuple[float, float]:
        radians = math.radians(self.heading_degrees)
        return (
            east_tiles * math.cos(radians) + north_tiles * math.sin(radians),
            east_tiles * math.sin(radians) - north_tiles * math.cos(radians),
        )


class SensorCompass:
    """Read a compass heading from the optional status-socket snapshot.

    Status payloads have used several names over time.  Missing or malformed
    values intentionally fall back to north-up, preserving deterministic and
    fail-closed behaviour when no socket is configured.
    """

    def __init__(self, snapshot: Callable[[], Any] | None = None) -> None:
        self.snapshot = snapshot
        self._heading = 0.0

    def __call__(self) -> CompassRotation:
        if self.snapshot is not None:
            try:
                payload = self.snapshot()
                if isinstance(payload, dict):
                    payload = payload.get("minimap") or payload
                else:
                    payload = getattr(payload, "minimap", None) or payload
                if isinstance(payload, dict):
                    value = next((payload[key] for key in ("heading", "headingDegrees", "compassHeading", "yaw") if key in payload), None)
                    if value is not None:
                        value = float(value)
                        if math.isfinite(value):
                            self._heading = value % 360.0
            except (AttributeError, TypeError, ValueError, OSError):
                pass
        return CompassRotation(self._heading)


class WindowMinimapProjector:
    """Projector which follows the current RuneLite minimap rectangle."""

    def __init__(self, window: Any, compass: Callable[[], CompassRotation] | None = None,
                 pixels_per_tile: float = 4.0, edge_padding_pixels: float = 4.0) -> None:
        if pixels_per_tile <= 0:
            raise ValueError("pixels_per_tile must be positive")
        self.window = window
        self.compass = compass or CompassRotation
        self.pixels_per_tile = pixels_per_tile
        self.edge_padding_pixels = edge_padding_pixels

    def project(self, current: Tile, target: Tile) -> tuple[int, int] | None:
        rectangle = getattr(self.window, "minimap", None)
        if rectangle is None:
            return None
        width, height = float(getattr(rectangle, "width", 0)), float(getattr(rectangle, "height", 0))
        if width <= 0 or height <= 0:
            return None
        center = (round(float(rectangle.left) + width / 2), round(float(rectangle.top) + height / 2))
        return CircularMinimapProjector(center, min(width, height) / 2, self.pixels_per_tile,
                                        compass=self.compass, edge_padding_pixels=self.edge_padding_pixels).project(current, target)


class SnapshotTilePosition:
    """Extract the player's world tile from a status snapshot when present."""

    def __init__(self, snapshot: Callable[[], Any]) -> None:
        self.snapshot = snapshot

    def __call__(self) -> Tile | None:
        try:
            value = self.snapshot()
            value = getattr(value, "raw", value)
            if not isinstance(value, dict):
                return None
            value = value.get("playerPosition", value.get("position"))
            if not isinstance(value, dict):
                return None
            x, y = value.get("x"), value.get("y")
            if x is None or y is None:
                return None
            return Tile(int(x), int(y), int(value.get("plane", value.get("z", 0))))
        except (AttributeError, TypeError, ValueError, OSError):
            return None


class NullPathProvider:
    """Explicit no-route provider used until a local/provider route is injected."""

    def path(self, start: Tile, destination: Tile) -> Sequence[Tile]:
        return ()


@dataclass(frozen=True)
class CircularMinimapProjector:
    """Project tiles into a circular minimap with an injectable compass source."""

    center: tuple[int, int]
    radius_pixels: float
    pixels_per_tile: float
    compass: Callable[[], CompassRotation] = CompassRotation
    edge_padding_pixels: float = 4.0

    def __post_init__(self) -> None:
        if self.radius_pixels <= 0 or self.pixels_per_tile <= 0:
            raise ValueError("minimap radius and pixels_per_tile must be positive")
        if self.edge_padding_pixels < 0:
            raise ValueError("edge_padding_pixels cannot be negative")

    def project(self, current: Tile, target: Tile) -> tuple[int, int] | None:
        if current.plane != target.plane:
            return None
        relative_x, relative_y = self.compass().rotate(target.x - current.x, target.y - current.y)
        relative_x *= self.pixels_per_tile
        relative_y *= self.pixels_per_tile
        if math.hypot(relative_x, relative_y) > self.radius_pixels - self.edge_padding_pixels:
            return None
        return (round(self.center[0] + relative_x), round(self.center[1] + relative_y))


class NavigationStatus(str, Enum):
    ARRIVED = "arrived"
    NO_PATH = "no_path"
    TARGET_NOT_ON_MINIMAP = "target_not_on_minimap"
    MOVEMENT_NOT_CONFIRMED = "movement_not_confirmed"
    REPLAN_LIMIT_REACHED = "replan_limit_reached"
    POSITION_UNAVAILABLE = "position_unavailable"


@dataclass(frozen=True)
class NavigationPolicy:
    """Bounds navigation recovery and controls non-deterministic route horizons."""

    horizon_min: int = 4
    horizon_max: int = 9
    max_replans: int = 3
    arrival_distance: float = 0.0
    movement_timeout_seconds: float = 1.5
    arrival_timeout_seconds: float = 10.0
    poll_interval_seconds: float = 0.2

    def __post_init__(self) -> None:
        if self.horizon_min < 1 or self.horizon_max < self.horizon_min:
            raise ValueError("horizon bounds must be positive and ordered")
        if self.max_replans < 0 or self.arrival_distance < 0:
            raise ValueError("max_replans and arrival_distance cannot be negative")
        if min(self.movement_timeout_seconds, self.arrival_timeout_seconds, self.poll_interval_seconds) <= 0:
            raise ValueError("navigation timeouts and poll interval must be positive")


@dataclass(frozen=True)
class NavigationResult:
    status: NavigationStatus
    replans: int
    clicks: int
    last_position: Tile | None

    @property
    def arrived(self) -> bool:
        return self.status is NavigationStatus.ARRIVED


class MinimapNavigator:
    """Click bounded route horizons and verify observed world-tile progress."""

    def __init__(
        self,
        position: Callable[[], Tile | None],
        path_provider: PathProvider,
        projector: MinimapProjector,
        click: Callable[[tuple[int, int]], None],
        *,
        policy: NavigationPolicy | None = None,
        rng: random.Random | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.position = position
        self.path_provider = path_provider
        self.projector = projector
        self.click = click
        self.policy = policy or NavigationPolicy()
        self.rng = rng or random.Random()
        self.clock = clock
        self.sleep = sleep

    def walk_to(self, destination: Tile) -> NavigationResult:
        clicks = 0
        for replans in range(self.policy.max_replans + 1):
            start = self.position()
            if start is None:
                return NavigationResult(NavigationStatus.POSITION_UNAVAILABLE, replans, clicks, None)
            if self._arrived(start, destination):
                return NavigationResult(NavigationStatus.ARRIVED, replans, clicks, start)

            route = tuple(self.path_provider.path(start, destination))
            waypoint = self._select_horizon(route, start)
            if waypoint is None:
                return NavigationResult(NavigationStatus.NO_PATH, replans, clicks, start)
            point = self.projector.project(start, waypoint)
            if point is None:
                return NavigationResult(NavigationStatus.TARGET_NOT_ON_MINIMAP, replans, clicks, start)

            self.click(point)
            clicks += 1
            movement = self._wait_for(lambda tile: tile.distance_to(start) > 0, self.policy.movement_timeout_seconds)
            if movement is None:
                return NavigationResult(NavigationStatus.MOVEMENT_NOT_CONFIRMED, replans, clicks, self.position())
            arrival = self._wait_for(lambda tile: self._arrived(tile, waypoint), self.policy.arrival_timeout_seconds)
            if arrival is not None:
                if self._arrived(arrival, destination):
                    return NavigationResult(NavigationStatus.ARRIVED, replans, clicks, arrival)
                continue
        return NavigationResult(NavigationStatus.REPLAN_LIMIT_REACHED, self.policy.max_replans, clicks, self.position())

    def _select_horizon(self, route: Sequence[Tile], start: Tile) -> Tile | None:
        candidates = [tile for tile in route if tile != start]
        if not candidates:
            return None
        index = min(self.rng.randint(self.policy.horizon_min, self.policy.horizon_max), len(candidates)) - 1
        return candidates[index]

    def _wait_for(self, predicate: Callable[[Tile], bool], timeout: float) -> Tile | None:
        deadline = self.clock() + timeout
        while self.clock() <= deadline:
            tile = self.position()
            if tile is None:
                return None
            if predicate(tile):
                return tile
            self.sleep(self.policy.poll_interval_seconds)
        return None

    def _arrived(self, current: Tile, destination: Tile) -> bool:
        return current.distance_to(destination) <= self.policy.arrival_distance
