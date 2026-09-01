from types import SimpleNamespace

from actions.game_actions import GameActions


class _Mouse:
    def __init__(self):
        self.moves = []
        self.clicks = []

    def move_to(self, point, **_kwargs):
        self.moves.append(point)

    def click(self, button="left"):
        self.clicks.append(button)


class _Rectangle:
    def __init__(self, left, top, width, height):
        self.left = left
        self.top = top
        self.width = width
        self.height = height

    def get_center(self):
        return SimpleNamespace(x=self.left + self.width // 2, y=self.top + self.height // 2)


def test_control_panel_and_inventory_actions_click_within_requested_region():
    mouse = _Mouse()
    actions = GameActions(mouse)
    tab = _Rectangle(100, 200, 40, 30)
    slot = _Rectangle(300, 400, 50, 50)
    window = SimpleNamespace(cp_tabs=[tab], inventory_slots=[slot])

    tab_point = actions.click_control_panel_tab(window, 0)
    slot_point = actions.click_inventory_slot(window, 0)

    assert 108 <= tab_point[0] <= 132
    assert 206 <= tab_point[1] <= 224
    assert 310 <= slot_point[0] <= 340
    assert 410 <= slot_point[1] <= 440
    assert mouse.moves == [tab_point, slot_point]
    assert mouse.clicks == ["left", "left"]
