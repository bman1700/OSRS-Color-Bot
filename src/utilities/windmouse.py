"""Transport-independent WindMouse path generation."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class WindMouseSettings:
    gravity: float = 9.0
    wind: float = 3.0
    max_step: float = 12.0
    target_radius: float = 3.0
    max_points: int = 500


def generate_path(start: tuple[int, int], target: tuple[int, int], settings: WindMouseSettings = WindMouseSettings(), rng: random.Random | None = None) -> list[tuple[int, int]]:
    """Generate a bounded, integer-coordinate path from ``start`` to ``target``.

    This function performs no I/O. The caller owns timing and sends the returned
    points through an input provider.
    """
    if settings.max_step <= 0 or settings.max_points <= 0:
        raise ValueError("max_step and max_points must be positive")
    if start == target:
        return [target]

    rng = rng or random.Random()
    x, y = map(float, start)
    tx, ty = target
    vx = vy = wx = wy = 0.0
    points: list[tuple[int, int]] = []

    for _ in range(settings.max_points):
        dx, dy = tx - x, ty - y
        distance = math.hypot(dx, dy)
        if distance <= settings.target_radius:
            break

        wind_scale = min(settings.wind, distance) / math.sqrt(3)
        wx = wx / math.sqrt(3) + rng.uniform(-wind_scale, wind_scale)
        wy = wy / math.sqrt(3) + rng.uniform(-wind_scale, wind_scale)
        vx += wx + settings.gravity * dx / distance
        vy += wy + settings.gravity * dy / distance

        speed = math.hypot(vx, vy)
        if speed > settings.max_step:
            scale = rng.uniform(settings.max_step / 2, settings.max_step) / speed
            vx *= scale
            vy *= scale
        x += vx
        y += vy
        point = (round(x), round(y))
        if not points or point != points[-1]:
            points.append(point)

    if not points or points[-1] != target:
        points.append(target)
    return points
