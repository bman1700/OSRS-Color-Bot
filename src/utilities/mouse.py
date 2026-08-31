from __future__ import annotations

import time
from collections.abc import Callable

from utilities.input import InputProvider
from utilities.input_executor import InputCancellationToken, InputExecutor
from utilities.random_util import truncated_normal_sample
from utilities.windmouse import WindMouseSettings, generate_path


class Mouse:
    click_delay = True

    def __init__(
        self,
        input_provider: InputProvider | None = None,
        coordinate_origin: tuple[int, int] = (0, 0),
        input_executor: InputExecutor | None = None,
    ) -> None:
        """Create a mouse action service.

        Destinations are converted from the existing screen-relative
        coordinates to client-relative coordinates and delivered through the
        configured provider. Game actions have no desktop-input fallback.
        """
        self.input_provider = input_provider
        self.coordinate_origin = coordinate_origin
        self._last_position: tuple[int, int] | None = None
        self.windmouse_settings = WindMouseSettings()
        self.input_executor = input_executor or InputExecutor()
        self._red_click_verifier: Callable[[tuple[int, int]], bool] | None = None
        self._layout_refresh: Callable[[tuple[int, int]], tuple[int, int] | None] | None = None

    def set_input_cadence(self, cadence_hz: float) -> None:
        """Set the maximum native-command rate for subsequent mouse actions."""
        old_executor = self.input_executor
        self.input_executor = InputExecutor(cadence_hz)
        old_executor.shutdown()

    def cancel_pending_input(self) -> None:
        """Cancel queued input and cause the active delivery to stop promptly."""
        self.input_executor.cancel_pending()

    def set_input_provider(self, input_provider: InputProvider, coordinate_origin: tuple[int, int]) -> None:
        self.input_provider = input_provider
        self.coordinate_origin = coordinate_origin
        self._last_position = None

    def set_windmouse_settings(self, settings: WindMouseSettings) -> None:
        self.windmouse_settings = settings

    def set_red_click_verifier(self, verifier: Callable[[tuple[int, int]], bool] | None) -> None:
        """Set a post-click visual verifier; no verifier means fail closed."""
        self._red_click_verifier = verifier

    def set_layout_refresh(self, refresh: Callable[[tuple[int, int]], tuple[int, int] | None] | None) -> None:
        """Install a callback for layout-sensitive input destinations."""
        self._layout_refresh = refresh

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
        if self._layout_refresh is not None:
            refreshed_point = self._layout_refresh((dest_x, dest_y))
            if refreshed_point is not None:
                dest_x, dest_y = refreshed_point
        cancellation = kwargs.pop("cancellation", None)
        path = generate_path(self.position(), (dest_x, dest_y), self.windmouse_settings)

        def deliver(session) -> None:
            for point in path:
                session.call(self.input_provider.move_to, *self._to_client_coordinates(point))

        self.input_executor.execute(deliver, cancellation)
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

    def click(self, button="left", force_delay=False, check_red_click=False, cancellation: InputCancellationToken | None = None) -> tuple:
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
        if self._layout_refresh is not None:
            self._layout_refresh(mouse_pos_before)
        def deliver(session) -> None:
            session.call(self.input_provider.mouse_down, button)
            if force_delay or self.click_delay:
                LOWER_BOUND_CLICK = 0.03
                UPPER_BOUND_CLICK = 0.2
                AVERAGE_CLICK = 0.06
                time.sleep(truncated_normal_sample(LOWER_BOUND_CLICK, UPPER_BOUND_CLICK, AVERAGE_CLICK))
            session.call(self.input_provider.mouse_up, button)

        self.input_executor.execute(deliver, cancellation)
        if check_red_click:
            return bool(self._red_click_verifier and self._red_click_verifier(mouse_pos_before))

    def right_click(self, force_delay=False):
        """
        Right-clicks on the current mouse position. This is a wrapper for click(button="right").
        Args:
            with_delay: whether to add a random delay between mouse down and mouse up (default True).
        """
        self.click(button="right", force_delay=force_delay)

