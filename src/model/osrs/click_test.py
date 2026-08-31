"""Screen-only RuneLite tab and inventory click diagnostic."""

from model.osrs.osrs_bot import OSRSBot


class OSRSClickTest(OSRSBot):
    """Validate the refreshed layout and exercise every visible UI target."""

    def __init__(self):
        super().__init__(
            bot_title="Click Test",
            description="Clicks each visible control-panel tab, returns to Inventory, then clicks every inventory slot.",
        )
        self.options_set = True

    def create_options(self):
        pass

    def save_options(self, options: dict):
        if options:
            self.log_msg(f"Click Test ignores options: {', '.join(options)}")
        self.options_set = True

    def main_loop(self):
        try:
            zones = {
                "game view": self.win.game_view,
                "control panel": self.win.control_panel,
                "minimap": self.win.minimap,
                "chat": self.win.chat,
            }
            missing = [name for name, zone in zones.items() if zone is None or zone.width <= 0 or zone.height <= 0]
            if missing or len(self.win.cp_tabs) < 7 or len(self.win.inventory_slots) < 28:
                missing.extend(("control-panel tabs" if len(self.win.cp_tabs) < 7 else "", "inventory slots" if len(self.win.inventory_slots) < 28 else ""))
                missing = [item for item in missing if item]
                self.log_msg(f"Click Test failed zone validation: {', '.join(missing)}.")
                return

            self.log_msg("Click Test: all screen zones are available.")
            visible_tabs = self.win.cp_tabs[:7]
            for index, tab in enumerate(visible_tabs, start=1):
                self.cancellation.raise_if_cancelled()
                self.log_msg(f"Click Test: clicking tab {index}/7 at {tab.get_center()}.")
                self.runtime.actions.click_at(tab.random_point())
                self.wait(0.35)

            inventory_tab = self.win.cp_tabs[3]
            self.log_msg(f"Click Test: returning to Inventory at {inventory_tab.get_center()}.")
            self.runtime.actions.click_at(inventory_tab.random_point())
            self.wait(0.5)

            for index, slot in enumerate(self.win.inventory_slots[:28], start=1):
                self.cancellation.raise_if_cancelled()
                self.log_msg(f"Click Test: clicking inventory slot {index}/28 at {slot.get_center()}.")
                self.runtime.actions.click_at(slot.random_point())
                self.wait(0.12)

            self.log_msg("Click Test finished successfully.")
        finally:
            self.stop()
