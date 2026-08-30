"""
Serves as the mediator between a bot and the UI. Methods should likely not be modified.
"""

from model.bot import Bot, BotStatus
from view.bot_view import BotView
from utilities.windmouse import WindMouseSettings
from runtime.config import InputSettings, RuntimeConfig, SessionSettings, VerificationSettings


class BotController(object):
    def __init__(self, model, view):
        """
        Constructor.
        """
        self.model: Bot = model
        self.view: BotView = view
        self._subscriptions = []
        self._subscribe_runtime()

    def _subscribe_runtime(self):
        if self.model is None:
            return
        self.model.runtime.events.set_dispatcher(lambda callback: self.view.after(0, callback))
        self._subscriptions = [
            self.model.runtime.events.subscribe("status", lambda event: self.update_status(event.payload)),
            self.model.runtime.events.subscribe("progress", lambda event: self.update_progress(event.payload)),
            self.model.runtime.events.subscribe("log", lambda event: self.update_log(*event.payload)),
            self.model.runtime.events.subscribe("clear_log", lambda event: self.clear_log()),
            self.model.runtime.events.subscribe("input_health", lambda event: self.update_log("RemoteInput health check passed.")),
            self.model.runtime.events.subscribe("config_error", lambda event: self.update_log(event.payload)),
            self.model.runtime.events.subscribe("client_initialized", lambda event: self.update_log(f"RuneLite client initialized at {event.payload}.")),
        ]

    def _unsubscribe_runtime(self):
        for unsubscribe in self._subscriptions:
            unsubscribe()
        self._subscriptions = []

    def play(self):
        """
        Play/pause btn clicked on view.
        """
        self.model.play()

    def configure_remote_input(self, process_id: str, dll_path: str = "") -> bool:
        """Validate and apply the Java PID selected in the UI."""
        try:
            pid = int(process_id)
            if pid <= 0:
                raise ValueError
        except (TypeError, ValueError):
            self.update_log("Enter a valid RuneLite Java process ID before starting.")
            return False
        self.model.configure_remote_input(pid, dll_path.strip() or None)
        return True

    def save_runtime_config(self) -> None:
        self.model.runtime.save_config()

    def configure_windmouse(self, values: tuple[str, str, str]) -> bool:
        try:
            movement = WindMouseSettings(gravity=float(values[0]), wind=float(values[1]), max_step=float(values[2]))
            self.model.configure_movement(movement)
            return True
        except (TypeError, ValueError) as error:
            self.update_log(f"Invalid WindMouse settings: {error}")
            return False

    def configure_runtime(self, *, cadence_hz: str, max_attempts: str,
                          retry_delay_seconds: str, telemetry_enabled: bool,
                          telemetry_capacity: str = "512") -> bool:
        """Apply advanced runtime controls collected by the settings view."""
        try:
            config = RuntimeConfig(
                process_id=getattr(self.model.runtime.input_provider, "process_id", None),
                dll_path=str(getattr(self.model.runtime.input_provider, "dll_path", "")) or None,
                windmouse=self.model.mouse.windmouse_settings,
                input=InputSettings(float(cadence_hz)),
                verification=VerificationSettings(int(max_attempts), float(retry_delay_seconds)),
                navigation=self.model.runtime.navigation_policy,
                session=SessionSettings(),
                telemetry_enabled=bool(telemetry_enabled),
                telemetry_capacity=int(telemetry_capacity),
            )
            self.model.runtime.apply_config(config)
            return True
        except (TypeError, ValueError) as error:
            self.update_log(f"Invalid runtime settings: {error}")
            return False

    def stop(self):
        """
        Stop btn clicked on view.
        """
        self.model.stop()

    def get_options_view(self, parent):
        """
        Called from view. Fetches the options view from the model.
        """
        self.model.set_status(BotStatus.CONFIGURING)
        return self.model.get_options_view(parent)

    def save_options(self, options):
        """
        Called from view. Tells model to save options.
        """
        self.model.save_options(options)
        if self.model.options_set:
            self.model.set_status(BotStatus.CONFIGURED)
        else:
            self.model.set_status(BotStatus.STOPPED)

    def abort_options(self):
        """
        Called from view when options window is closed manually.
        """
        self.update_log("Bot configuration aborted.")
        self.model.set_status(BotStatus.STOPPED)

    def launch_game(self):
        """
        Called from view. Tells model to launch game.
        """
        self.model.launch_game()

    def update_status(self, status=None):
        """
        Called from model. Tells view to update status.
        """
        status = self.model.status if status is None else status
        if status == BotStatus.RUNNING:
            self.view.frame_info.update_status_running()
        elif status in (BotStatus.STOPPED, BotStatus.FAILED_SAFE):
            self.view.frame_info.update_status_stopped()
        elif status == BotStatus.CONFIGURING:
            self.view.frame_info.update_status_configuring()
        elif status == BotStatus.CONFIGURED:
            self.view.frame_info.update_status_configured()

    def update_progress(self, progress=None):
        """
        Called from model. Tells view to update progress.
        """
        self.view.frame_info.update_progress(self.model.progress if progress is None else progress)

    def update_log(self, msg: str, overwrite: bool = False):
        """
        Called from model. Tells view to update log.
        """
        self.view.frame_output_log.update_log(msg, overwrite)

    def clear_log(self):
        """
        Called from model. Tells view to clear log.
        """
        self.view.frame_output_log.clear_log()

    def change_model(self, model: Bot):
        """
        Called from view. Swaps the controller's model, halting the old one. Reconfigures the info frame.
        Args:
            model: The new model to use.
        """
        if self.model is not None:
            self.view.frame_info.stop_keyboard_listener()
            try:
                self.model.stop()
            except AttributeError:
                print("Could not stop bot thread when changing views as it was not running. This is normal.")
            self.model.options_set = False
        self._unsubscribe_runtime()
        self.model = model
        if self.model is not None:
            self._subscribe_runtime()
            self.view.frame_info.setup(title=model.bot_title, description=model.description)
            self.view.frame_info.start_keyboard_listener()
        else:
            self.view.frame_info.setup(title="", description="")
        self.clear_log()


class MockBotController(object):
    def __init__(self, model):
        """
        A mock controller for testing purposes. Allows you to run a bot without a UI.
        """
        self.model: Bot = model

    def update_status(self):
        """
        Called from model. Tells view to update status
        """
        print(f"Status: {self.model.status}")

    def update_progress(self):
        """
        Called from model. Tells view to update progress.
        """
        print(f"Progress: {int(self.model.progress * 100)}%")

    def update_log(self, msg: str, overwrite: bool = False):
        """
        Called from model. Tells view to update log.
        """
        print(f"Log: {msg}")

    def clear_log(self):
        """
        Called from model. Tells view to clear log.
        """
        print("--- Clearing log ---")
