from controller.bot_controller import BotController
from runtime.events import RuntimeEventBus
from runtime.navigation import NavigationPolicy
from utilities.windmouse import WindMouseSettings


class View:
    class FrameInfo:
        def setup(self, **_):
            pass

        def stop_keyboard_listener(self):
            pass

        def start_keyboard_listener(self):
            pass

    class OutputLog:
        def clear_log(self):
            pass

        def update_log(self, *_):
            pass

    def __init__(self):
        self.frame_info = self.FrameInfo()
        self.frame_output_log = self.OutputLog()

    def after(self, _, callback):
        callback()


class Model:
    def __init__(self):
        self.runtime = type("Runtime", (), {"events": RuntimeEventBus()})()
        self.bot_title = "Test"
        self.description = "Test model"
        self.options_set = True

    def stop(self):
        pass


def test_controller_allows_initial_empty_model_and_releases_old_subscriptions():
    controller = BotController(None, View())
    first = Model()
    second = Model()

    controller.change_model(first)
    assert len(first.runtime.events._listeners["status"]) == 1
    controller.change_model(second)

    assert first.runtime.events._listeners["status"] == []
    assert len(second.runtime.events._listeners["status"]) == 1


class ConfigurableRuntime:
    def __init__(self):
        self.events = RuntimeEventBus()
        self.input_provider = None
        self.navigation_policy = NavigationPolicy()
        self.applied_config = None

    def apply_config(self, config):
        self.applied_config = config


class ConfigurableModel:
    def __init__(self):
        self.runtime = ConfigurableRuntime()
        self.mouse = type("Mouse", (), {"windmouse_settings": WindMouseSettings()})()
        self.movement = None

    def configure_movement(self, settings):
        self.movement = settings


class LoggingView(View):
    class OutputLog(View.OutputLog):
        def __init__(self):
            self.messages = []

        def update_log(self, message, *_):
            self.messages.append(message)

    def __init__(self):
        super().__init__()
        self.frame_output_log = self.OutputLog()


def test_controller_applies_valid_runtime_controls_without_gui():
    model = ConfigurableModel()
    controller = BotController(model, LoggingView())

    assert controller.configure_windmouse(("4", "2", "10"))
    assert controller.configure_runtime(
        cadence_hz="90", max_attempts="2", retry_delay_seconds="0.1",
        telemetry_enabled=True, telemetry_capacity="64",
    )

    assert model.movement == WindMouseSettings(gravity=4.0, wind=2.0, max_step=10.0)
    assert model.runtime.applied_config.input.cadence_hz == 90.0
    assert model.runtime.applied_config.verification.max_attempts == 2
    assert model.runtime.applied_config.telemetry_enabled is True
    assert model.runtime.applied_config.telemetry_capacity == 64


def test_controller_rejects_invalid_configuration_without_applying():
    model = ConfigurableModel()
    view = LoggingView()
    controller = BotController(model, view)

    assert not controller.configure_windmouse(("0", "2", "10"))
    assert not controller.configure_runtime(
        cadence_hz="0", max_attempts="2", retry_delay_seconds="0",
        telemetry_enabled=False, telemetry_capacity="0",
    )

    assert model.movement is None
    assert model.runtime.applied_config is None
    assert view.frame_output_log.messages == [
        "Invalid WindMouse settings: gravity and max_step must be positive; wind and target_radius cannot be negative",
        "Invalid runtime settings: cadence_hz must be a positive finite number",
    ]
