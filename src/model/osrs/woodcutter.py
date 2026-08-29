import time
from math import dist

import utilities.api.item_ids as ids
import utilities.random_util as rd
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
        self.running_time = 10
        self.take_breaks = False
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

        self.log_msg("Selecting inventory...")
        self.runtime.actions.click_at(self.win.cp_tabs[3].random_point())

        self.logs = 0
        failed_searches = 0

        # Main loop
        start_time = time.time()
        end_time = self.running_time * 60
        while time.time() - start_time < end_time:
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
                time.sleep(1)
                continue
            failed_searches = 0  # If code got here, a tree was found

            # The tagged-tree detector is the target validation. Legacy hover OCR
            # is unreliable with the scaled RuneLite client layout.
            time.sleep(0.1)
            self.runtime.actions.click()
            time.sleep(0.5)

            # While the player is chopping (or moving), wait
            probability = 0.10
            while self.runtime.snapshot().player_idle is False:
                # Every second there is a chance to move the mouse to the next tree, lessen the chance as time goes on
                if rd.random_chance(probability):
                    self.__move_mouse_to_nearest_tree(next_nearest=True)
                    probability /= 2
                time.sleep(1)

            self.update_progress((time.time() - start_time) / end_time)

        self.update_progress(1)
        self.__logout("Finished.")

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
        self.drop(slots)
        self.logs += len(slots)
        self.log_msg(f"Logs cut: ~{self.logs}")
        time.sleep(1)
