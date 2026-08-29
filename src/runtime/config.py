"""Typed, JSON-backed configuration for runtime services."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from utilities.windmouse import WindMouseSettings


@dataclass
class RuntimeConfig:
    process_id: int | None = None
    dll_path: str | None = None
    windmouse: WindMouseSettings = WindMouseSettings()

    def __post_init__(self) -> None:
        if self.process_id is not None and self.process_id <= 0:
            raise ValueError("process_id must be positive")

    def save(self, path: str | Path) -> None:
        payload = asdict(self)
        Path(path).write_text(json.dumps(payload, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> "RuntimeConfig":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        windmouse = WindMouseSettings(**payload.pop("windmouse", {}))
        return cls(windmouse=windmouse, **payload)
