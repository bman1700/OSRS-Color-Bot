from utilities.input import MockInputProvider
from utilities.mouse import Mouse


def test_mouse_translates_screen_coordinates_for_input_provider():
    provider = MockInputProvider()
    provider.connect()
    mouse = Mouse(provider, coordinate_origin=(100, 200))

    mouse.move_to((130, 240))
    mouse.move_rel(5, -10)
    mouse.click("right", force_delay=False)

    assert provider.events[0].name == "connect"
    moves = [event.args for event in provider.events if event.name == "move_to"]
    assert len(moves) > 2
    assert (30, 40) in moves
    assert moves[-1] == (35, 30)
    assert [(event.name, event.args) for event in provider.events[-2:]] == [
        ("mouse_down", ("right",)),
        ("mouse_up", ("right",)),
    ]
