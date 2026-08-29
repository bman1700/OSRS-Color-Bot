from utilities.input import MockInputProvider
from utilities.mouse import Mouse


def test_mouse_translates_screen_coordinates_for_input_provider():
    provider = MockInputProvider()
    provider.connect()
    mouse = Mouse(provider, coordinate_origin=(100, 200))

    mouse.move_to((130, 240))
    mouse.move_rel(5, -10)
    mouse.click("right", force_delay=False)

    assert [(event.name, event.args) for event in provider.events] == [
        ("connect", ()),
        ("move_to", (30, 40)),
        ("move_to", (35, 30)),
        ("mouse_down", ("right",)),
        ("mouse_up", ("right",)),
    ]
