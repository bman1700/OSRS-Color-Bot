from __future__ import annotations

import time

from utilities.input import InputProvider
from utilities.random_util import truncated_normal_sample
from utilities.windmouse import WindMouseSettings, generate_path


class Mouse:
    click_delay = True

    def __init__(self, input_provider: InputProvider | None = None, coordinate_origin: tuple[int, int] = (0, 0)) -> None:
        """Create a mouse action service.

        Destinations are converted from the existing screen-relative
        coordinates to client-relative coordinates and delivered through the
        configured provider. Game actions have no desktop-input fallback.
        """
        self.input_provider = input_provider
        self.coordinate_origin = coordinate_origin
        self._last_position: tuple[int, int] | None = None
        self.windmouse_settings = WindMouseSettings()

    def set_input_provider(self, input_provider: InputProvider, coordinate_origin: tuple[int, int]) -> None:
        self.input_provider = input_provider
        self.coordinate_origin = coordinate_origin
        self._last_position = None

    def set_windmouse_settings(self, settings: WindMouseSettings) -> None:
        self.windmouse_settings = settings

    def position(self) -> tuple[int, int]:
        if self.input_provider is None:
            raise RuntimeError("Mouse input provider has not been configured")
        return self._last_position or self.coordinate_origin

    def _to_client_coordinates(self, point: tuple[int, int]) -> tuple[int, int]:
        return int(point[0] - self.coordinate_origin[0]), int(point[1] - self.coordinate_origin[1])

    def move_to(self, destination: tuple, **kwargs):
        """
        Move through the configured game-client input provider.
        Args:
            destination: x, y tuple of the destination point
            destination_variance: pixel variance to add to the destination point (default 0)
        Kwargs:
            Legacy movement keywords are accepted for script compatibility but
            are not interpreted by the transport.
        """
        if self.input_provider is None:
            raise RuntimeError("Mouse input provider has not been configured")
        dest_x, dest_y = int(destination[0]), int(destination[1])
        for point in generate_path(self.position(), (dest_x, dest_y), self.windmouse_settings):
            self.input_provider.move_to(*self._to_client_coordinates(point))
        self._last_position = (dest_x, dest_y)

    def move_rel(self, x: int, y: int, x_var: int = 0, y_var: int = 0, **kwargs):
        """
        Use Bezier curve to simulate human-like relative mouse movements.
        Args:
            x: x distance to move
            y: y distance to move
            x_var: maxiumum pixel variance that may be added to the x distance (default 0)
            y_var: maxiumum pixel variance that may be added to the y distance (default 0)
        Kwargs:
            knotsCount: if right-click menus are being cancelled due to erratic mouse movements,
                        try setting this value to 0.
        """
        if x_var != 0:
            x += round(truncated_normal_sample(-x_var, x_var))
        if y_var != 0:
            y += round(truncated_normal_sample(-y_var, y_var))
        current_x, current_y = self.position()
        self.move_to((current_x + x, current_y + y), **kwargs)

    def click(self, button="left", force_delay=False, check_red_click=False) -> tuple:
        """
        Clicks on the current mouse position.
        Args:
            button: button to click (default left).
            force_delay: whether to force a delay between mouse button presses regardless of the Mouse property.
            check_red_click: whether to check if the click was red (i.e., successful action) (default False).
        Returns:
            None, unless check_red_click is True, in which case it returns a boolean indicating
            whether the click was red (i.e., successful action) or not.
        """
        mouse_pos_before = self.position()
        if self.input_provider is None:
            raise RuntimeError("Mouse input provider has not been configured")
        self.input_provider.mouse_down(button)
        mouse_pos_after = self.position()
        if force_delay or self.click_delay:
            LOWER_BOUND_CLICK = 0.03  # Milliseconds
            UPPER_BOUND_CLICK = 0.2  # Milliseconds
            AVERAGE_CLICK = 0.06  # Milliseconds
            time.sleep(truncated_normal_sample(LOWER_BOUND_CLICK, UPPER_BOUND_CLICK, AVERAGE_CLICK))
        self.input_provider.mouse_up(button)
        if check_red_click:
            return False

    def right_click(self, force_delay=False):
        """
        Right-clicks on the current mouse position. This is a wrapper for click(button="right").
        Args:
            with_delay: whether to add a random delay between mouse down and mouse up (default True).
        """
        self.click(button="right", force_delay=force_delay)

