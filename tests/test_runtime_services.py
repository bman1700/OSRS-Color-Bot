from collections import namedtuple

from runtime import BotRuntime
from runtime import RuntimeEventBus
from utilities.input import MockInputProvider
from utilities.mouse import Mouse
from utilities.zones import ZoneSet
from runtime.navigation import NavigationPolicy, Tile, NavigationStatus


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
    assert provider.events[0].name == "connect"
    moves = [event.args for event in provider.events if event.name == "move_to"]
    assert len(moves) > 1
    assert moves[-1] == (5, 4)
    assert [event.name for event in provider.events[-5:]] == [
        "mouse_down", "mouse_up", "mouse_down", "mouse_up", "disconnect"
    ]


def test_runtime_event_bus_delivers_events_to_subscribers():
    events = []
    bus = RuntimeEventBus()
    bus.subscribe("status", events.append)
    bus.emit("status", "running")

    assert events[0].name == "status"
    assert events[0].payload == "running"


def test_runtime_event_bus_uses_dispatcher_when_configured():
    callbacks = []
    events = []
    bus = RuntimeEventBus()
    bus.set_dispatcher(callbacks.append)
    bus.subscribe("status", events.append)
    bus.emit("status", "running")

    assert not events
    callbacks.pop()()
    assert events[0].payload == "running"


def test_runtime_exposes_injectable_navigation_without_external_provider():
    class Route:
        def path(self, start, destination):
            return [start, destination]

    window = FakeWindow()
    provider = MockInputProvider()
    runtime = BotRuntime(window, Mouse())
    runtime.set_input_provider(provider)
    runtime.attach_sensor_source(lambda: {"playerPosition": {"x": 0, "y": 0}})
    runtime.start()
    runtime.configure_navigation(Route(), policy=NavigationPolicy(
        horizon_min=1, horizon_max=1, movement_timeout_seconds=.01,
        arrival_timeout_seconds=.01, poll_interval_seconds=.01,
    ))
    # The static position source cannot observe progress, so navigation fails
    # closed after issuing at most one bounded click.
    result = runtime.walk_to(Tile(1, 0))
    runtime.stop()
    assert result.status is NavigationStatus.MOVEMENT_NOT_CONFIRMED
