"""Dedicated GE-to-tree movement diagnostic.

This intentionally performs no banking, chopping, equipment, or inventory
actions.  Its log is therefore a focused record of coordinate reads,
calibration, clicks, and each route outcome.
"""

import random
import re
import time

from model.osrs.woodcutter import OSRSWoodcutter
from runtime import Tile


class OSRSMovement(OSRSWoodcutter):
    """Repeatedly walk only between the GE west bank and tree-area tiles."""

    BANK_NAME = "GE West Side"
    FLUID_CLICK_INTERVAL_SECONDS = 0.35
    FLUID_MAX_CLICKS_PER_LEG = 80
    FLUID_LOOKAHEAD_TILES = 8
    TERMINAL_CROSS_AXIS_TILES = 10
    NORTH_UP_X_PIXELS_PER_TILE = 35.0
    NORTH_UP_Y_PIXELS_PER_TILE = 30.0

    def __init__(self):
        super().__init__()
        self.bot_title = "Movement"
        self.description = (
            "Movement diagnostic: repeatedly walks between two configurable world tiles. "
            "It never banks, chops, or changes inventory/equipment."
        )
        self.round_trips = 5
        # 3162,3488 projects into the tagged west-bank booth.  Exact-finish
        # clicks deliberately reject tagged objects, so use the nearest
        # repeatedly observed clear standing tile instead.
        self.start_point = Tile(3162, 3486, 0)
        self.end_point = Tile(3157, 3459, 0)
        self._approved_walk_point: tuple[int, int] | None = None
        self.options_set = True

    def create_options(self):
        self.options_builder.add_slider_option("round_trips", "How many round trips?", 1, 100)
        self.options_builder.add_text_edit_option("start_point", "Start tile (x, y, plane)", "3162, 3486, 0")
        self.options_builder.add_text_edit_option("end_point", "End tile (x, y, plane)", "3157, 3459, 0")

    def save_options(self, options: dict):
        unknown_options = set(options) - {"round_trips", "start_point", "end_point"}
        if unknown_options:
            self.log_msg(f"Movement received unknown options: {', '.join(sorted(unknown_options))}")
            self.options_set = False
            return
        try:
            self.round_trips = int(options.get("round_trips", self.round_trips))
            for key in ("start_point", "end_point"):
                value = str(options.get(key, "")).strip()
                if value:
                    setattr(self, key, self.__parse_tile_option(value))
        except ValueError as error:
            self.log_msg(f"Movement options invalid: {error}")
            self.options_set = False
            return
        self.options_set = self.round_trips > 0 and self.start_point != self.end_point
        if self.options_set:
            self.log_msg(
                f"Movement will run {self.round_trips} round trip(s): "
                f"({self.start_point.x},{self.start_point.y},{self.start_point.plane}) <-> "
                f"({self.end_point.x},{self.end_point.y},{self.end_point.plane})."
            )
        else:
            self.log_msg("Movement start and end tiles must be different, with at least one round trip.")

    @staticmethod
    def __parse_tile_option(value: str) -> Tile:
        """Parse a settings tile written as ``x, y`` or ``x, y, plane``."""
        values = [int(part) for part in re.findall(r"-?\d+", value)]
        if len(values) not in (2, 3):
            raise ValueError(f"tile {value!r} must be x, y, plane (plane may be omitted)")
        x, y = values[:2]
        plane = values[2] if len(values) == 3 else 0
        if not 1000 <= x <= 5000 or not 1000 <= y <= 5000 or not 0 <= plane <= 3:
            raise ValueError(f"tile {value!r} is outside valid world-coordinate bounds")
        return Tile(x, y, plane)

    def _resolve_movement_click_point(
        self, point: tuple[int, int], bounds: tuple[int, int, int, int]
    ) -> tuple[int, int] | None:
        """Find a nearby point with conservative visual clearance from trees."""
        self._approved_walk_point = None
        left, top, right, bottom = bounds
        # Cursor-coordinate tooltips can cover the tagged outline at the
        # exact point that is about to be checked. Move to the most distant
        # safe canvas corner first, then take one unobscured marker snapshot
        # for every candidate in this resolution pass.
        parking_point = max(
            (
                (left + 10, top + 10),
                (right - 10, top + 10),
                (left + 10, bottom - 10),
                (right - 10, bottom - 10),
            ),
            key=lambda candidate: (candidate[0] - point[0]) ** 2 + (candidate[1] - point[1]) ** 2,
        )
        self.runtime.actions.move_to(parking_point)
        self.wait(0.08)
        marker_areas = self.__marker_avoidance_areas()
        # This RuneLite client's action-text OCR cannot reliably read either
        # the normal hover action or context-menu entries.  Use the tagged
        # tree geometry instead: try the route projection first, then a
        # compact ring, excluding a generous margin around every tree/NPC
        # marker. The selected point becomes the checkpoint anchor.
        offsets = (
            (0, 0),
            (-45, 0), (45, 0), (0, -35), (0, 35),
            (-70, -35), (70, -35), (-70, 35), (70, 35),
            (-110, 0), (110, 0), (0, -85), (0, 85),
            (-110, -70), (110, -70), (-110, 70), (110, 70),
            (-165, 0), (165, 0), (0, -130), (0, 130),
        )
        for dx, dy in offsets:
            candidate = (min(max(point[0] + dx, left), right), min(max(point[1] + dy, top), bottom))
            if not self.__has_marker_clearance(candidate, marker_areas):
                continue
            self._approved_walk_point = candidate
            if candidate != point:
                self.log_msg(f"Movement chose marker-clear ground at {candidate} instead of {point}.")
            return candidate
        self.log_msg(f"No nearby point had sufficient marker clearance around {point}; movement click cancelled safely.")
        return None

    def _OSRSWoodcutter__click_walk_here(self, *, force_context: bool = False) -> bool:
        """Click only a marker-clear point with no live object/NPC action."""
        if self._approved_walk_point != self.mouse.position():
            self.log_msg("Movement point lost its marker-clearance approval; click cancelled safely.")
            return False
        # This must be the final movement check: an NPC can move beneath the
        # cursor after marker detection but before the input is sent.
        for _ in range(2):
            self.wait(0.06)
            hover_text = self.mouseover_text()
            # A blank OCR result is not evidence of clear ground: the
            # reported tree click occurred when Chop down was rendered but
            # action-text OCR returned empty. Only two explicit Walk here
            # reads may authorize a normal left-click.
            if not hover_text or "walk here" not in hover_text.lower():
                self.log_msg(
                    "Movement could not verify clear ground from the live hover action; "
                    "selecting Walk here from the context menu."
                )
                approved_point = self._approved_walk_point
                clicked = super()._OSRSWoodcutter__click_walk_here(force_context=True)
                self._approved_walk_point = approved_point if clicked else None
                return clicked
        self.runtime.actions.click()
        return True

    def __marker_avoidance_areas(self) -> list[tuple[int, int, int, int]]:
        """Snapshot padded tagged-tree and banker rectangles."""
        areas = []
        for profile, padding in ((self.tree_profile, 22), (self.banker_profile, 32)):
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

    def __has_marker_clearance(
        self,
        point: tuple[int, int],
        marker_areas: list[tuple[int, int, int, int]] | None = None,
    ) -> bool:
        """Reject a point inside or immediately beside any tagged tree/banker."""
        areas = self.__marker_avoidance_areas() if marker_areas is None else marker_areas
        for left, top, right, bottom in areas:
            if left <= point[0] <= right and top <= point[1] <= bottom:
                return False
        return True

    def main_loop(self):
        self._OSRSWoodcutter__refresh_window_layout("movement diagnostic startup")
        self.log_msg(
            f"Movement diagnostic started: start ({self.start_point.x},{self.start_point.y},{self.start_point.plane}) "
            f"<-> end ({self.end_point.x},{self.end_point.y},{self.end_point.plane})."
        )

        # Begin with the closer endpoint so testing can start from either
        # location.  Subsequent legs always alternate between the same two
        # designated coordinates.
        player = self.__read_character_tile()
        if player is None:
            self.log_msg("Movement setup failed: could not read the current player tile.")
            return
        _, current = player
        # Head to the opposite endpoint first so a run launched at either
        # configured tile starts with a real movement leg.
        heading_to_end = current.distance_to(self.start_point) <= current.distance_to(self.end_point)

        for leg_number in range(1, self.round_trips * 2 + 1):
            self.cancellation.raise_if_cancelled()
            destination = self.end_point if heading_to_end else self.start_point
            name = "end point" if heading_to_end else "start point"
            arrival_distance = 0.0
            self.log_msg(f"Movement leg {leg_number}/{self.round_trips * 2}: heading to {name}.")
            if not self.__navigate_fluidly(destination, name, arrival_distance):
                self.log_msg(f"Movement leg {leg_number} failed; stopping so its route diagnostics can be reviewed.")
                return
            heading_to_end = not heading_to_end

        self.log_msg("Movement diagnostic completed all requested round trips.")

    def __read_character_tile(
        self, expected_tile: Tile | None = None, expected_distance: float = 5.0
    ) -> tuple[tuple[int, int], Tile] | None:
        """Hover a randomized interior point of the teal player tile and read it."""
        game_view = self.win.game_view
        if game_view is None:
            return None
        replacement_candidate = None
        for _ in range(3):
            # The local player remains at essentially the same screen anchor
            # while the camera follows it.  The geometric centre of the full
            # RuneLite screenshot is *not* that anchor (the side panel shifts
            # it), so retain the last confirmed screen point to avoid choosing
            # an unrelated cyan quadrilateral elsewhere in the scene.
            center = self._OSRSWoodcutter__find_player_tile(
                game_view, preferred_point=self._last_player_point
            )
            if center is None:
                self.wait(0.10)
                continue
            point = (center[0] + random.randint(-5, 5), center[1] + random.randint(-4, 4))
            self.runtime.actions.move_to(point)
            self.wait(0.12)
            tile = self._OSRSWoodcutter__read_coordinate_tooltip(point)
            if tile is None:
                continue
            # OCR occasionally turns 3158 into 3188/2158 even though the
            # cursor is correctly on the teal tile. Confirm from a different
            # interior pixel; moving the tooltip changes its raster position
            # and prevents one repeatable segmentation error from counting as
            # two independent coordinate readings.
            confirmation_point = point
            for _ in range(4):
                candidate_point = (center[0] + random.randint(-5, 5), center[1] + random.randint(-4, 4))
                if abs(candidate_point[0] - point[0]) + abs(candidate_point[1] - point[1]) >= 4:
                    confirmation_point = candidate_point
                    break
            self.runtime.actions.move_to(confirmation_point)
            self.wait(0.08)
            confirmation = self._OSRSWoodcutter__read_coordinate_tooltip(confirmation_point)
            if confirmation is None or confirmation.plane != tile.plane or confirmation.distance_to(tile) > 6:
                self.log_msg("Fluid movement rejected a non-repeating player coordinate OCR reading.")
                continue
            tile = confirmation
            if expected_tile is not None and tile.distance_to(expected_tile) > expected_distance:
                discrepancy = tile.distance_to(expected_tile)
                # Compass reset does not move the player, but the reading
                # taken before it can contain a repeatable tens-digit error.
                # Two independently hovered post-reset candidates agreeing
                # with one another outweigh that stale hint. Keep a strict
                # upper bound so 2157/3074-style corruption never qualifies.
                if discrepancy > 45:
                    self.log_msg(
                        f"Fluid movement rejected implausible post-compass player OCR "
                        f"({expected_tile.x},{expected_tile.y}) -> ({tile.x},{tile.y})."
                    )
                    continue
                if replacement_candidate is None or tile.distance_to(replacement_candidate) > 2:
                    replacement_candidate = tile
                    self.log_msg(
                        f"Fluid movement is verifying post-compass correction "
                        f"({expected_tile.x},{expected_tile.y}) -> ({tile.x},{tile.y})."
                    )
                    continue
                self.log_msg(
                    f"Fluid movement replaced stale pre-compass coordinate "
                    f"({expected_tile.x},{expected_tile.y}) with ({tile.x},{tile.y})."
                )
            # A fluid leg can cover many tiles before final polling returns
            # to the teal marker. Reject only digit-corruption-scale jumps.
            if self._last_player_tile is not None and tile.distance_to(self._last_player_tile) > 80:
                self.log_msg(
                    f"Fluid movement rejected implausible player coordinate "
                    f"({self._last_player_tile.x},{self._last_player_tile.y}) -> ({tile.x},{tile.y})."
                )
                continue
            self._last_player_point = confirmation_point
            self._last_player_tile = tile
            self._OSRSWoodcutter__remember_confirmed_tile(tile)
            self.log_msg(f"Fluid movement player tile: ({tile.x}, {tile.y}, {tile.plane}) at {confirmation_point}.")
            return confirmation_point, tile
        self.log_msg("Fluid movement could not establish the teal player tile coordinate after three reads.")
        return None

    def __reset_movement_compass(self) -> None:
        """Normalize the projection before each independent movement leg."""
        self._OSRSWoodcutter__reset_compass_to_north()

    def __navigate_fluidly(
        self, destination: Tile, destination_name: str, arrival_distance: float, correction_attempt: int = 0
    ) -> bool:
        """Keep queueing corrected ground clicks while the player is running."""
        expected_after_reset = self._last_player_tile
        self.__reset_movement_compass()
        player = self.__read_character_tile(expected_tile=expected_after_reset)
        if player is None:
            return False
        player_point, player_tile = player
        if player_tile == destination:
            self.log_msg(f"Already at {destination_name} ({destination.x}, {destination.y}).")
            return True

        game_view = self.win.game_view
        if game_view is None:
            return False
        # Resetting north fixes the world/screen axes. Start immediately from
        # a stable client-scale projection; live cursor coordinates steer the
        # bounded strides and exact-tile reads refine the final few tiles.
        calibration = self.__north_up_tile_map()
        self.log_msg("Fluid movement using immediate north-up tile projection.")
        left = game_view.left + 25
        top = game_view.top + 25
        right = min(game_view.left + game_view.width - 25, self.win.minimap_area.left - 25)
        bottom = min(game_view.top + game_view.height - 35, self.win.chat.top - 45)
        if right <= left or bottom <= top:
            self.log_msg("Fluid movement has no safe game-view click area.")
            return False

        initial_dx, initial_dy = destination.x - player_tile.x, destination.y - player_tile.y
        last_cursor_tile = player_tile
        for click_number in range(1, self.FLUID_MAX_CLICKS_PER_LEG + 1):
            self.cancellation.raise_if_cancelled()
            cursor_point = self.mouse.position()
            cursor_tile = self._OSRSWoodcutter__read_cursor_tile(cursor_point)
            cursor_is_bad = cursor_tile is None or cursor_tile.plane != destination.plane
            if not cursor_is_bad and cursor_tile.distance_to(last_cursor_tile) > 35:
                self.log_msg(
                    f"Fluid movement ignored implausible cursor coordinate "
                    f"({last_cursor_tile.x},{last_cursor_tile.y}) -> ({cursor_tile.x},{cursor_tile.y})."
                )
                cursor_is_bad = True
            if cursor_is_bad:
                recovered = self.__reanchor_live_cursor((left, top, right, bottom), destination, last_cursor_tile)
                if recovered is None:
                    self.log_msg("Fluid movement could not recover a trustworthy live cursor anchor.")
                    return False
                cursor_point, cursor_tile = recovered
            last_cursor_tile = cursor_tile

            # Crossing one axis is not enough to make a final click: the
            # other axis can still be many tiles away. Let the target vector
            # steer back toward the crossed axis until both are close.
            crossed_x = initial_dx and (cursor_tile.x - destination.x) * initial_dx >= 0
            crossed_y = initial_dy and (cursor_tile.y - destination.y) * initial_dy >= 0
            x_remaining = abs(cursor_tile.x - destination.x)
            y_remaining = abs(cursor_tile.y - destination.y)
            final_approach = (
                (x_remaining <= 5 and y_remaining <= 5)
                or (crossed_x and y_remaining <= self.TERMINAL_CROSS_AXIS_TILES)
                or (crossed_y and x_remaining <= self.TERMINAL_CROSS_AXIS_TILES)
            )
            if (crossed_x or crossed_y) and not final_approach:
                self.log_msg("Fluid movement cursor passed one target axis; steering back before final approach.")
            if final_approach:
                # The previous stride has put its highlighted ground tile
                # close to the goal. Let that movement settle, then count
                # from the stopped teal tile to the exact destination instead
                # of queuing another full-speed correction past it.
                stopped = self.__wait_for_player_stop()
                if stopped is None:
                    self.log_msg("Fluid movement could not establish a stopped player tile for the exact finish.")
                    return False
                return self.__finish_at_exact_tile(
                    stopped, destination, destination_name, calibration, (left, top, right, bottom), correction_attempt
                )
            stride_target = self.__limited_stride_target(cursor_tile, destination, self.FLUID_LOOKAHEAD_TILES)
            point = self.__project_cursor_target(
                cursor_point, cursor_tile, stride_target, calibration, (left, top, right, bottom)
            )
            if point is None:
                # At a game-view edge there may be zero remaining pixels in
                # the desired direction, even though camera tracking keeps
                # changing the world tile beneath that cursor. Re-click the
                # same forward edge instead of moving back to the centre and
                # pausing for another OCR anchor. The next loop reads the new
                # live tile under this unchanged screen point.
                point = (
                    min(max(cursor_point[0], left), right),
                    min(max(cursor_point[1], top), bottom),
                )
                self.log_msg(
                    f"Fluid movement continuing from forward edge at {point} "
                    f"({cursor_tile.x},{cursor_tile.y})."
                )
            point = self._resolve_movement_click_point(point, (left, top, right, bottom))
            if point is None:
                return False
            self.runtime.actions.move_to(point)
            if not self._OSRSWoodcutter__click_walk_here():
                return False
            self.log_msg(
                f"Fluid movement {click_number}: stride click at {point}; "
                f"cursor tile ({cursor_tile.x},{cursor_tile.y}) -> ({destination.x},{destination.y})."
            )
            # Do not wait for the player to stop. While it runs, camera
            # tracking changes the world coordinate under this cursor and the
            # next iteration recalibrates the following stride.
            self.wait(self.FLUID_CLICK_INTERVAL_SECONDS)
        self.log_msg(f"Fluid movement exceeded {self.FLUID_MAX_CLICKS_PER_LEG} clicks en route to {destination_name}.")
        return False

    def __reanchor_live_cursor(
        self,
        bounds: tuple[int, int, int, int],
        destination: Tile,
        previous: Tile,
    ) -> tuple[tuple[int, int], Tile] | None:
        """Recover from bad OCR without falling back to the leg's stale origin."""
        left, top, right, bottom = bounds
        point = ((left + right) // 2, (top + bottom) // 2)
        self.runtime.actions.move_to(point)
        self.wait(0.10)
        tile = self._OSRSWoodcutter__read_cursor_tile(point)
        if tile is None or tile.plane != destination.plane or tile.distance_to(previous) > 45:
            return None
        self.log_msg(f"Fluid movement recovered live cursor anchor at {point} ({tile.x},{tile.y}).")
        return point, tile

    @staticmethod
    def __limited_stride_target(current: Tile, destination: Tile, maximum_tiles: int) -> Tile:
        """Return a bounded waypoint that cannot command a full-screen reversal."""
        dx, dy = destination.x - current.x, destination.y - current.y
        span = max(abs(dx), abs(dy))
        if span <= maximum_tiles:
            return destination
        scale = maximum_tiles / span
        step_x, step_y = round(dx * scale), round(dy * scale)
        if step_x == 0 and dx:
            step_x = 1 if dx > 0 else -1
        if step_y == 0 and dy:
            step_y = 1 if dy > 0 else -1
        return Tile(current.x + step_x, current.y + step_y, current.plane)

    def __wait_for_player_stop(self) -> tuple[tuple[int, int], Tile] | None:
        """Wait for two stationary teal-tile reads without sending a new click."""
        deadline = time.monotonic() + 12.0
        previous = None
        stable_reads = 0
        while time.monotonic() < deadline:
            self.cancellation.raise_if_cancelled()
            player = self.__read_character_tile()
            if player is not None:
                current = player[1]
                if previous is not None and current.distance_to(previous) <= 1:
                    stable_reads += 1
                else:
                    stable_reads = 0
                if stable_reads >= 2:
                    return player
                previous = current
            self.wait(0.35)
        return None

    @classmethod
    def __north_up_tile_map(cls):
        """Return world-coordinate change per screen pixel for north-up view."""
        return (
            (1.0, 0.0),
            (0.0, 1.0),
            (1.0 / cls.NORTH_UP_X_PIXELS_PER_TILE, 0.0),
            (0.0, -1.0 / cls.NORTH_UP_Y_PIXELS_PER_TILE),
        )

    def __finish_at_exact_tile(
        self,
        stopped: tuple[tuple[int, int], Tile],
        destination: Tile,
        destination_name: str,
        calibration,
        bounds: tuple[int, int, int, int],
        correction_attempt: int,
    ) -> bool:
        """Use highlighted cursor coordinates to correct onto one exact tile."""
        point, source = stopped
        if source == destination:
            self.log_msg(f"Arrived at {destination_name}.")
            return True
        if max(abs(source.x - destination.x), abs(source.y - destination.y)) > 5:
            if correction_attempt < 3:
                self.log_msg(
                    f"Near-target cursor stopped with player at ({source.x},{source.y}); "
                    "resuming a bounded approach before exact tile counting."
                )
                return self.__navigate_fluidly(
                    destination, destination_name, 0.0, correction_attempt=correction_attempt + 1
                )
            self.log_msg("Player remained outside the five-tile exact-finish zone after three approaches.")
            return False
        anchor_point, anchor_tile = point, source
        for attempt in range(1, 4):
            candidate_point = self.__project_cursor_target(
                anchor_point, anchor_tile, destination, calibration, bounds, allow_clip=False
            )
            if candidate_point is None:
                self.log_msg("Exact finish could not display the destination tile inside the game view.")
                break
            self.runtime.actions.move_to(candidate_point)
            self.wait(0.15)
            highlighted = self._OSRSWoodcutter__read_cursor_tile(candidate_point)
            if highlighted is None:
                self.log_msg("Exact finish could not read the highlighted destination candidate.")
                continue
            if highlighted.distance_to(destination) > 5:
                # A projected point only a few tiles from the destination
                # cannot legitimately jump tens (or thousands) of tiles.
                # Keep the last trustworthy point/tile pair so the next
                # correction repeats the same projection instead of letting
                # one bad digit throw the cursor out of the game view.
                self.log_msg(
                    f"Exact finish rejected implausible cursor OCR "
                    f"({highlighted.x},{highlighted.y}); expected near "
                    f"({destination.x},{destination.y})."
                )
                continue
            if highlighted != destination:
                self.log_msg(
                    f"Exact finish correction {attempt}/3: highlighted "
                    f"({highlighted.x},{highlighted.y}) instead of ({destination.x},{destination.y})."
                )
                anchor_point, anchor_tile = candidate_point, highlighted
                continue
            if not self.__has_marker_clearance(candidate_point):
                self.log_msg(
                    "Exact finish destination is covered by a tagged marker; "
                    "choose a marker-clear endpoint tile."
                )
                return False
            self._approved_walk_point = candidate_point
            if not self._OSRSWoodcutter__click_walk_here():
                break
            self.log_msg(
                f"Exact finish: clicked destination tile ({destination.x},{destination.y}) at {candidate_point}."
            )
            arrived = self.__wait_for_player_stop()
            if arrived is not None and arrived[1] == destination:
                self.log_msg(f"Arrived at {destination_name}.")
                return True
            break
        if correction_attempt < 3:
            self.log_msg("Exact finish stopped short; resuming from the stopped player tile.")
            return self.__navigate_fluidly(
                destination, destination_name, 0.0, correction_attempt=correction_attempt + 1
            )
        self.log_msg("Exact finish did not reach the destination after three corrections; stopping safely.")
        return False

    def __calibrate_fluid_tile_map(self, game_view, player_point: tuple[int, int], player_tile: Tile):
        """Calibrate from clear-sided probes rather than fixed right/up pixels."""
        for attempt in range(1, 4):
            horizontal = []
            vertical = []
            # An arch, wall, or tall object can occlude one side of the
            # player. Probe both directions on each screen axis so a bad
            # right/up coordinate never vetoes a valid left/down pair.
            for screen_delta in ((60, 0), (-60, 0), (45, 0), (-45, 0), (0, -90), (0, 90), (0, -60), (0, 60)):
                point = (player_point[0] + screen_delta[0], player_point[1] + screen_delta[1])
                if not self._OSRSWoodcutter__point_in_game_view(point, game_view):
                    continue
                self.runtime.actions.move_to(point)
                self.wait(0.16)
                tile = self._OSRSWoodcutter__read_coordinate_tooltip(point)
                if tile is None or tile.plane != player_tile.plane:
                    continue
                world_delta = (tile.x - player_tile.x, tile.y - player_tile.y)
                if self.__is_fluid_probe(screen_delta, world_delta):
                    (horizontal if screen_delta[0] else vertical).append((screen_delta, world_delta))
                else:
                    self.log_msg(f"Fluid movement ignored occluded calibration probe {screen_delta}->{world_delta}.")
            if horizontal and vertical:
                x_delta = self.__fit_probe_axis(horizontal, 0)
                y_delta = self.__fit_probe_axis(vertical, 1)
                determinant = x_delta[0] * y_delta[1] - x_delta[1] * y_delta[0]
                if abs(determinant) >= 0.0001:
                    # Unit screen probes plus fitted world-units-per-pixel
                    # coefficients let projection use every valid sample.
                    # This is much less sensitive to a 60px probe rounding
                    # to one tile on one frame and two tiles on another.
                    calibration = ((1.0, 0.0), (0.0, 1.0), x_delta, y_delta)
                    self.log_msg(
                        f"Fluid tile map fitted from {len(horizontal)} horizontal and {len(vertical)} vertical probes: "
                        f"screen-x->{x_delta}, screen-y->{y_delta}."
                    )
                    return calibration
            self.log_msg(f"Fluid movement rejected calibration attempt {attempt}/3; retrying.")
        return None

    @staticmethod
    def __fit_probe_axis(samples, component: int) -> tuple[float, float]:
        """Least-squares fit of world-coordinate change per screen pixel."""
        denominator = sum(screen_delta[component] ** 2 for screen_delta, _ in samples)
        return tuple(
            sum(screen_delta[component] * world_delta[world_axis] for screen_delta, world_delta in samples)
            / denominator
            for world_axis in (0, 1)
        )

    @staticmethod
    def __is_fluid_probe(screen_delta: tuple[int, int], world_delta: tuple[int, int]) -> bool:
        """Return whether a probe follows its expected north-up screen axis."""
        screen_x, screen_y = screen_delta
        world_x, world_y = world_delta
        if screen_x:
            return (
                1 <= abs(world_x) <= 6
                and world_x * screen_x > 0
                and abs(world_y) <= max(1, abs(world_x))
            )
        return (
            1 <= abs(world_y) <= 8
            and world_y * screen_y < 0
            and abs(world_x) <= max(2, round(abs(world_y) * 0.75))
        )

    @staticmethod
    def __is_fluid_calibration(calibration) -> bool:
        """Compatibility validator for tests and externally supplied maps."""
        x_probe, y_probe, x_delta, y_delta = calibration
        return (
            OSRSMovement.__is_fluid_probe(x_probe, x_delta)
            and OSRSMovement.__is_fluid_probe(y_probe, y_delta)
            and x_delta[0] * y_delta[1] - x_delta[1] * y_delta[0] != 0
        )

    @staticmethod
    def __project_cursor_target(
        anchor_point: tuple[int, int],
        anchor_tile: Tile,
        destination: Tile,
        calibration,
        bounds: tuple[int, int, int, int],
        *,
        allow_clip: bool = True,
    ) -> tuple[int, int] | None:
        """Project a destination from the live cursor tile, clipped to the canvas."""
        x_probe, y_probe, x_tile_delta, y_tile_delta = calibration
        determinant = x_tile_delta[0] * y_tile_delta[1] - y_tile_delta[0] * x_tile_delta[1]
        # Fitted calibration stores world tiles per screen pixel, so a valid
        # determinant is naturally around 0.001. The former whole-probe
        # cutoff rejected good fitted maps such as 0.028 * -0.0346.
        if abs(determinant) < 1e-8:
            return None
        tile_x, tile_y = destination.x - anchor_tile.x, destination.y - anchor_tile.y
        x_factor = (tile_x * y_tile_delta[1] - tile_y * y_tile_delta[0]) / determinant
        y_factor = (x_tile_delta[0] * tile_y - x_tile_delta[1] * tile_x) / determinant
        vector = (x_factor * x_probe[0] + y_factor * y_probe[0], x_factor * x_probe[1] + y_factor * y_probe[1])
        left, top, right, bottom = bounds
        scales = []
        if vector[0] > 0:
            scales.append((right - anchor_point[0]) / vector[0])
        elif vector[0] < 0:
            scales.append((left - anchor_point[0]) / vector[0])
        if vector[1] > 0:
            scales.append((bottom - anchor_point[1]) / vector[1])
        elif vector[1] < 0:
            scales.append((top - anchor_point[1]) / vector[1])
        positive_scales = [scale for scale in scales if scale > 0]
        if not positive_scales:
            return None
        scale = min(1.0, min(positive_scales))
        if not allow_clip and scale < 1.0:
            return None
        return (
            min(max(round(anchor_point[0] + vector[0] * scale), left), right),
            min(max(round(anchor_point[1] + vector[1] * scale), top), bottom),
        )
