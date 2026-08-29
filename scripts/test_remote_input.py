"""Safely verify a RemoteInput connection to a running RuneLite Java process.

This diagnostic only moves the virtual client pointer. It does not click or
send keyboard input.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from utilities.input import InputProviderError, RemoteInputProvider


def main() -> int:
    parser = argparse.ArgumentParser(description="Test the native RemoteInput DLL against a RuneLite Java PID.")
    parser.add_argument("process_id", type=int, help="RuneLite Java process ID")
    parser.add_argument("--x", type=int, default=300, help="Canvas-relative test X coordinate")
    parser.add_argument("--y", type=int, default=250, help="Canvas-relative test Y coordinate")
    args = parser.parse_args()

    provider = RemoteInputProvider(process_id=args.process_id)
    try:
        provider.connect()
        print(f"Connected: {provider.is_connected()}")
        print(f"Healthy: {provider.health_check()}")
        provider.move_to(args.x, args.y)
        print(f"Moved virtual pointer to ({args.x}, {args.y}).")
        return 0
    except InputProviderError as error:
        print(f"RemoteInput failed: {error}", file=sys.stderr)
        return 1
    finally:
        provider.disconnect()


if __name__ == "__main__":
    raise SystemExit(main())
