"""Smoke-test RemoteInput configuration for every registered OSRS script.

This intentionally does not start a bot loop or send clicks/keypresses. With a
PID it only verifies that each script can be constructed and that the shared
RemoteInput provider can connect and pass its health check.
"""

from __future__ import annotations

import argparse
import inspect
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import model
from model import Bot, RuneLiteBot
from utilities.input import MockInputProvider, RemoteInputProvider


def osrs_script_classes() -> list[type[Bot]]:
    return sorted(
        [
            value
            for _, value in inspect.getmembers(model, inspect.isclass)
            if issubclass(value, Bot)
            and value not in {Bot, RuneLiteBot}
            and value.__module__.startswith("model.osrs")
        ],
        key=lambda value: value.__name__,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pid", type=int, help="RuneLite Java PID for a live connection/health check")
    parser.add_argument("--dll", default=None, help="Optional RemoteInput DLL path")
    args = parser.parse_args()

    scripts = osrs_script_classes()
    if not scripts:
        parser.error("No OSRS scripts were found")

    for script_class in scripts:
        script = script_class()
        if args.pid is None:
            script.set_input_provider(MockInputProvider())
            print(f"PASS {script_class.__name__}: constructed with mock input")
            continue

        provider = RemoteInputProvider(process_id=args.pid, dll_path=args.dll)
        script.set_input_provider(provider)
        try:
            provider.connect()
            if not provider.health_check():
                raise RuntimeError("health check failed")
            print(f"PASS {script_class.__name__}: RemoteInput connected and healthy")
        except Exception as error:
            print(f"FAIL {script_class.__name__}: {error}")
            return 1
        finally:
            provider.disconnect()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
