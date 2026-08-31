"""Persistent, shared world locations used by bot scripts."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from runtime.navigation import Tile


@dataclass(frozen=True)
class BankLocation:
    """A named bank destination in world coordinates."""

    name: str
    tile: Tile
    notes: str = ""

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("Bank location name cannot be empty")

    def to_dict(self) -> dict:
        return {"name": self.name, "x": self.tile.x, "y": self.tile.y, "plane": self.tile.plane, "notes": self.notes}

    @classmethod
    def from_dict(cls, payload: dict, *, name: str | None = None) -> "BankLocation":
        if not isinstance(payload, dict):
            raise ValueError("Bank location must be an object")
        location_name = name or payload.get("name")
        if not isinstance(location_name, str):
            raise ValueError("Bank location name is required")
        try:
            tile = Tile(int(payload["x"]), int(payload["y"]), int(payload.get("plane", 0)))
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError(f"Invalid bank location coordinates for {location_name!r}") from error
        notes = payload.get("notes", "")
        if not isinstance(notes, str):
            raise ValueError("Bank location notes must be text")
        return cls(location_name, tile, notes)


class BankLocationRegistry:
    """Named bank locations shared by every script in a runtime."""

    def __init__(self, locations: list[BankLocation] | None = None) -> None:
        self._locations: dict[str, BankLocation] = {}
        for location in locations or []:
            self.add(location)

    def add(self, location: BankLocation) -> None:
        if location.name in self._locations:
            raise ValueError(f"Bank location already exists: {location.name}")
        self._locations[location.name] = location

    def upsert(self, location: BankLocation) -> None:
        self._locations[location.name] = location

    def get(self, name: str) -> BankLocation:
        try:
            return self._locations[name]
        except KeyError as error:
            available = ", ".join(sorted(self._locations)) or "none"
            raise KeyError(f"Unknown bank location {name!r}; available locations: {available}") from error

    def find(self, name: str) -> BankLocation | None:
        return self._locations.get(name)

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._locations))

    def remove(self, name: str) -> BankLocation:
        try:
            return self._locations.pop(name)
        except KeyError as error:
            raise KeyError(f"Unknown bank location: {name}") from error

    def save(self, path: str | Path) -> None:
        payload = {"locations": [location.to_dict() for location in self._locations.values()]}
        Path(path).write_text(json.dumps(payload, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> "BankLocationRegistry":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or not isinstance(payload.get("locations", []), list):
            raise ValueError("Bank location file must contain a locations list")
        return cls([BankLocation.from_dict(item) for item in payload["locations"]])

    @classmethod
    def from_builtin(cls) -> "BankLocationRegistry":
        path = Path(__file__).resolve().parents[2] / "bank_locations.json"
        return cls.load(path) if path.is_file() else cls()
