from controller.bot_controller import BotController
from runtime.events import RuntimeEventBus


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
