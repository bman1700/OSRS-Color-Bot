import random

from utilities.windmouse import WindMouseSettings, generate_path
from utilities.input import MockInputProvider
from utilities.mouse import Mouse


def test_windmouse_reaches_target_with_bounded_path():
    path = generate_path((0, 0), (100, 50), WindMouseSettings(max_points=100), random.Random(7))

    assert path[-1] == (100, 50)
    assert 1 < len(path) <= 101


def test_windmouse_returns_target_for_zero_distance():
    assert generate_path((4, 8), (4, 8)) == [(4, 8)]


def test_mouse_delivers_windmouse_path_to_provider():
    provider = MockInputProvider()
    provider.connect()
    mouse = Mouse(provider, coordinate_origin=(0, 0))
    mouse.set_movement_strategy("windmouse")
    mouse.windmouse_settings = WindMouseSettings(max_points=100)

    mouse.move_to((30, 20))

    moves = [event for event in provider.events if event.name == "move_to"]
    assert len(moves) > 1
    assert moves[-1].args == (30, 20)
