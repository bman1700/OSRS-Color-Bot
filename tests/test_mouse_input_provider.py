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


def test_mouse_translates_negative_virtual_desktop_coordinates_for_input_provider():
    provider = MockInputProvider()
    provider.connect()
    mouse = Mouse(provider, coordinate_origin=(-1920, 120))

    mouse.move_to((-1800, 180))

    moves = [event.args for event in provider.events if event.name == "move_to"]
    assert moves[-1] == (120, 60)


def test_mouse_red_click_check_uses_configured_fail_closed_verifier():
    provider = MockInputProvider()
    provider.connect()
    mouse = Mouse(provider, coordinate_origin=(100, 200))
    mouse.move_to((130, 240))
    mouse.set_red_click_verifier(lambda point: point == (130, 240))

    assert mouse.click(check_red_click=True) is True

    mouse.set_red_click_verifier(None)
    assert mouse.click(check_red_click=True) is False
