"""Capture the visible RuneLite window for layout calibration (read-only)."""

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from utilities.display import enable_per_monitor_dpi_awareness

# Keep window discovery and MSS capture in physical virtual-desktop pixels.
enable_per_monitor_dpi_awareness()

import mss
from PIL import Image
import pywinctl
import win32gui


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture the visible RuneLite window or one of its layout regions.")
    parser.add_argument("--output", type=Path, help="Output PNG path")
    parser.add_argument("--region", choices=("full", "game_view", "control_panel", "chat"), default="full")
    args = parser.parse_args()
    windows = [window for window in pywinctl.getAllWindows() if "runelite" in window.title.casefold()]
    if not windows:
        print("No window containing 'RuneLite' was found.")
        print("Visible windows:")

        def show_window(hwnd, _):
            title = win32gui.GetWindowText(hwnd)
            if title and win32gui.IsWindowVisible(hwnd):
                print(f"  {hwnd}: {title!r}")

        win32gui.EnumWindows(show_window, None)
        return 1

    window = windows[0]
    # MSS accepts virtual-desktop coordinates, including negative values for
    # displays arranged to the left of or above the primary monitor.  Do not
    # clamp these values: doing so captures the wrong part of the desktop.
    left, top = window.left, window.top
    right, bottom = left + window.width, top + window.height
    if right <= left or bottom <= top:
        print(f"Invalid window bounds: {left}, {top}, {right}, {bottom}")
        return 1

    output = args.output or (Path(__file__).resolve().parents[1] / "src" / "images" / "temp" / "runelite_client.png")
    with mss.mss() as screen:
        shot = screen.grab((left, top, right, bottom))
    image = Image.frombytes("RGB", shot.size, shot.rgb)
    width, height = image.size
    game_width = round(width * 0.66)
    if args.region == "game_view":
        image = image.crop((0, 30, game_width, min(height, 570)))
    elif args.region == "control_panel":
        image = image.crop((game_width, 30, width, height))
    elif args.region == "chat":
        image = image.crop((0, round(height * 0.675), game_width, height))
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output)

    print(f"Window: {window.title!r}")
    print(f"Bounds: left={left}, top={top}, width={window.width}, height={window.height}")
    print(f"Saved: {output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
