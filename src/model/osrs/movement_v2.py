"""Client-visual test bed for the second version of OSRS movement.

Movement V2 deliberately uses no game-state API. Player position, movement,
layout, and click safety are inferred from the visible RuneLite client.
"""

from __future__ import annotations

import math
import re
import time

import cv2
import numpy as np

from model.osrs.woodcutter import OSRSWoodcutter
from runtime import Tile
import utilities.color as clr
import utilities.ocr as ocr


class OSRSMovementV2(OSRSWoodcutter):
    """Walk a configured visual route with sparse, verified clicks."""

    DEFAULT_ROUTE = "3162,3486,0; 3157,3459,0"
    MINIMAP_PIXELS_PER_TILE = 4.0
    MINIMAP_SAFE_RADIUS_FRACTION = 0.72
    FINAL_GAME_VIEW_TILES = 8.0
    ARRIVAL_DISTANCE_TILES = 0.0
    MAX_STALLS_PER_WAYPOINT = 3
    MOTION_POLL_SECONDS = 0.18
    MOTION_STABLE_FRAMES = 3

    def __init__(self):
        super().__init__()
        self.bot_title = "Movement V2"
        self.description = (
            "Client-visual movement test bed. Configure semicolon-separated route tiles; "
            "V2 uses sparse minimap clicks, visual stop detection, and a validated "
            "game-view final approach. Consecutive points must describe clear walkable corridors."
        )
        self.round_trips = 5
        self.tile_points = self._parse_tile_points(self.DEFAULT_ROUTE)
        self._v2_last_confirmed_tile: Tile | None = None
        self.options_set = True

    def create_options(self):
        self.options_builder.add_slider_option("round_trips", "How many round trips?", 1, 100)
        self.options_builder.add_text_edit_option(
            "tile_points",
            "Route tiles (x,y,plane; x,y,plane; ...)",
            self.DEFAULT_ROUTE,
        )

    def save_options(self, options: dict):
        unknown = set(options) - {"round_trips", "tile_points"}
        if unknown:
            self.log_msg(f"Movement V2 received unknown options: {', '.join(sorted(unknown))}")
            self.options_set = False
            return
        try:
            round_trips = int(options.get("round_trips", self.round_trips))
            raw_points = str(options.get("tile_points", "")).strip()
            tile_points = self._parse_tile_points(raw_points) if raw_points else self.tile_points
            if round_trips < 1:
                raise ValueError("round trips must be at least one")
        except (TypeError, ValueError) as error:
            self.log_msg(f"Movement V2 options invalid: {error}")
            self.options_set = False
            return

        self.round_trips = round_trips
        self.tile_points = tile_points
        self.options_set = True
        route = " -> ".join(f"({tile.x},{tile.y},{tile.plane})" for tile in tile_points)
        self.log_msg(f"Movement V2 will run {round_trips} round trip(s): {route}.")

    @staticmethod
    def _parse_tile_points(value: str) -> list[Tile]:
        """Parse two or more route points separated by semicolons or newlines."""
        chunks = [chunk.strip() for chunk in re.split(r"[;\n]+", value) if chunk.strip()]
        points = []
        for chunk in chunks:
            values = [int(part) for part in re.findall(r"-?\d+", chunk)]
            if len(values) not in (2, 3):
                raise ValueError(f"route point {chunk!r} must be x,y or x,y,plane")
            x, y = values[:2]
            plane = values[2] if len(values) == 3 else 0
            if not 1000 <= x <= 5000 or not 1000 <= y <= 5000 or not 0 <= plane <= 3:
                raise ValueError(f"route point {chunk!r} is outside valid world-coordinate bounds")
            tile = Tile(x, y, plane)
            if not points or tile != points[-1]:
                points.append(tile)
        if len(points) < 2:
            raise ValueError("enter at least two different route points")
        if len({point.plane for point in points}) != 1:
            raise ValueError("all route points must be on the same plane")
        return points

    def main_loop(self):
        """Traverse the configured route forward and backward."""
        self._OSRSWoodcutter__refresh_window_layout("Movement V2 startup")
        if len(self.tile_points) < 2:
            self.log_msg("Movement V2 requires at least two configured route points.")
            return

        self._OSRSWoodcutter__reset_compass_to_north()
        current = self._read_player_tile()
        if current is None:
            self.log_msg("Movement V2 stopped: the highlighted player tile coordinate was unavailable.")
            return
        if current.plane != self.tile_points[0].plane:
            self.log_msg("Movement V2 stopped: the player and configured route are on different planes.")
            return

        targets = self._route_targets(current)
        total_targets = len(targets) * self.round_trips
        completed = 0
        for trip in range(1, self.round_trips + 1):
            self.log_msg(f"Movement V2 round trip {trip}/{self.round_trips} started.")
            for destination in targets:
                self.cancellation.raise_if_cancelled()
                current = self._read_player_tile(expected=current)
                if current is None or not self._walk_corridor(current, destination):
                    self.log_msg(
                        f"Movement V2 stopped before route tile "
                        f"({destination.x},{destination.y},{destination.plane})."
                    )
                    return
                completed += 1
                self.update_progress(completed / total_targets)

        self.update_progress(1)
        self.log_msg("Movement V2 completed all configured round trips.")

    def _route_targets(self, current: Tile) -> list[Tile]:
        """Approach the nearest route end, then make one complete return trip."""
        points = self.tile_points
        nearest_index = min(range(len(points)), key=lambda index: current.distance_to(points[index]))
        first_is_nearer = current.distance_to(points[0]) <= current.distance_to(points[-1])
        if first_is_nearer:
            alignment = list(reversed(points[: nearest_index + 1]))
            round_trip = points[1:] + list(reversed(points[:-1]))
        else:
            alignment = points[nearest_index:]
            round_trip = list(reversed(points[:-1])) + points[1:]
        return self._without_consecutive_duplicates(alignment + round_trip)

    @staticmethod
    def _without_consecutive_duplicates(points: list[Tile]) -> list[Tile]:
        result = []
        for point in points:
            if not result or point != result[-1]:
                result.append(point)
        return result

    def _walk_corridor(self, current: Tile, destination: Tile) -> bool:
        """Walk one user-declared clear corridor with bounded visual recovery."""
        stalls = 0
        distance = current.distance_to(destination)
        coarse_budget = math.ceil(distance / self._maximum_minimap_tiles())
        precision_budget = math.ceil(min(distance, self.FINAL_GAME_VIEW_TILES))
        max_actions = max(6, coarse_budget + precision_budget + 4)
        for action_number in range(1, max_actions + 1):
            self.cancellation.raise_if_cancelled()
            if current.distance_to(destination) <= self.ARRIVAL_DISTANCE_TILES:
                self.log_msg(f"Movement V2 reached route tile ({destination.x},{destination.y}).")
                return True

            click_target = self._bounded_corridor_target(
                current, destination, self._maximum_minimap_tiles()
            )
            mode = "minimap"
            baseline = None
            clicked = False
            precise_approach = current.distance_to(destination) <= self.FINAL_GAME_VIEW_TILES
            if precise_approach:
                visible_target = self._farthest_visible_game_view_tile(current, destination)
                if visible_target is None:
                    self.log_msg("Movement V2 could not find a visible precise step toward the route tile.")
                    return False
                click_target = visible_target
                clicked, baseline = self._click_game_view_tile(current, click_target)
                mode = "game view"
            if not clicked and not precise_approach:
                clicked, baseline = self._click_minimap_tile(current, click_target)
                mode = "minimap"
            if not clicked:
                self.log_msg(
                    "Movement V2 could not authorize the exact game-view tile; "
                    "it will not substitute an imprecise minimap click."
                )
                return False

            self.log_msg(
                f"Movement V2 action {action_number}: {mode} click toward "
                f"({click_target.x},{click_target.y})."
            )
            saw_motion = self._wait_for_visual_stop(baseline, current.distance_to(click_target))
            observed = self._read_player_tile(expected=click_target)
            if observed is None:
                self.log_msg("Movement V2 could not reacquire the player after movement.")
                return False
            if observed.plane != destination.plane:
                self.log_msg("Movement V2 rejected an unexpected plane change.")
                return False

            progress = current.distance_to(destination) - observed.distance_to(destination)
            if progress > 0.5:
                current = observed
                stalls = 0
                continue

            stalls += 1
            motion_note = "visible motion was detected" if saw_motion else "no clear motion was detected"
            self.log_msg(
                f"Movement V2 made no verified forward progress ({motion_note}); "
                f"recovery {stalls}/{self.MAX_STALLS_PER_WAYPOINT}."
            )
            current = observed
            if stalls >= self.MAX_STALLS_PER_WAYPOINT:
                return False

        self.log_msg("Movement V2 exceeded its click budget for this route corridor.")
        return False

    def _read_player_tile(self, expected: Tile | None = None) -> Tile | None:
        """Read several visible tooltip samples and select their tightest consensus."""
        game_view = self.win.game_view
        if game_view is None:
            return None
        center = self._OSRSWoodcutter__find_player_tile(
            game_view, preferred_point=self._last_player_point
        )
        if center is None:
            self.log_msg("Movement V2 could not find the highlighted player tile.")
            return None

        readings: list[tuple[tuple[int, int], Tile]] = []
        offsets = ((0, 0), (-5, -3), (5, 3), (-4, 4), (4, -4))
        reference = self._v2_last_confirmed_tile
        for dx, dy in offsets:
            self.cancellation.raise_if_cancelled()
            point = (center[0] + dx, center[1] + dy)
            self.runtime.actions.move_to(point)
            self.wait(0.10)
            tile = self._OSRSWoodcutter__read_coordinate_tooltip(point)
            if tile is None:
                continue
            if reference is not None and (
                tile.plane != reference.plane or tile.distance_to(reference) > 30
            ):
                continue
            readings.append((point, tile))
            if len(readings) >= 3 and self._reading_has_consensus(readings):
                break

        selected = self._select_consensus_reading(readings, expected)
        if selected is None:
            self.log_msg("Movement V2 rejected inconsistent player-coordinate OCR samples.")
            return None
        point, tile = selected
        self._last_player_point = point
        self._last_player_tile = tile
        self._v2_last_confirmed_tile = tile
        self._OSRSWoodcutter__remember_confirmed_tile(tile)
        self.log_msg(
            f"Movement V2 confirmed player tile ({tile.x}, {tile.y}, {tile.plane}) "
            f"from {len(readings)} OCR samples."
        )
        return tile

    @staticmethod
    def _reading_has_consensus(readings: list[tuple[tuple[int, int], Tile]]) -> bool:
        for _, candidate in readings:
            if sum(tile.distance_to(candidate) <= 1.5 for _, tile in readings) >= 2:
                return True
        return False

    @staticmethod
    def _select_consensus_reading(
        readings: list[tuple[tuple[int, int], Tile]], expected: Tile | None = None
    ) -> tuple[tuple[int, int], Tile] | None:
        if not readings:
            return None
        ranked = sorted(
            readings,
            key=lambda reading: (
                sum(reading[1].distance_to(other) for _, other in readings),
                reading[1].distance_to(expected) if expected is not None else 0.0,
            ),
        )
        best = ranked[0]
        neighbors = sum(best[1].distance_to(tile) <= 2.0 for _, tile in readings)
        if len(readings) > 1 and neighbors < 2:
            return None
        return best

    def _maximum_minimap_tiles(self) -> float:
        geometry = self._minimap_geometry()
        if geometry is None:
            return 1.0
        _, safe_radius = geometry
        return max(1.0, safe_radius / self.MINIMAP_PIXELS_PER_TILE)

    def _minimap_geometry(self) -> tuple[tuple[int, int], float] | None:
        minimap = getattr(self.win, "minimap", None)
        if minimap is None or minimap.width <= 0 or minimap.height <= 0:
            return None
        center = (round(minimap.left + minimap.width / 2), round(minimap.top + minimap.height / 2))
        radius = min(minimap.width, minimap.height) / 2
        return center, radius * self.MINIMAP_SAFE_RADIUS_FRACTION

    @staticmethod
    def _bounded_corridor_target(current: Tile, destination: Tile, maximum_tiles: float) -> Tile:
        """Return the farthest in-corridor tile that fits in the safe minimap radius."""
        distance = current.distance_to(destination)
        if not math.isfinite(distance) or distance <= maximum_tiles:
            return destination
        scale = maximum_tiles / distance
        x = current.x + round((destination.x - current.x) * scale)
        y = current.y + round((destination.y - current.y) * scale)
        if (x, y) == (current.x, current.y):
            x += 1 if destination.x > current.x else -1 if destination.x < current.x else 0
            y += 1 if destination.y > current.y else -1 if destination.y < current.y else 0
        return Tile(x, y, current.plane)

    def _project_minimap_tile(self, current: Tile, target: Tile) -> tuple[int, int] | None:
        geometry = self._minimap_geometry()
        if geometry is None or current.plane != target.plane:
            return None
        center, safe_radius = geometry
        dx = (target.x - current.x) * self.MINIMAP_PIXELS_PER_TILE
        dy = -(target.y - current.y) * self.MINIMAP_PIXELS_PER_TILE
        if math.hypot(dx, dy) > safe_radius + 0.5:
            return None
        return round(center[0] + dx), round(center[1] + dy)

    def _click_minimap_tile(
        self, current: Tile, target: Tile
    ) -> tuple[bool, np.ndarray | None]:
        point = self._project_minimap_tile(current, target)
        if point is None:
            return False, None
        self.runtime.actions.move_to(point)
        if self._cursor_missed(point):
            self.log_msg("Movement V2 cancelled a minimap click because WindMouse missed its endpoint.")
            return False, None
        baseline = self._capture_motion_frame()
        self.runtime.actions.click()
        return True, baseline

    def _click_game_view_tile(
        self, current: Tile, target: Tile
    ) -> tuple[bool, np.ndarray | None]:
        """Iteratively correct the cursor until client OCR identifies the exact tile."""
        game_view = self.win.game_view
        player_point = self._last_player_point
        if game_view is None or player_point is None or current.plane != target.plane:
            return False, None
        anchor_point = player_point
        anchor_tile = current
        marker_areas = self._marker_avoidance_areas(precision=True)
        for attempt in range(1, 6):
            point = (
                round(anchor_point[0] + (target.x - anchor_tile.x) * 35.0),
                round(anchor_point[1] - (target.y - anchor_tile.y) * 30.0),
            )
            if not self._point_in_safe_game_view(point):
                self.log_msg("Movement V2 exact-tile projection left the safe game view.")
                return False, None

            self.runtime.actions.move_to(point)
            self.wait(0.12)
            actual_point = self.mouse.position()
            highlighted = self._OSRSWoodcutter__read_cursor_tile(actual_point)
            if highlighted is None or highlighted.plane != target.plane:
                self.log_msg(f"Movement V2 exact-tile OCR failed on correction {attempt}/5.")
                continue
            if highlighted.distance_to(target) > self.FINAL_GAME_VIEW_TILES + 2:
                self.log_msg(
                    f"Movement V2 rejected implausible exact-tile OCR "
                    f"({highlighted.x},{highlighted.y})."
                )
                continue
            if highlighted != target:
                self.log_msg(
                    f"Movement V2 exact correction {attempt}/5: cursor is on "
                    f"({highlighted.x},{highlighted.y}); adjusting to "
                    f"({target.x},{target.y})."
                )
                anchor_point, anchor_tile = actual_point, highlighted
                continue

            over_marker = not self._has_marker_clearance(actual_point, marker_areas)
            if over_marker:
                alternate = self._find_marker_clear_exact_point(target, actual_point, marker_areas)
                if alternate is not None:
                    actual_point = alternate
                    over_marker = False
                    self.log_msg(
                        "Movement V2 moved to a marker-clear pixel on the same exact world tile."
                    )
                else:
                    self.log_msg(
                        "Movement V2 exact tile is fully covered by a tagged screen marker; "
                        "selecting the explicit Walk here action."
                    )
            baseline = self._capture_motion_frame()
            if self._click_verified_walk_here(
                force_context=over_marker, coordinate_verified=True
            ):
                return True, baseline
            return False, None

        self.log_msg("Movement V2 could not place the cursor on the exact destination tile.")
        return False, None

    def _farthest_visible_game_view_tile(
        self, current: Tile, destination: Tile
    ) -> Tile | None:
        """Select the farthest exact in-corridor tile whose first projection is visible."""
        if self._last_player_point is None:
            return None
        maximum = max(1, math.ceil(current.distance_to(destination)))
        for tiles in range(maximum, 0, -1):
            candidate = self._bounded_corridor_target(current, destination, float(tiles))
            point = (
                round(self._last_player_point[0] + (candidate.x - current.x) * 35.0),
                round(self._last_player_point[1] - (candidate.y - current.y) * 30.0),
            )
            if candidate != current and self._point_in_safe_game_view(point):
                return candidate
        return None

    def _find_marker_clear_exact_point(
        self,
        target: Tile,
        seed: tuple[int, int],
        marker_areas: list[tuple[int, int, int, int]],
    ) -> tuple[int, int] | None:
        """Search the visible footprint of one OCR-confirmed tile for a clear pixel."""
        offsets = (
            (-7, 0),
            (7, 0),
            (0, -6),
            (0, 6),
            (-11, -5),
            (11, -5),
            (-11, 5),
            (11, 5),
            (-15, 0),
            (15, 0),
        )
        visited = {seed}
        for dx, dy in offsets:
            candidate = (seed[0] + dx, seed[1] + dy)
            if candidate in visited or not self._point_in_safe_game_view(candidate):
                continue
            self.runtime.actions.move_to(candidate)
            self.wait(0.08)
            actual = self.mouse.position()
            visited.add(actual)
            if not self._has_marker_clearance(actual, marker_areas):
                continue
            if self._OSRSWoodcutter__read_cursor_tile(actual) == target:
                return actual
        return None

    def _click_verified_walk_here(
        self,
        *,
        force_context: bool = False,
        coordinate_verified: bool = False,
    ) -> bool:
        """Authorize a ground click from visible action text or the visible context menu."""
        if not force_context:
            last_hover = ""
            for _ in range(2):
                last_hover = self.mouseover_text()
                if not last_hover or "walk here" not in last_hover.lower():
                    break
                self.wait(0.06)
            else:
                self.runtime.actions.click()
                return True
            if coordinate_verified and not last_hover:
                self.log_msg(
                    "Movement V2 is clicking a marker-clear, exact-coordinate tile "
                    "despite blank hover OCR."
                )
                self.runtime.actions.click()
                return True

        self.runtime.actions.click(button="right")
        self.wait(0.25)
        entries = ocr.find_text(
            "Walk here",
            self.win.game_view,
            ocr.BOLD_12,
            [clr.OFF_WHITE, clr.OFF_YELLOW, clr.OFF_ORANGE],
        )
        if not entries:
            self.log_msg("Movement V2 could not verify Walk here in the context menu.")
            return False
        self.runtime.actions.click_within(entries[0])
        return True

    def _point_in_safe_game_view(self, point: tuple[int, int]) -> bool:
        game_view = self.win.game_view
        if game_view is None:
            return False
        left, top = game_view.left + 20, game_view.top + 20
        right, bottom = game_view.left + game_view.width - 20, game_view.top + game_view.height - 12
        minimap_area = getattr(self.win, "minimap_area", None)
        chat = getattr(self.win, "chat", None)
        if minimap_area is not None:
            right = min(right, minimap_area.left - 20)
        if chat is not None:
            bottom = min(bottom, chat.top - 10)
        return left <= point[0] <= right and top <= point[1] <= bottom

    def _marker_avoidance_areas(
        self, *, precision: bool = False
    ) -> list[tuple[int, int, int, int]]:
        areas = []
        paddings = ((self.tree_profile, 3), (self.banker_profile, 5)) if precision else (
            (self.tree_profile, 22),
            (self.banker_profile, 32),
        )
        for profile, padding in paddings:
            for marker in self.runtime.vision.detect_hsv("game_view", profile):
                bounds = marker.metadata.get("screen_bounds", {})
                left = int(bounds.get("left", 0)) - padding
                top = int(bounds.get("top", 0)) - padding
                areas.append(
                    (
                        left,
                        top,
                        left + int(bounds.get("width", 0)) + padding * 2,
                        top + int(bounds.get("height", 0)) + padding * 2,
                    )
                )
        return areas

    def _has_marker_clearance(
        self,
        point: tuple[int, int],
        areas: list[tuple[int, int, int, int]] | None = None,
    ) -> bool:
        for left, top, right, bottom in areas if areas is not None else self._marker_avoidance_areas():
            if left <= point[0] <= right and top <= point[1] <= bottom:
                return False
        return True

    def _cursor_missed(self, point: tuple[int, int], tolerance: int = 4) -> bool:
        actual = self.mouse.position()
        return abs(actual[0] - point[0]) > tolerance or abs(actual[1] - point[1]) > tolerance

    def _capture_motion_frame(self) -> np.ndarray | None:
        game_view = self.win.game_view
        if game_view is None:
            return None
        try:
            image = game_view.screenshot()
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
            return cv2.resize(gray, (160, 100), interpolation=cv2.INTER_AREA)
        except (AttributeError, cv2.error, TypeError, ValueError):
            return None

    @staticmethod
    def _motion_score(previous: np.ndarray, current: np.ndarray) -> float:
        difference = cv2.absdiff(previous, current)
        return float(np.count_nonzero(difference > 18)) / difference.size

    def _wait_for_visual_stop(self, baseline: np.ndarray | None, distance: float) -> bool:
        """Observe client frames until movement has started and then visually settled."""
        if baseline is None:
            self.wait(min(10.0, max(2.0, distance * 0.55)))
            return False
        deadline = time.monotonic() + min(20.0, max(4.0, distance * 0.75 + 3.0))
        previous = baseline
        saw_motion = False
        stable_frames = 0
        while time.monotonic() < deadline:
            self.cancellation.raise_if_cancelled()
            self.wait(self.MOTION_POLL_SECONDS)
            current = self._capture_motion_frame()
            if current is None:
                continue
            score = self._motion_score(previous, current)
            previous = current
            if score >= 0.025:
                saw_motion = True
                stable_frames = 0
            elif saw_motion and score <= 0.012:
                stable_frames += 1
                if stable_frames >= self.MOTION_STABLE_FRAMES:
                    return True
            elif saw_motion:
                stable_frames = 0
        return saw_motion
