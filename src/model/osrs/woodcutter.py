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
from runtime import Tile
from runtime.navigation import CompassRotation, RandomizedDirectPathProvider, WindowMinimapProjector
from utilities.geometry import Rectangle
from utilities.hsv_color import HSVColorProfile


class OSRSWoodcutter(OSRSBot):
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
        # Tagged-tree outlines vary slightly with client scaling and scene
        # lighting. Keep this aligned with the known RuneLite capture range.
        self.tree_profile = HSVColorProfile.from_rgb("tagged_tree", (255, 0, 231), tolerance=(5, 50, 50), min_area=4)

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

        if not self.__navigate_to_start():
            return

        self.log_msg("Checking inventory for one free space...")
        inventory_tab = self.win.cp_tabs[3]
        self.log_msg(f"Selecting inventory tab at {inventory_tab.get_center()}.")
        self.runtime.actions.click_at(inventory_tab.random_point())
        self.wait(0.5)
        if not self.__inventory_has_free_slot():
            self.log_msg("Startup check failed: inventory has no free space.")
            return

        self.log_msg(f"Using bank location: {self.bank_location_name}.")
        self.runtime.actions.click_at(self.win.cp_tabs[3].random_point())

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

            if self.runtime.snapshot().inventory_full:
                if not self.__bank_inventory():
                    return
                continue

            # Select a fresh tagged tree each cycle; marker detection replaces the
            # old hover-text OCR check for this scaled client layout.
            if not self.__move_mouse_to_nearest_tree():
                failed_searches += 1
                if failed_searches % 10 == 0:
                    self.log_msg("Searching for trees...")
                if failed_searches > 60:
                    # If we've been searching for a whole minute...
                    self.__logout("No tagged trees found. Logging out.")
                self.wait(1)
                continue
            failed_searches = 0  # If code got here, a tree was found

            baseline_logs = self.__count_visible_logs()
            self.runtime.actions.click()
            self.runtime.record_action_intent("chop_tree")
            self.wait_for(
                lambda: self.__count_visible_logs() > baseline_logs,
                timeout=30.0,
                interval=0.5,
                action="new wood in inventory",
            )

            self.update_progress((time.time() - start_time) / end_time)

        self.update_progress(1)
        self.__logout("Finished.")

    def __startup_checks(self, *, check_inventory: bool = True) -> bool:
        """Confirm the equipped axe, optionally checking inventory space."""
        self.__refresh_window_layout("equipment check")
        self.log_msg("Checking gear tab for an equipped bronze axe...")
        # Click Test verified that the equipment tab is directly to the right
        # of Inventory in this client layout.
        equipment_tab = self.win.cp_tabs[4]
        self.log_msg(f"Selecting equipment tab at {equipment_tab.get_center()}.")
        self.runtime.actions.click_at(equipment_tab.random_point())
        self.wait(0.5)
        if not self.__find_equipped_axe():
            self.log_msg("Startup check failed: bronze axe sprite was not found in the gear tab.")
            return False
        self.log_msg("Bronze axe is equipped.")

        if check_inventory:
            self.__refresh_window_layout("inventory check")
            self.log_msg("Checking inventory for one free space...")
            inventory_tab = self.win.cp_tabs[3]
            self.log_msg(f"Selecting inventory tab at {inventory_tab.get_center()}.")
            self.runtime.actions.click_at(inventory_tab.random_point())
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
            if self.win.initialize():
                self.log_msg(f"RuneLite layout refreshed before {reason}.")
            else:
                self.log_msg(f"RuneLite layout refresh failed before {reason}.")
        except Exception as error:
            self.log_msg(f"RuneLite layout refresh error before {reason}: {error}.")

    def __read_current_tile(self) -> Tile | None:
        """Read the hovered tile coordinate from RuneLite's on-screen text."""
        game_view = self.win.game_view
        if game_view is None:
            return None
        teal_tile = self.__find_teal_tile(game_view)
        if teal_tile is None:
            self.log_msg("Current-tile check failed: teal highlighted player tile was not found.")
            return None
        self.log_msg(f"Teal current tile found at {teal_tile}; moving pointer inside it.")
        self.runtime.actions.move_to(teal_tile)
        self.wait(0.25)
        return self.__read_coordinate_tooltip(teal_tile)

    @staticmethod
    def __find_teal_tile(game_view) -> tuple[int, int] | None:
        """Return the screen center of the teal current-tile highlight."""
        image = game_view.screenshot()
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        # The current-tile outline in the supplied capture is bright teal,
        # approximately OpenCV hue 90, unlike the green destination marker.
        mask = cv2.inRange(hsv, np.array([80, 120, 120], dtype=np.uint8), np.array([105, 255, 255], dtype=np.uint8))
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        candidates = []
        for contour in contours:
            x, y, width, height = cv2.boundingRect(contour)
            if not (25 <= width <= 130 and 25 <= height <= 130):
                continue
            ratio = width / max(1, height)
            if 0.65 <= ratio <= 1.5:
                candidates.append((abs(width - height), -(width * height), x + width // 2, y + height // 2))
        if not candidates:
            return None
        _, _, x, y = min(candidates)
        return game_view.left + x, game_view.top + y

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

    def __navigate_to_start(self) -> bool:
        """Walk from the current visually-read tile to the tree area."""
        current = self.__read_current_tile()
        if current is None:
            self.log_msg("Could not read the current tile from the on-screen coordinate overlay.")
            self.log_msg("Enable RuneLite tile-coordinate text and keep the player visible before starting.")
            return False
        if current == self.start_tile:
            self.log_msg(f"Already at the tree area ({self.start_tile.x}, {self.start_tile.y}).")
            return True

        self.log_msg(
            f"Current tile: ({current.x}, {current.y}, {current.plane}); "
            f"walking to tree area ({self.start_tile.x}, {self.start_tile.y}, {self.start_tile.plane})."
        )
        provider = RandomizedDirectPathProvider(tiles_per_step=5.0, lateral_variance=2)
        projector = WindowMinimapProjector(self.win, compass=lambda: CompassRotation(), pixels_per_tile=4.0)

        for action_number in range(1, 31):
            self.cancellation.raise_if_cancelled()
            current = self.__read_current_tile()
            if current is None:
                self.log_msg("Could not reread the teal current tile; stopping navigation safely.")
                return False
            if current.distance_to(self.start_tile) <= 1.0:
                self.log_msg("Arrived at the configured tree area.")
                return True

            route = list(provider.path(current, self.start_tile))
            if len(route) < 2:
                self.log_msg("Could not create a route to the tree area.")
                return False
            horizon = min(random.randint(2, 4), len(route) - 1)
            waypoint = route[horizon]
            point = projector.project(current, waypoint)
            if point is None:
                self.log_msg("Route point is outside the minimap; stopping navigation safely.")
                return False

            self.log_msg(
                f"Movement action {action_number}: {current.x},{current.y} -> "
                f"waypoint {waypoint.x},{waypoint.y} at {point}."
            )
            self.runtime.actions.click_at(point)
            stopped_at = self.__wait_until_player_stops(current)
            if stopped_at is None:
                self.log_msg("Player did not produce a stable coordinate after movement.")
                return False

        self.log_msg("Could not reach the configured tree area within 30 single-action moves.")
        return False

    def __wait_until_player_stops(self, previous: Tile) -> Tile | None:
        """Wait for two identical teal-tile readings after one movement click."""
        deadline = time.monotonic() + 12.0
        last = previous
        stable_reads = 0
        while time.monotonic() < deadline:
            self.cancellation.raise_if_cancelled()
            current = self.__read_current_tile()
            if current is not None:
                if current == last:
                    stable_reads += 1
                    if stable_reads >= 2:
                        self.log_msg(f"Movement stopped at {current.x},{current.y},{current.plane}.")
                        return current
                else:
                    last = current
                    stable_reads = 0
            self.wait(0.5)
        return None

    def __bank_inventory(self) -> bool:
        """Walk to the configured bank and deposit the inventory."""
        self.log_msg("Screen-only bank routing is not configured for this woodcutting area yet.")
        return False

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
        """Use slot pixels to distinguish an empty inventory slot from an item."""
        for slot in self.win.inventory_slots:
            image = slot.screenshot()
            inner = image[4:-4, 4:-4]
            hsv = cv2.cvtColor(inner, cv2.COLOR_BGR2HSV)
            bright_colored_pixels = cv2.inRange(hsv, np.array([0, 65, 75], dtype=np.uint8), np.array([179, 255, 255], dtype=np.uint8))
            if cv2.countNonZero(bright_colored_pixels) < max(12, inner.shape[0] * inner.shape[1] // 30):
                return True
        return False

    def __count_visible_logs(self) -> int:
        """Count log sprites in inventory slots using screen-only template matching."""
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

    def __move_mouse_to_nearest_tree(self, next_nearest=False):
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
            return False
        # If we are looking for the next nearest tree, we need to make sure trees has at least 2 elements
        if next_nearest and len(trees) < 2:
            return False
        zone = self.win.zones.game_view
        center = (zone.rectangle.width // 2, zone.rectangle.height // 2)
        trees = sorted(trees, key=lambda tree: dist(tree.center, center))
        tree = trees[1] if next_nearest else trees[0]
        # Marker outlines can have thin/irregular masks; their bounding-box center
        # is a more stable point inside the marked tree than a random box point.
        self.runtime.actions.move_to(zone.to_screen(tree.center))
        return True

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
