from collections import namedtuple

from runtime import BotRuntime
from utilities.input import MockInputProvider
from utilities.mouse import Mouse
from utilities.zones import ZoneSet


Point = namedtuple("Point", "x y")


class FakeRectangle:
    left = 10
    top = 20
    width = 100
    height = 80

    def screenshot(self):
        import numpy as np

        return np.zeros((self.height, self.width, 3), dtype=np.uint8)


class FakeWindow:
    padding_top = 26

    def __init__(self):
        self.game_view = self.control_panel = self.minimap = self.chat = self.mouseover = FakeRectangle()
        self.zones = ZoneSet(self)
        self.focused = False
        self.initialized = False

    def focus(self):
        self.focused = True

    def initialize(self):
        self.initialized = True

    def position(self):
        return Point(10, 20)

    def rectangle(self):
        return FakeRectangle()


def test_runtime_wires_client_input_and_actions():
    window = FakeWindow()
    provider = MockInputProvider()
    runtime = BotRuntime(window, Mouse())
    runtime.set_input_provider(provider)

    runtime.start()
    runtime.actions.click_at((15, 50))
    runtime.actions.click()
    runtime.stop()

    assert window.focused and window.initialized
    assert [(event.name, event.args) for event in provider.events] == [
        ("connect", ()),
        ("move_to", (5, 4)),
        ("mouse_down", ("left",)),
        ("mouse_up", ("left",)),
        ("mouse_down", ("left",)),
        ("mouse_up", ("left",)),
        ("disconnect", ()),
    ]
