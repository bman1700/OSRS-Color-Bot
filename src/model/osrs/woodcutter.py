import time
from math import dist

import utilities.api.item_ids as ids
import utilities.random_util as rd
from actions import RetryPolicy, interact_then_wait
from model.osrs.osrs_bot import OSRSBot
from utilities.api.status_socket import StatusSocket
from utilities.hsv_color import HSVColorProfile


class OSRSWoodcutter(OSRSBot):
    def __init__(self):
        bot_title = "Woodcutter"
        description = (
            "This bot power-chops wood. Position your character near some trees, tag them, and press Play.\nTHIS SCRIPT IS AN EXAMPLE, DO NOT USE LONGTERM."
        )
        super().__init__(bot_title=bot_title, description=description)
        self.running_time = 5
        self.take_breaks = False
        self.test_mode = True
        self.options_set = True
        self.tree_profile = HSVColorProfile.from_rgb("tagged_tree", (255, 0, 231), tolerance=(3, 40, 40), min_area=4)

    def create_options(self):
        self.options_builder.add_slider_option("running_time", "How long to run (minutes)?", 1, 500)
        self.options_builder.add_checkbox_option("take_breaks", "Take breaks?", [" "])

    def save_options(self, options: dict):
        for option in options:
            if option == "running_time":
                self.running_time = options[option]
            elif option == "take_breaks":
                self.take_breaks = options[option] != []
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
        # Setup API
        api_s = StatusSocket()
        self.attach_status_socket(api_s)

        if self.test_mode:
            self.__run_test_script()
            return

        self.log_msg("Selecting inventory...")
        self.runtime.actions.click_at(self.win.cp_tabs[3].random_point())

        self.logs = 0
        failed_searches = 0
        sensors = self.runtime.temporal_sensors()

        # Main loop
        start_time = time.time()
        end_time = self.running_time * 60
        while time.time() - start_time < end_time:
            self.cancellation.raise_if_cancelled()
            # 5% chance to take a break between tree searches
            if rd.random_chance(probability=0.05) and self.take_breaks:
                self.take_break(max_seconds=30, fancy=True)

            # 2% chance to drop logs early
            if rd.random_chance(probability=0.02):
                self.__drop_logs()

            # If inventory is full, drop logs
            if self.runtime.snapshot().inventory_full:
                self.__drop_logs()

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

            # The tagged-tree detector is the target validation. Legacy hover OCR
            # is unreliable with the scaled RuneLite client layout.
            self.wait(0.1)
            self.runtime.record_action_intent("chop_tree")
            # A successful click must produce an observable animation state.
            # Passing self.wait keeps the bounded transaction interruptible.
            result = interact_then_wait(
                self.runtime.actions.click,
                lambda: self.runtime.snapshot().player_idle is False,
                timeout=3.0,
                interval=0.2,
                retry_policy=RetryPolicy(max_attempts=2, retry_delay_seconds=0.25),
                sleep=self.wait,
            )
            self.runtime.record_verification(
                "chop_tree", succeeded=result.succeeded, attempts=result.attempts, reason=result.reason
            )
            if not result.succeeded:
                self.runtime.record_recovery("chop_tree", result.reason)
                self.wait(0.5)
                continue

            # While the player is chopping (or moving), wait for a debounced
            # return to idle. The predicate retains the old human-like mouse
            # pre-positioning behavior while temporal sensors own polling.
            probability = 0.10
            def chopping_finished(snapshot):
                nonlocal probability
                if snapshot.player_idle is True:
                    return True
                if rd.random_chance(probability):
                    self.__move_mouse_to_nearest_tree(next_nearest=True)
                    probability /= 2
                return False

            started_wait = time.monotonic()
            sensors.wait_for(
                chopping_finished,
                timeout=120.0,
                interval=1.0,
                cancellation=self.cancellation,
                action="tree chopping to finish",
            )
            sensors.wait_for_stable(
                "player_idle",
                ticks=2,
                timeout=3.0,
                interval=0.2,
                cancellation=self.cancellation,
                action="player idle debounce",
            )
            self.runtime.record_wait(
                "player_idle", time.monotonic() - started_wait, "verified"
            )

            self.update_progress((time.time() - start_time) / end_time)

        self.update_progress(1)
        self.__logout("Finished.")

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
                result = interact_then_wait(
                    lambda: self.runtime.actions.click_at(point),
                    lambda: self.runtime.snapshot().player_idle is False,
                    timeout=3.0,
                    interval=0.2,
                    retry_policy=RetryPolicy(max_attempts=2, retry_delay_seconds=0.25),
                    sleep=self.wait,
                )
                self.runtime.record_verification("test_chop_tree", succeeded=result.succeeded, attempts=result.attempts, reason=result.reason)
            else:
                self.log_msg(f"Cycle {cycle}: no highlighted tree found.")

            slots = self.runtime.snapshot().item_indices(ids.logs)
            inventory_slots = [self.win.inventory_slots[index] for index in slots if 0 <= index < len(self.win.inventory_slots)]
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
