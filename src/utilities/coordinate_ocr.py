"""OCR helpers for RuneLite's on-screen tile-coordinate tooltip."""

from __future__ import annotations

import re

import cv2
import numpy as np

try:
    import pytesseract
except ImportError:  # pragma: no cover - depends on optional local install
    pytesseract = None

if pytesseract is not None:
    # Winget installs the maintained Windows build here, but it may not update
    # the PATH inherited by an already-open terminal or the bot UI.
    _WINDOWS_TESSERACT = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    if __import__("pathlib").Path(_WINDOWS_TESSERACT).is_file():
        pytesseract.pytesseract.tesseract_cmd = _WINDOWS_TESSERACT


def read_tile_coordinates(image: np.ndarray) -> tuple[int, int, int] | None:
    """Read ``x, y, plane`` from a tooltip image using Tesseract."""
    if pytesseract is None or image is None or image.size == 0:
        return None

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    gray = cv2.resize(gray, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
    variants = [
        cv2.threshold(gray, 135, 255, cv2.THRESH_BINARY)[1],
        cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1],
    ]
    for threshold in variants:
        threshold = cv2.medianBlur(threshold, 3)
        for psm in (7, 6, 11):
            config = f"--psm {psm} -c tessedit_char_whitelist=0123456789,()"
            try:
                text = pytesseract.image_to_string(threshold, config=config)
            except (OSError, RuntimeError, pytesseract.TesseractNotFoundError):
                return None
            values = [int(value) for value in re.findall(r"\d+", text)]
            if len(values) < 2:
                continue
            x, y = values[0], values[1]
            plane = values[2] if len(values) > 2 and values[2] <= 3 else 0
            if 1000 <= x <= 5000 and 1000 <= y <= 5000:
                return x, y, plane
    return None


def is_available() -> bool:
    """Return whether the Python bridge and Tesseract executable are usable."""
    if pytesseract is None:
        return False
    try:
        pytesseract.get_tesseract_version()
    except (OSError, RuntimeError, pytesseract.TesseractNotFoundError):
        return False
    return True
