import time
import random
import re
from pathlib import Path
from math import dist

import cv2
import numpy as np
import utilities.api.item_ids as ids
import utilities.random_util as rd
import utilities.imagesearch as imagesearch
import utilities.color as clr
import utilities.ocr as ocr
from utilities.coordinate_ocr import is_available as coordinate_ocr_available
from utilities.coordinate_ocr import read_tile_coordinates
from model.osrs.osrs_bot import OSRSBot
from runtime import ActionTimeoutError, Tile
from utilities.geometry import Rectangle
from utilities.hsv_color import HSVColorProfile


class OSRSWoodcutter(OSRSBot):
    LOG_WAIT_TIMEOUT_SECONDS = 18.0
    ROUTE_CHUNK_TILES = 7
    ROUTE_CHECKPOINT_SECONDS = 2.2

    def __init__(self):
        bot_title = "Woodcutter"
        description = (
            "This bot power-chops wood. Position your character near some trees, tag them, and press Play.\nTHIS SCRIPT IS AN EXAMPLE, DO NOT USE LONGTERM."
        )
        super().__init__(bot_title=bot_title, description=description)
        self.running_time = 10
        self.take_breaks = False
        self.test_mode = False
        self.options_set = True
        self.start_tile = Tile(3158, 3459, 0)
        self.bank_location_name = "GE West Side"
        self.bronze_axe_sprite = Path(__file__).resolve().parents[2] / "images" / "bot" / "items" / "Bronze_axe.png"
        self.logs_sprite = Path(__file__).resolve().parents[2] / "images" / "bot" / "items" / "Logs.png"
        project_root = Path(__file__).resolve().parents[3]
        self.bank_reference = project_root / "Bank Tab with deposit all and x buttons showing.png"
        # These captures show the current client controls both with and
        # without RuneLite's sidebar.  Crop only the icon artwork, rather
        # than the surrounding tab frame: the frame changes when a tab is
        # active, while the icon itself does not.
        self.tab_references = (
            project_root / "inventory screenshot no runelite sidebar.png",
            project_root / "inventory screenshot with runelite sidebar.png",
        )
        # RuneLite's Deposit inventory control is the backpack with the green
        # arrow (not the adjacent text button labelled "All").
        self.bank_deposit_all_template = self.__load_reference_crop(self.bank_reference, (659, 496, 715, 550))
        self.bank_close_template = self.__load_reference_crop(self.bank_reference, (758, 45, 800, 85))
        # The icons are at fixed positions within the OSRS client portion of
        # both captures.  Keep two samples because the RuneLite sidebar can
        # slightly change rendering without moving the client controls.
        self.tab_templates = {
            "inventory": tuple(
                self.__load_reference_crop(reference, (1008, 300, 1050, 345))
                for reference in self.tab_references
            ),
            "equipment": tuple(
                self.__load_reference_crop(reference, (1061, 300, 1103, 345))
                for reference in self.tab_references
            ),
        }
        # Tagged-tree outlines vary slightly with client scaling and scene
        # lighting. Keep this aligned with the known RuneLite capture range.
        self.tree_profile = HSVColorProfile.from_rgb("tagged_tree", (255, 0, 231), tolerance=(5, 50, 50), min_area=4)
        # Keep banker markers distinct from the cyan player-tile marker.
        self.banker_profile = HSVColorProfile.from_rgb("highlighted_banker", (0, 0, 255), tolerance=(12, 130, 130), min_area=150)
        self._unavailable_tree_points: dict[tuple[int, int], float] = {}
        self._last_player_point: tuple[int, int] | None = None
        self._last_player_tile: Tile | None = None
        self._last_coordinate_was_rejected = False
        self._last_rejected_coordinate: tuple[int, int] | None = None
        self._movement_attempts: dict[tuple[int, int, int, int, int, int], int] = {}
        self._last_movement_point: tuple[int, int] | None = None
        self._route_stall_count = 0
        self._local_tile_calibration = None
        self._tab_indices = {"inventory": 3, "equipment": 4}

    def create_options(self):
        self.options_builder.add_slider_option("running_time", "How long to run (minutes)?", 1, 500)
        self.options_builder.add_checkbox_option("take_breaks", "Take breaks?", [" "])
        bank_names = list(self.runtime.bank_locations.names())
        if bank_names:
            self.options_builder.add_dropdown_option("bank_location_name", "Bank location", bank_names)

    def save_options(self, options: dict):
        for option in options:
            if option == "running_time":
                self.running_time = options[option]
            elif option == "take_breaks":
                self.take_breaks = options[option] != []
            elif option == "bank_location_name":
                if self.runtime.bank_locations.find(options[option]) is None:
                    self.log_msg(f"Unknown bank location: {options[option]}")
                    self.options_set = False
                    return
                self.bank_location_name = options[option]
            else:
                self.log_msg(f"Unknown option: {option}")
                print("Developer: ensure that the option keys are correct, and that options are being unpacked correctly.")
                self.options_set = False
                return
        self.log_msg(f"Running time: {self.running_time} minutes.")
        self.log_msg(f"Bot will{' ' if self.take_breaks else ' not '}take breaks.")
        self.log_msg("Options set successfully.")
        self.options_set = True

    def main_loop(self):
        if self.test_mode:
            self.__run_test_script()
            return

        self.__refresh_window_layout("startup")
        if not self.__startup_checks(check_inventory=False):
            return

        # Complete both panel checks before touching the game view. Selecting
        # inventory here prevents the startup sequence from moving to the
        # player between equipment and inventory inspection.
        self.log_msg("Checking inventory for one free space...")
        if not self.__select_control_panel_tab("inventory"):
            return
        self.wait(0.5)
        if not self.__inventory_has_free_slot():
            self.log_msg("Startup check failed: inventory has no free space.")
            return

        self.log_msg(f"Using bank location: {self.bank_location_name}.")
        if not self.__navigate_to_tile(self.start_tile, "tree area"):
            return

        if not self.__navigate_to_tree_cluster():
            self.log_msg("Could not visually locate the tagged tree cluster after minimap search.")
            return

        failed_searches = 0

        # Main loop
        start_time = time.time()
        end_time = self.running_time * 60
        while time.time() - start_time < end_time:
            self.cancellation.raise_if_cancelled()
            # 5% chance to take a break between tree searches
            if rd.random_chance(probability=0.05) and self.take_breaks:
                self.take_break(max_seconds=30, fancy=True)

            # Bank only when every inventory slot is occupied. This is item
            # agnostic: bird nests or other incidental drops count too.
            if self.__inventory_is_full():
                self.log_msg("Inventory is full; travelling to the bank.")
                if not self.__bank_inventory():
                    return
                continue

            # Select a fresh tagged tree each cycle; marker detection replaces the
            # old hover-text OCR check for this scaled client layout.
            tree_point = self.__move_mouse_to_nearest_tree()
            if tree_point is None:
                failed_searches += 1
                if failed_searches % 10 == 0:
                    self.log_msg("Searching for trees...")
                if failed_searches > 60:
                    # If we've been searching for a whole minute...
                    self.__logout("No tagged trees found. Logging out.")
                self.wait(1)
                continue
            failed_searches = 0  # If code got here, a tree was found

            baseline_inventory_count = self.__inventory_occupied_slot_count()
            self.runtime.actions.click()
            self.runtime.record_action_intent("chop_tree")
            try:
                self.wait_for(
                    lambda: self.__inventory_occupied_slot_count() > baseline_inventory_count,
                    timeout=self.LOG_WAIT_TIMEOUT_SECONDS,
                    interval=0.5,
                    action="new inventory item",
                )
            except ActionTimeoutError:
                # Another player can deplete a tree after it was detected.
                # Treat that as a recoverable unavailable target rather than a
                # bot-wide failure, and avoid retrying its same marker briefly.
                self._unavailable_tree_points[tree_point] = time.monotonic() + 45.0
                self.runtime.record_recovery("chop_tree", "no log received; tree unavailable")
                self.log_msg(f"No log received from tree at {tree_point}; trying a different tagged tree.")
                self.wait(0.5)
                continue

            self.update_progress((time.time() - start_time) / end_time)

        self.update_progress(1)
        self.__logout("Finished.")

    def __startup_checks(self, *, check_inventory: bool = True) -> bool:
        """Confirm the equipped axe, optionally checking inventory space."""
        self.__refresh_window_layout("equipment check")
        self.log_msg("Checking gear tab for an equipped bronze axe...")
        # Click Test verified that the equipment tab is directly to the right
        # of Inventory in this client layout.
        if not self.__select_control_panel_tab("equipment"):
            return False
        self.wait(0.5)
        if not self.__find_equipped_axe():
            self.log_msg("Startup check failed: bronze axe sprite was not found in the gear tab.")
            return False
        self.log_msg("Bronze axe is equipped.")

        if check_inventory:
            self.__refresh_window_layout("inventory check")
            self.log_msg("Checking inventory for one free space...")
            if not self.__select_control_panel_tab("inventory"):
                return False
            self.wait(0.5)
            if not self.__inventory_has_free_slot():
                self.log_msg("Startup check failed: inventory has no free space.")
                return False
        self.log_msg(
            "Startup equipment check passed."
            if not check_inventory
            else "Startup checks passed: bronze axe equipped and inventory has free space."
        )
        return True

    def __select_control_panel_tab(self, name: str) -> bool:
        """Locate and click a tab icon visually, falling back to panel geometry."""
        # Search the live right half of the client instead of relying on the
        # cached control-panel rectangle. RuneLite's expanded settings
        # sidebar changes the panel scale and can make that rectangle stale.
        client = self.win.rectangle()
        search_area = self.win.control_panel
        if client is not None:
            search_area = Rectangle(
                client.left + client.width // 2,
                self.win.control_panel.top,
                client.width - client.width // 2,
                self.win.control_panel.height,
            )
        for template in self.tab_templates[name]:
            visual_tab = self.__find_template_rect(search_area, template, confidence=0.16)
            if visual_tab is not None:
                # Keep the random click tightly around the icon center. This
                # preserves human variation without allowing a scaled match
                # to reach the adjacent Quest List tab.
                point = self.runtime.actions.click_within(visual_tab, center_fraction=0.20)
                self.log_msg(f"Selecting {name} tab by visual match at randomized point {point}.")
                self.wait(0.5)
                return True
        tab_index = self._tab_indices[name]
        point = self.runtime.actions.click_control_panel_tab(self.win, tab_index)
        self.log_msg(f"Selecting {name} tab {tab_index} by fallback geometry at randomized point {point}.")
        self.wait(0.5)
        return True

    def __find_equipped_axe(self) -> bool:
        """Search the live right-side panel, independent of sidebar width."""
        client = self.win.rectangle()
        if client is None:
            return False
        # The equipment slots are always in the right-side client panel, but
        # the panel's left edge changes when RuneLite's sidebar is toggled.
        panel_width = min(700, client.width)
        panel_left = client.left + client.width - panel_width
        panel = Rectangle(panel_left, self.win.control_panel.top, panel_width, self.win.control_panel.height)
        self.log_msg(f"Searching equipment panel region {panel.left},{panel.top},{panel.width},{panel.height}.")
        return self.__find_template(panel, self.bronze_axe_sprite, confidence=0.40)

    def __refresh_window_layout(self, reason: str) -> None:
        """Re-read the live client geometry before any tab interaction.

        RuneLite can add or remove its right sidebar without changing the
        game process. Reinitializing here refreshes the control-panel and tab
        rectangles so mouse movement/clicks use the currently visible layout.
        """
        try:
            # Visual detection reads the desktop, so RuneLite must be the
            # foreground window when another application or browser window
            # is covering it.
            self.win.focus()
            self.wait(0.15)
            if self.win.initialize():
                self.log_msg(f"RuneLite layout refreshed before {reason}.")
            else:
                self.log_msg(f"RuneLite layout refresh failed before {reason}.")
        except Exception as error:
            self.log_msg(f"RuneLite layout refresh error before {reason}: {error}.")

    def __read_current_tile(self) -> Tile | None:
        """Read the hovered tile coordinate from RuneLite's on-screen text."""
        self._last_coordinate_was_rejected = False
        game_view = self.win.game_view
        if game_view is None:
            return None
        player_tile = self.__find_player_tile(game_view, preferred_point=self._last_player_point)
        if player_tile is None:
            # The tile outline can briefly disappear while a tree is being
            # chopped or while the scene redraws. The last confirmed screen
            # point is still a useful coordinate probe, so try it before
            # aborting navigation.
            if self._last_player_point is None:
                self.log_msg("Current-tile check failed: cyan highlighted player tile was not found.")
                return None
            player_tile = self._last_player_point
            self.log_msg(f"Cyan player tile temporarily unavailable; probing last known point {player_tile}.")
        self.log_msg(f"Highlighted player tile found at {player_tile}; moving pointer inside it.")
        self.runtime.actions.move_to(player_tile)
        self.wait(0.25)
        tile = self.__read_coordinate_tooltip(player_tile)
        if tile is not None:
            if self._last_player_tile is not None and tile.plane != self._last_player_tile.plane:
                self.log_msg(f"Ignoring transient OCR plane {tile.plane}; keeping plane {self._last_player_tile.plane}.")
                tile = Tile(tile.x, tile.y, self._last_player_tile.plane)
            if self._last_player_tile is not None:
                jump = abs(tile.x - self._last_player_tile.x) + abs(tile.y - self._last_player_tile.y)
                # A player cannot move dozens of tiles between two tooltip
                # reads.  OCR occasionally swaps a digit (for example 3166
                # becoming 2167); never let that poison the next movement
                # vector or calibration.
                # A checkpoint can arrive after a delayed OCR frame while a
                # route chunk is completing, so allow a normal movement
                # segment. Larger jumps remain characteristic of OCR digit
                # corruption (for example 3488 becoming 3060).
                if jump > 25:
                    self._last_coordinate_was_rejected = True
                    rejected = (tile.x, tile.y)
                    if rejected != self._last_rejected_coordinate:
                        self.log_msg(
                            f"Ignoring implausible coordinate OCR jump: "
                            f"{self._last_player_tile.x},{self._last_player_tile.y} -> {tile.x},{tile.y}."
                        )
                        self._last_rejected_coordinate = rejected
                    return self._last_player_tile
            self._last_rejected_coordinate = None
            self._last_player_point = player_tile
            self._last_player_tile = tile
        return tile

    def __read_confirmed_route_tile(self) -> Tile | None:
        """Read the route origin twice so one bad OCR frame cannot steer it."""
        first = self.__read_current_tile()
        if first is None:
            return None
        second = self.__read_current_tile()
        if second is None:
            return first
        if abs(second.x - first.x) + abs(second.y - first.y) <= 5:
            return second
        self.log_msg(
            f"Route origin OCR disagreed ({first.x},{first.y} vs {second.x},{second.y}); "
            "using the later reading."
        )
        return second

    @staticmethod
    def __find_player_tile(game_view, preferred_point: tuple[int, int] | None = None) -> tuple[int, int] | None:
        """Return the screen center of the highlighted player tile.

        The supported RuneLite configuration uses cyan for the player tile.
        Bankers use a distinct dark-blue marker and are detected separately.
        """
        image = game_view.screenshot()
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        candidates = []
        # Cyan player-tile outline in the current RuneLite configuration.
        for priority, (lower, upper) in enumerate(
            (
                ((80, 120, 120), (105, 255, 255)),
            )
        ):
            mask = cv2.inRange(hsv, np.array(lower, dtype=np.uint8), np.array(upper, dtype=np.uint8))
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            for contour in contours:
                x, y, width, height = cv2.boundingRect(contour)
                if not (25 <= width <= 130 and 25 <= height <= 130):
                    continue
                ratio = width / max(1, height)
                if 0.65 <= ratio <= 1.5:
                    # The player tile has the largest continuous highlighted
                    # area; bounding-box area can incorrectly favor minimap
                    # icons with a large empty box.
                    center_x, center_y = game_view.left + x + width // 2, game_view.top + y + height // 2
                    candidates.append((priority, -cv2.contourArea(contour), abs(width - height), center_x, center_y))
        if not candidates:
            return None
        if preferred_point is not None:
            # A player tile moves smoothly across consecutive reads. Prefer
            # the candidate nearest the previously OCR-confirmed player tile
            # so unrelated highlighted overlays cannot hijack navigation.
            _, _, _, x, y = min(
                candidates,
                key=lambda candidate: (candidate[0], dist((candidate[3], candidate[4]), preferred_point), candidate[1], candidate[2]),
            )
            return x, y
        _, _, _, x, y = min(candidates)
        return x, y

    def __read_coordinate_tooltip(self, point: tuple[int, int]) -> Tile | None:
        """OCR the coordinate tooltip rendered next to a hovered tile."""
        client = self.win.rectangle()
        if client is None:
            return None
        if coordinate_ocr_available():
            # RuneLite positions the tooltip beside the cursor and may flip
            # it above/left near a screen edge. Try all neighboring placements.
            for offset_x, offset_y, width, height in (
                (-60, -60, 340, 160),
                (10, -80, 300, 160),
                (-260, -80, 300, 160),
                (-80, 10, 360, 180),
            ):
                left = max(client.left, point[0] + offset_x)
                top = max(client.top, point[1] + offset_y)
                right = min(client.left + client.width, left + width)
                bottom = min(client.top + client.height, top + height)
                values = read_tile_coordinates(Rectangle(left, top, max(1, right - left), max(1, bottom - top)).screenshot())
                if values is not None:
                    x, y, plane = values
                    self.log_msg(f"Coordinate OCR read: ({x}, {y}, {plane}).")
                    return Tile(x, y, plane)

        tooltip = Rectangle(
            max(client.left, point[0] - 60),
            max(client.top, point[1] - 60),
            min(340, client.left + client.width - max(client.left, point[0] - 60)),
            min(160, client.top + client.height - max(client.top, point[1] - 60)),
        )

        colors = [clr.OFF_CYAN, clr.OFF_GREEN, clr.OFF_ORANGE, clr.OFF_WHITE, clr.OFF_YELLOW]
        texts = [
            ocr.extract_text(tooltip, font, colors)
            for font in (ocr.BOLD_12, ocr.PLAIN_12)
        ]
        self.log_msg(f"Coordinate OCR near {point}: {texts!r}")
        if not coordinate_ocr_available():
            self.log_msg("Coordinate OCR engine unavailable: install Tesseract and the pytesseract package.")
        for text in texts:
            tile = self.__parse_tile_text(text)
            if tile is not None:
                return tile
        return None

    @staticmethod
    def __parse_tile_text(text: str) -> Tile | None:
        if not isinstance(text, str):
            return None
        digits = re.findall(r"\d+", text)
        if len(digits) < 2:
            compact = re.sub(r"\D", "", text)
            if len(compact) >= 8:
                digits = [compact[:4], compact[4:8], compact[8:9]]
        if len(digits) < 2:
            return None
        try:
            x, y = int(digits[0]), int(digits[1])
            plane = int(digits[2]) if len(digits) > 2 and int(digits[2]) <= 3 else 0
        except ValueError:
            return None
        if not (1000 <= x <= 5000 and 1000 <= y <= 5000):
            return None
        return Tile(x, y, plane)

    def __navigate_to_tile(self, destination: Tile, destination_name: str, *, arrival_distance: float = 1.0) -> bool:
        """Walk using a north-reset, cached-calibration chunked route."""
        self._route_stall_count = 0
        self._movement_attempts.clear()
        self.__reset_compass_to_north()
        current = self.__read_confirmed_route_tile()
        if current is None:
            self.log_msg("Could not read the current tile from the on-screen coordinate overlay.")
            self.log_msg("Enable RuneLite tile-coordinate text and keep the player visible before starting.")
            return False
        if current.distance_to(destination) <= arrival_distance:
            self.log_msg(f"Already at {destination_name} ({destination.x}, {destination.y}).")
            return True

        self.log_msg(
            f"Current tile: ({current.x}, {current.y}, {current.plane}); "
            f"walking to {destination_name} ({destination.x}, {destination.y}, {destination.plane})."
        )
        for action_number in range(1, 31):
            self.cancellation.raise_if_cancelled()
            if current.distance_to(destination) <= arrival_distance:
                self.log_msg(f"Arrived at {destination_name}.")
                return True

            previous_distance = current.distance_to(destination)
            waypoint = self.__route_waypoint(current, destination)
            stopped_at = self.__move_toward_destination_in_game_view(current, waypoint, action_number)
            if stopped_at is None:
                # A single reread is a recovery path, not the normal route
                # loop. This keeps OCR from dominating routine movement.
                stopped_at = self.__read_current_tile()
            if stopped_at is None:
                self.log_msg("Player did not produce a usable coordinate after game-view movement.")
                return False
            movement_key = (current.x, current.y, destination.x, destination.y, current.plane, destination.plane)
            made_progress = stopped_at.distance_to(destination) < previous_distance - 0.5
            if not made_progress:
                attempts = self._movement_attempts.get(movement_key, 0) + 1
                self._movement_attempts[movement_key] = attempts
                self._route_stall_count += 1
                self.log_msg(
                    f"Movement did not approach the destination from {current.x},{current.y}; "
                    f"trying an alternate walk point ({attempts}/5)."
                )
                if attempts >= 5:
                    self.log_msg("Movement appears blocked; stopping instead of retrying the same inaccessible tile.")
                    return False
            else:
                self._route_stall_count = 0
                self._movement_attempts.clear()
            # Continue route planning from the latest checkpoint, not from
            # the route origin. Without this update every chunk targets the
            # same screen point and the player can run past the destination.
            current = stopped_at

        self.log_msg("Could not reach the configured tree area within 30 single-action moves.")
        return False

    def __reset_compass_to_north(self) -> None:
        """Normalize camera orientation before deriving a route map."""
        compass = self.win.compass_orb
        if compass is None:
            self.log_msg("Compass was not located; retaining the existing route calibration.")
            return
        point = self.runtime.actions.click_within(compass, center_fraction=0.25)
        self.log_msg(f"Resetting compass north at randomized point {point}.")
        self.wait(0.35)
        # Resetting the compass to north preserves the screen orientation
        # used by the existing projection. Keep a successful calibration for
        # the next tree/bank route; recalibrating beside a wall can expose the
        # coordinate tooltip to an occluded or stale tile.

    @classmethod
    def __route_waypoint(cls, current: Tile, destination: Tile) -> Tile:
        """Return a nearby world-tile waypoint in the direction of the goal."""
        dx, dy = destination.x - current.x, destination.y - current.y
        span = max(abs(dx), abs(dy))
        if span <= cls.ROUTE_CHUNK_TILES:
            return destination
        scale = cls.ROUTE_CHUNK_TILES / span
        step_x = round(dx * scale)
        step_y = round(dy * scale)
        if step_x == 0 and dx:
            step_x = 1 if dx > 0 else -1
        if step_y == 0 and dy:
            step_y = 1 if dy > 0 else -1
        return Tile(current.x + step_x, current.y + step_y, current.plane)

    def __move_toward_destination_in_game_view(self, current: Tile, destination: Tile, action_number: int) -> Tile | None:
        """Walk toward a target using only a safe point in the main game view."""
        game_view = self.win.game_view
        if game_view is None:
            return None
        # The cursor normally remains over the last game tile that was
        # clicked. Use its live coordinate as the route anchor; scanning the
        # cyan player tile is reserved for recovery when the cursor tooltip is
        # unavailable or clearly inconsistent.
        anchor_point = self.mouse.position()
        anchor_tile = self.__read_cursor_tile(anchor_point)
        if anchor_tile is None or anchor_tile.plane != current.plane or anchor_tile.distance_to(current) > 20:
            anchor_point = self.__find_player_tile(game_view, preferred_point=self._last_player_point)
            anchor_tile = current if anchor_point is not None else None
        if anchor_point is None or anchor_tile is None:
            return None
        calibration = self._local_tile_calibration or self.__calibrate_local_tile_map(game_view, anchor_point, anchor_tile)
        if calibration is None:
            return None
        self._local_tile_calibration = calibration

        x_probe, y_probe, x_tile_delta, y_tile_delta = calibration
        tile_x, tile_y = destination.x - anchor_tile.x, destination.y - anchor_tile.y
        determinant = x_tile_delta[0] * y_tile_delta[1] - y_tile_delta[0] * x_tile_delta[1]
        if abs(determinant) < 0.001:
            return None
        x_factor = (tile_x * y_tile_delta[1] - tile_y * y_tile_delta[0]) / determinant
        y_factor = (x_tile_delta[0] * tile_y - x_tile_delta[1] * tile_x) / determinant
        vector = (x_factor * x_probe[0] + y_factor * y_probe[0], x_factor * x_probe[1] + y_factor * y_probe[1])
        if abs(vector[0]) < 1 and abs(vector[1]) < 1:
            return current

        # Restrict directional clicks to the visible game canvas. The chat
        # and minimap occupy portions of game_view in fallback layouts.
        left = game_view.left + 25
        top = game_view.top + 25
        right = min(game_view.left + game_view.width - 25, self.win.minimap_area.left - 25)
        # Leave a generous buffer above chat. Fallback layouts can report the
        # chat boundary a few pixels late while the client/sidebar is resizing.
        bottom = min(game_view.top + game_view.height - 35, self.win.chat.top - 45)
        if right <= left or bottom <= top:
            return None
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
        point = (round(anchor_point[0] + vector[0] * scale), round(anchor_point[1] + vector[1] * scale))
        # If the last destination was inaccessible, move the next click along
        # the same direction but offset perpendicular to it. This avoids
        # repeatedly selecting one blocked tile under an object, wall, or
        # other collision boundary.
        movement_key = (current.x, current.y, destination.x, destination.y, current.plane, destination.plane)
        attempt = max(self._movement_attempts.get(movement_key, 0), self._route_stall_count)
        if attempt:
            length = max(1.0, (vector[0] ** 2 + vector[1] ** 2) ** 0.5)
            perpendicular = (-vector[1] / length, vector[0] / length)
            offsets = ((70, 0), (-70, 0), (0, 70), (0, -70))
            offset_x, offset_y = offsets[(attempt - 1) % len(offsets)]
            point = (
                round(point[0] + perpendicular[0] * offset_x + perpendicular[1] * offset_y),
                round(point[1] + perpendicular[1] * offset_x - perpendicular[0] * offset_y),
            )
            point = (
                min(max(point[0], left), right),
                min(max(point[1], top), bottom),
            )
        if self._last_movement_point == point:
            point = (point[0] + 45, point[1])
            point = (min(max(point[0], left), right), min(max(point[1], top), bottom))
        if self.__point_over_tagged_tree(point):
            # A route waypoint can project onto a tagged tree even though the
            # player only needs to approach the tree area. Step back along
            # and sideways from the route vector to find clear ground before
            # resorting to a context-menu interaction.
            clear_point = None
            vector_length = max(1.0, (point[0] - anchor_point[0]) ** 2 + (point[1] - anchor_point[1]) ** 2) ** 0.5
            perpendicular = (
                -(point[1] - anchor_point[1]) / vector_length,
                (point[0] - anchor_point[0]) / vector_length,
            )
            for fraction in (0.75, 0.55, 0.35, 0.20):
                for lateral in (0, -120, 120, -200, 200):
                    candidate = (
                        round(anchor_point[0] + (point[0] - anchor_point[0]) * fraction + perpendicular[0] * lateral),
                        round(anchor_point[1] + (point[1] - anchor_point[1]) * fraction + perpendicular[1] * lateral),
                    )
                    candidate = (
                        min(max(candidate[0], left), right),
                        min(max(candidate[1], top), bottom),
                    )
                    if not self.__point_over_tagged_tree(candidate):
                        clear_point = candidate
                        break
                if clear_point is not None:
                    break
            if clear_point is not None:
                self.log_msg(f"Movement point overlaps a tagged tree; using clear ground at {clear_point}.")
                point = clear_point
        self._last_movement_point = point
        self.runtime.actions.move_to(point)
        self.wait(0.2)
        self.log_msg(
            f"Game-view movement {action_number}: {current.x},{current.y} -> "
            f"{destination.x},{destination.y} at {point}."
        )
        if not self.__click_walk_here(force_context=self.__point_over_tagged_tree(point)):
            return None
        # Context-menu selection moves the cursor away from the game tile;
        # restore the destination point so the next checkpoint can read its
        # on-screen coordinate directly.
        self.runtime.actions.move_to(point)
        return self.__read_route_checkpoint(current, point, action_number)

    def __read_cursor_tile(self, point: tuple[int, int] | None = None) -> Tile | None:
        """Read the tile currently under the virtual cursor without moving it."""
        self._last_coordinate_was_rejected = False
        game_view = self.win.game_view
        if game_view is None:
            return None
        point = point or self.mouse.position()
        if not self.__point_in_game_view(point, game_view):
            return None
        tile = self.__read_coordinate_tooltip(point)
        if tile is None or self._last_coordinate_was_rejected:
            return None
        return tile

    def __read_route_checkpoint(self, previous: Tile, point: tuple[int, int], action_number: int) -> Tile | None:
        """Read the clicked tile once after a directional route chunk."""
        self.wait(self.ROUTE_CHECKPOINT_SECONDS)
        # Periodically resynchronize against the cyan player tile. Cursor
        # coordinates are faster for ordinary chunks, but a blocked path or
        # camera shift can otherwise let the route estimate drift.
        if action_number % 3 == 0:
            player = self.__read_current_tile()
            if player is not None and not self._last_coordinate_was_rejected:
                return player
        current = self.__read_cursor_tile(point)
        if current is not None:
            # Cursor coordinates are the normal route state now. Keep the
            # world-coordinate cache synchronized so the next route does not
            # compare a real tree position against the previous bank tile.
            self._last_player_tile = current
            return current
        # A scene redraw can hide the cursor tooltip. Use the cyan player tile
        # only as a recovery path, not during normal route checkpoints.
        self.wait(0.6)
        current = self.__read_current_tile()
        return current if current is not None and not self._last_coordinate_was_rejected else None

    def __navigate_local_to_tile(self, current: Tile, destination: Tile, destination_name: str, *, arrival_distance: float) -> bool:
        """Click a nearby destination using an OCR-calibrated game-view map."""
        game_view = self.win.game_view
        if game_view is None:
            self.log_msg("Local movement failed: game view was not located.")
            return False
        player_point = self.__find_player_tile(game_view, preferred_point=self._last_player_point)
        if player_point is None:
            self.log_msg("Local movement failed: player tile was not located.")
            return False

        calibration = self.__calibrate_local_tile_map(game_view, player_point, current)
        if calibration is None:
            self.log_msg("Local movement failed: could not calibrate the current game-view tile map.")
            return False

        def project(point: tuple[int, int], source: Tile, destination: Tile) -> tuple[int, int] | None:
            x_probe, y_probe, x_tile_delta, y_tile_delta = calibration
            tile_x = destination.x - source.x
            tile_y = destination.y - source.y
            determinant = x_tile_delta[0] * y_tile_delta[1] - y_tile_delta[0] * x_tile_delta[1]
            if abs(determinant) < 0.001:
                return None
            x_factor = (tile_x * y_tile_delta[1] - tile_y * y_tile_delta[0]) / determinant
            y_factor = (x_tile_delta[0] * tile_y - x_tile_delta[1] * tile_x) / determinant
            return (
                round(point[0] + x_factor * x_probe[0] + y_factor * y_probe[0]),
                round(point[1] + x_factor * x_probe[1] + y_factor * y_probe[1]),
            )

        target_point = project(player_point, current, destination)
        if target_point is None or not self.__point_in_game_view(target_point, game_view):
            self.log_msg(f"Local destination could not be projected inside the game view: {target_point}.")
            return False

        self.log_msg(
            f"Local movement: {current.x},{current.y} -> "
            f"{destination.x},{destination.y} at {target_point}."
        )
        # Camera perspective and zoom can shift the initial isometric
        # estimate. Correct it from the coordinate tooltip instead of clicking
        # an unverified tile.
        verified_point = None
        point = target_point
        for attempt in range(1, 5):
            if not self.__point_in_game_view(point, game_view):
                break
            self.runtime.actions.move_to(point)
            self.wait(0.2)
            hovered = self.__read_coordinate_tooltip(point)
            if hovered is not None:
                self.log_msg(f"Local tile under cursor: ({hovered.x}, {hovered.y}, {hovered.plane}) at {point}.")
                if hovered.plane == destination.plane and hovered.distance_to(destination) <= arrival_distance:
                    verified_point = point
                    break
                point = project(point, hovered, destination)
                if point is None:
                    break
                self.log_msg(f"Correcting local tile projection (attempt {attempt + 1}) to {point}.")

        if verified_point is None:
            self.log_msg("Could not locate the destination tile in the local game-view search; stopping safely.")
            return False

        if not self.__click_walk_here():
            return False
        stopped_at = self.__wait_until_player_stops(current)
        if stopped_at is None:
            self.log_msg("Player did not produce a stable coordinate after local movement.")
            return False
        if stopped_at.distance_to(destination) <= arrival_distance:
            self.log_msg(f"Arrived at {destination_name}.")
            return True
        self.log_msg(f"Local movement stopped at {stopped_at.x},{stopped_at.y},{stopped_at.plane}.")
        return False

    def __point_over_tagged_tree(self, point: tuple[int, int]) -> bool:
        """Return whether a movement point falls inside a tagged tree area."""
        for tree in self.runtime.vision.detect_hsv("game_view", self.tree_profile):
            bounds = tree.metadata.get("screen_bounds", {})
            left = bounds.get("left", 0)
            top = bounds.get("top", 0)
            right = left + bounds.get("width", 0)
            bottom = top + bounds.get("height", 0)
            if left <= point[0] <= right and top <= point[1] <= bottom:
                return True
        return False

    def __click_walk_here(self, *, force_context: bool = False) -> bool:
        """Use the context-menu Walk here action when an object is hovered."""
        hover_text = self.mouseover_text()
        # Tooltip OCR sometimes returns punctuation such as "." over clear
        # ground.  That is not an interactable object and must not trigger a
        # right-click/context-menu search.
        has_object_name = bool(hover_text and re.search(r"[A-Za-z]{2,}", hover_text))
        if not force_context and (not has_object_name or "walk here" in hover_text.lower()):
            self.runtime.actions.click()
            return True

        reason = "tagged tree marker" if force_context else repr(hover_text)
        self.log_msg(f"Movement point is interactable ({reason}); selecting Walk here from the context menu.")
        self.runtime.actions.click(button="right")
        self.wait(0.25)
        walk_entries = ocr.find_text(
            "Walk here",
            self.win.game_view,
            ocr.BOLD_12,
            [clr.OFF_WHITE, clr.OFF_YELLOW, clr.OFF_ORANGE],
        )
        if not walk_entries:
            self.log_msg("Could not find Walk here in the context menu; movement click was cancelled safely.")
            return False
        self.runtime.actions.click_within(walk_entries[0])
        return True

    @staticmethod
    def __point_in_game_view(point: tuple[int, int], game_view) -> bool:
        return (
            game_view.left <= point[0] < game_view.left + game_view.width
            and game_view.top <= point[1] < game_view.top + game_view.height
        )

    def __park_mouse_at_game_center(self) -> None:
        """Leave the cursor on the main game canvas between movement actions."""
        game_view = self.win.game_view
        if game_view is None:
            return
        # The player is normally centered by the game camera. Keeping the
        # cursor here makes the next coordinate/adjacent-tile read immediate
        # and avoids resting it over a sidebar or chat control.
        point = (game_view.left + game_view.width // 2, game_view.top + game_view.height // 2)
        self.runtime.actions.move_to(point)

    def __calibrate_local_tile_map(self, game_view, player_point: tuple[int, int], current: Tile):
        """Derive screen-to-tile movement from two live coordinate probes."""
        # In this fixed client view, moving the cursor right increases world
        # X and moving it up increases world Y. Retry a bad OCR sample rather
        # than deriving a reversed movement map from it.
        probes = []
        # Try several nearby probe offsets. A tree, player model, or tooltip
        # placement can make one exact screen point produce bad OCR even
        # though the surrounding local map is readable.
        probe_options = (((30, 0), (45, 0), (60, 0)), ((0, -15), (0, -30), (0, -45)))
        for offsets in probe_options:
            accepted_delta = None
            accepted_offset = None
            for offset in offsets:
                point = (player_point[0] + offset[0], player_point[1] + offset[1])
                if not self.__point_in_game_view(point, game_view):
                    continue
                self.runtime.actions.move_to(point)
                self.wait(0.2)
                tile = self.__read_coordinate_tooltip(point)
                if tile is None:
                    continue
                if tile.plane != current.plane:
                    self.log_msg(f"Ignoring transient calibration plane {tile.plane}; using plane {current.plane}.")
                    tile = Tile(tile.x, tile.y, current.plane)
                delta = (tile.x - current.x, tile.y - current.y)
                valid_direction = (
                    (offset[0] and 0 < delta[0] <= 8 and abs(delta[1]) <= 2)
                    or (offset[1] and 0 < delta[1] <= 8 and abs(delta[0]) <= 2)
                )
                if valid_direction:
                    accepted_delta = delta
                    accepted_offset = offset
                    break
                self.log_msg(f"Ignoring implausible calibration probe {offset}->{delta}.")
            if accepted_delta is None:
                return None
            probes.append((accepted_offset, accepted_delta))

        x_probe, x_tile_delta = probes[0]
        y_probe, y_tile_delta = probes[1]
        determinant = x_tile_delta[0] * y_tile_delta[1] - y_tile_delta[0] * x_tile_delta[1]
        if determinant == 0:
            return None
        self.log_msg(
            "Local tile map calibrated from live coordinate probes: "
            f"{x_probe}->{x_tile_delta}, {y_probe}->{y_tile_delta}."
        )
        return x_probe, y_probe, x_tile_delta, y_tile_delta

    def __wait_until_player_stops(self, previous: Tile) -> Tile | None:
        """Wait for a stable tile, retaining the last reading for replanning."""
        # OCR takes a few seconds per reading, and longer minimap clicks can
        # legitimately keep the player moving for more than the old 12-second
        # window. Do not discard a usable last position because one tooltip
        # read was missed while the camera was moving.
        deadline = time.monotonic() + 25.0
        last = previous
        stable_reads = 0
        saw_new_position = False
        rejected_reads = 0
        while time.monotonic() < deadline:
            self.cancellation.raise_if_cancelled()
            current = self.__read_current_tile()
            if current is not None:
                if self._last_coordinate_was_rejected:
                    rejected_reads += 1
                    stable_reads = 0
                    if rejected_reads >= 4:
                        self.log_msg("Coordinate OCR remains invalid; using the last confirmed position for recovery.")
                        return last
                    continue
                rejected_reads = 0
                if current == last:
                    stable_reads += 1
                    if stable_reads >= 2:
                        self.log_msg(f"Movement stopped at {current.x},{current.y},{current.plane}.")
                        self.__park_mouse_at_game_center()
                        return current
                else:
                    last = current
                    stable_reads = 0
                    saw_new_position = True
            self.wait(0.5)
        if saw_new_position:
            self.log_msg(f"Movement did not stabilize cleanly; replanning from {last.x},{last.y},{last.plane}.")
            return last
        return None

    def __bank_inventory(self) -> bool:
        """Travel to the selected bank, deposit all, and return to the trees."""
        bank = self.runtime.bank_locations.find(self.bank_location_name)
        if bank is None:
            self.log_msg(f"Banking failed: unknown bank location {self.bank_location_name!r}.")
            return False
        if not self.__navigate_to_tile(bank.tile, f"bank {bank.name}", arrival_distance=4.0):
            return False
        if not self.__click_highlighted_banker():
            self.log_msg("Banking failed: no highlighted banker could be verified.")
            return False
        try:
            self.wait_for(
                lambda: self.__find_template_rect(self.win.game_view, self.bank_deposit_all_template, confidence=0.12) is not None,
                timeout=8.0,
                interval=0.4,
                action="bank interface",
            )
        except ActionTimeoutError:
            self.log_msg("Banking failed: bank interface did not open.")
            return False

        deposit = self.__find_template_rect(self.win.game_view, self.bank_deposit_all_template, confidence=0.12)
        if deposit is None:
            return False
        point = self.runtime.actions.click_within(deposit)
        self.log_msg(f"Depositing all inventory items at randomized point {point}.")
        self.wait(1.0)

        close = self.__find_template_rect(self.win.game_view, self.bank_close_template, confidence=0.12)
        if close is None:
            self.log_msg("Banking failed: close button was not found.")
            return False
        # Keep the randomized click inside the reliable center of the X
        # artwork. The outer crop includes the button frame, where clicks can
        # miss the close control at some client scales.
        point = self.runtime.actions.click_within(close, center_fraction=0.30)
        self.log_msg(f"Closing bank interface at randomized point {point}.")
        self.wait(0.6)
        if self.__find_template_rect(self.win.game_view, self.bank_deposit_all_template, confidence=0.12) is not None:
            # A missed click should be recoverable, but never proceed as if
            # the bank closed while its interface is still visible.
            point = self.runtime.actions.click_within(close, center_fraction=0.20)
            self.log_msg(f"Bank still open; retrying close at randomized point {point}.")
        # Let the game-view redraw before attempting to read the player. The
        # old bank close-button position can be outside the scene tooltip
        # region, and the cyan tile may take a frame to reappear.
        self.__park_mouse_at_game_center()
        self.wait(1.2)
        self._last_player_point = None
        self._last_player_tile = None
        self._last_rejected_coordinate = None
        if self.__find_template_rect(self.win.game_view, self.bank_deposit_all_template, confidence=0.12) is not None:
            self.log_msg("Banking failed: bank interface remained open after close retries.")
            return False
        return self.__navigate_to_tile(self.start_tile, "tree area")

    def __click_highlighted_banker(self) -> bool:
        """Find a marked banker and require Bank hover text before clicking."""
        bankers = self.runtime.vision.detect_hsv("game_view", self.banker_profile)
        for banker in sorted(bankers, key=lambda item: item.area, reverse=True):
            bounds = banker.metadata["screen_bounds"]
            point = (bounds["left"] + bounds["width"] // 2, bounds["top"] + bounds["height"] // 2)
            self.runtime.actions.move_to(point)
            self.wait(0.25)
            if not self.mouseover_text(contains="Bank"):
                # A dark-blue marker can also surround a Grand Exchange
                # clerk. Clicking when hover OCR is unavailable is unsafe:
                # it can open the exchange screen instead of the bank.
                self.log_msg(f"Skipping unverified banker candidate at {point}.")
                continue
            self.log_msg(f"Clicking verified highlighted banker at {point}.")
            self.runtime.actions.click()
            return True
        return False

    @staticmethod
    def __load_reference_crop(path: Path, bounds: tuple[int, int, int, int]) -> np.ndarray:
        image = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
        if image is None:
            raise FileNotFoundError(f"Missing bank reference image: {path}")
        left, top, right, bottom = bounds
        return image[top:bottom, left:right]

    @staticmethod
    def __find_template_rect(rect, template: np.ndarray, confidence: float = 0.20):
        # The control panel may be rendered at a larger scale when RuneLite's
        # sidebar is expanded.
        for scale in (0.70, 0.85, 1.0, 1.15, 1.3, 1.5, 1.7, 1.9):
            height, width = template.shape[:2]
            scaled = cv2.resize(template, (max(1, round(width * scale)), max(1, round(height * scale))), interpolation=cv2.INTER_NEAREST)
            if scaled.shape[0] <= rect.height and scaled.shape[1] <= rect.width:
                found = imagesearch.search_img_in_rect(scaled, rect, confidence)
                if found is not None:
                    return found
        return None

    def __navigate_to_tree_cluster(self) -> bool:
        """Search outward with minimap clicks until tagged trees are visible.

        A color bot cannot derive the player's world tile, so it cannot turn
        the configured world coordinates into a universal route from an
        arbitrary starting point. This visual fallback instead searches from
        the current screen position and stops as soon as the configured tree
        markers appear.
        """
        if self.runtime.vision.detect_hsv("game_view", self.tree_profile):
            self.log_msg("Tagged tree cluster is already visible.")
            return True

        minimap = self.win.minimap
        if minimap is None or minimap.width <= 0 or minimap.height <= 0:
            self.log_msg("Tree-cluster search failed: minimap was not located.")
            return False

        center_x = minimap.left + minimap.width // 2
        center_y = minimap.top + minimap.height // 2
        radius = min(minimap.width, minimap.height) // 3
        offsets = [(0, -radius), (radius, 0), (0, radius), (-radius, 0)]
        random.shuffle(offsets)

        for attempt, (dx, dy) in enumerate(offsets, start=1):
            self.cancellation.raise_if_cancelled()
            point = (center_x + dx, center_y + dy)
            self.log_msg(f"Tree-cluster search {attempt}/{len(offsets)}: walking via minimap to {point}.")
            self.runtime.actions.click_at(point)
            self.wait(3.0)
            if self.runtime.vision.detect_hsv("game_view", self.tree_profile):
                self.log_msg("Tagged tree cluster found.")
                return True

        return False

    @staticmethod
    def __find_template(rect, template: Path, confidence: float = 0.20) -> bool:
        """Find a visual template in a live screen rectangle, including scaling variants."""
        image = cv2.imread(str(template), cv2.IMREAD_UNCHANGED)
        if image is None:
            raise FileNotFoundError(f"Missing screen template: {template}")
        for scale in (0.85, 1.0, 1.15, 1.3, 1.5, 1.7):
            height, width = image.shape[:2]
            scaled = cv2.resize(image, (max(1, round(width * scale)), max(1, round(height * scale))), interpolation=cv2.INTER_NEAREST)
            if scaled.shape[0] <= rect.height and scaled.shape[1] <= rect.width and imagesearch.search_img_in_rect(scaled, rect, confidence):
                return True
        return False

    def __inventory_has_free_slot(self) -> bool:
        """Use live inventory-slot pixels to identify an available slot."""
        return any(self.__inventory_slot_looks_empty(slot) for slot in self.win.inventory_slots)

    def __inventory_occupied_slot_count(self) -> int:
        """Count every occupied slot, independent of item type or position."""
        return sum(1 for slot in self.win.inventory_slots if not self.__inventory_slot_looks_empty(slot))

    @staticmethod
    def __inventory_slot_looks_empty(slot) -> bool:
        """Best-effort empty-slot test used only before live status arrives."""
        image = slot.screenshot()
        inner = image[4:-4, 4:-4]
        hsv = cv2.cvtColor(inner, cv2.COLOR_BGR2HSV)
        bright_colored_pixels = cv2.inRange(
            hsv,
            np.array([0, 65, 75], dtype=np.uint8),
            np.array([179, 255, 255], dtype=np.uint8),
        )
        return cv2.countNonZero(bright_colored_pixels) < max(12, inner.shape[0] * inner.shape[1] // 30)

    def __inventory_is_full(self) -> bool:
        """Return true only when every inventory slot is occupied by any item."""
        slots = self.win.inventory_slots
        if not slots:
            return False
        return self.__inventory_occupied_slot_count() >= len(slots)

    def __count_visible_logs(self) -> int:
        """Count logs using live item IDs, with sprite matching as fallback.

        A log stack can change quantity without changing the number of visible
        slots, and template matching can briefly miss a newly updated slot.
        The status snapshot is authoritative when available.
        """
        return sum(1 for slot in self.win.inventory_slots if self.__find_template(slot, self.logs_sprite, confidence=0.25))

    def __run_test_script(self):
        """Exercise highlighted-tree clicks, inventory drops, and movement."""
        self.log_msg("Woodcutter test script started: highlighted trees, drops, and minimap movement.")
        start_time = time.monotonic()
        end_time = start_time + self.running_time * 60
        cycle = 0
        while time.monotonic() < end_time:
            self.cancellation.raise_if_cancelled()
            cycle += 1
            trees = self.runtime.vision.detect_hsv("game_view", self.tree_profile)
            self.runtime.record_detection(
                "tagged_tree_test",
                max((tree.confidence for tree in trees), default=None),
                metadata={"count": len(trees), "cycle": cycle},
            )
            if trees:
                zone = self.win.zones.game_view
                center = (zone.rectangle.width // 2, zone.rectangle.height // 2)
                tree = min(trees, key=lambda item: dist(item.center, center))
                point = zone.to_screen(tree.center)
                self.log_msg(f"Cycle {cycle}: clicking highlighted tree at {point}.")
                self.runtime.record_action_intent("test_chop_tree", metadata={"point": point})
                self.runtime.actions.click_at(point)
            else:
                self.log_msg(f"Cycle {cycle}: no highlighted tree found.")

            inventory_slots = [slot for slot in self.win.inventory_slots if self.__find_template(slot, self.logs_sprite, confidence=0.25)]
            self.log_msg(f"Cycle {cycle}: dropping {len(inventory_slots)} detected log slots.")
            self.runtime.actions.drop_inventory(inventory_slots)

            minimap = self.win.zones.minimap.rectangle
            center_x = minimap.left + minimap.width // 2
            center_y = minimap.top + minimap.height // 2
            for offset in ((18, 0), (0, 18), (-18, 0)):
                destination = (center_x + offset[0], center_y + offset[1])
                self.log_msg(f"Cycle {cycle}: moving via minimap to {destination}.")
                self.runtime.actions.click_at(destination)
                self.wait(0.5)
            self.wait(1.0)

    def __logout(self, msg):
        self.log_msg(msg)
        self.logout()
        self.stop()

    def __move_mouse_to_nearest_tree(self, next_nearest=False) -> tuple[int, int] | None:
        """
        Locates the nearest tree and moves the mouse to it. This code is used multiple times in this script,
        so it's been abstracted into a function.
        Args:
            next_nearest: If True, will move the mouse to the second nearest tree. If False, will move the mouse to the
                          nearest tree.
            mouseSpeed: The speed at which the mouse will move to the tree. See mouse.py for options.
        Returns:
            True if success, False otherwise.
        """
        trees = self.runtime.vision.detect_hsv("game_view", self.tree_profile)
        self.runtime.record_detection("tagged_tree", max((tree.confidence for tree in trees), default=None), metadata={"count": len(trees)})
        if not trees:
            return None
        # If we are looking for the next nearest tree, we need to make sure trees has at least 2 elements
        if next_nearest and len(trees) < 2:
            return None
        zone = self.win.zones.game_view
        center = (zone.rectangle.width // 2, zone.rectangle.height // 2)
        now = time.monotonic()
        self._unavailable_tree_points = {
            point: expires_at for point, expires_at in self._unavailable_tree_points.items() if expires_at > now
        }
        available_trees = []
        for tree in trees:
            point = zone.to_screen(tree.center)
            if all(dist(point, unavailable) > 80 for unavailable in self._unavailable_tree_points):
                available_trees.append((tree, point))
        if not available_trees:
            return None
        available_trees.sort(key=lambda item: dist(item[0].center, center))
        tree, point = available_trees[1] if next_nearest and len(available_trees) > 1 else available_trees[0]
        # Marker outlines can have thin/irregular masks; their bounding-box center
        # is a more stable point inside the marked tree than a random box point.
        self.runtime.actions.move_to(point)
        return point

    def __drop_logs(self):
        """
        Private function for dropping logs. This code is used in multiple places, so it's been abstracted.
        Since we made the `api` and `logs` variables assigned to `self`, we can access them from this function.
        """
        slots = self.runtime.snapshot().item_indices(ids.logs)
        inventory_slots = [self.win.inventory_slots[index] for index in slots if 0 <= index < len(self.win.inventory_slots)]
        self.runtime.record_action_intent("drop_logs", metadata={"count": len(inventory_slots)})
        result = self.runtime.actions.drop_inventory(inventory_slots)
        self.runtime.record_verification(
            "drop_logs", succeeded=result.succeeded, attempts=result.attempts, reason=result.reason
        )
        self.logs += len(slots)
        self.log_msg(f"Logs cut: ~{self.logs}")
        self.wait(1)
