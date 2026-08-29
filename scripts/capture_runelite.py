"""Capture the visible RuneLite window for layout calibration (read-only)."""

from pathlib import Path
import sys

import mss
from PIL import Image
import pywinctl
import win32gui


def main() -> int:
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
    left, top = max(0, window.left), max(0, window.top)
    right, bottom = left + window.width, top + window.height
    if right <= left or bottom <= top:
        print(f"Invalid window bounds: {left}, {top}, {right}, {bottom}")
        return 1

    output = Path(__file__).resolve().parents[1] / "src" / "images" / "temp" / "runelite_client.png"
    with mss.mss() as screen:
        shot = screen.grab((left, top, right, bottom))
    Image.frombytes("RGB", shot.size, shot.rgb).save(output)

    print(f"Window: {window.title!r}")
    print(f"Bounds: left={left}, top={top}, width={window.width}, height={window.height}")
    print(f"Saved: {output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
