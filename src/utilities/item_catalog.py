"""Item name/ID catalog used at the script boundary.

RuneLite's status socket reports item IDs, not human-readable names.  This
module provides a small, persistent catalog so scripts can be configured with
names while retaining ID-based runtime decisions.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


def normalize_item_name(name: str) -> str:
    """Normalize Wiki/user names for case- and punctuation-insensitive lookup."""
    return re.sub(r"[^a-z0-9]+", " ", str(name).casefold()).strip()


@dataclass(frozen=True)
class ItemDefinition:
    id: int
    name: str
    icon: str | None = None


class ItemCatalog:
    def __init__(self, items: Iterable[ItemDefinition] = ()) -> None:
        self._by_id: dict[int, ItemDefinition] = {}
        self._by_name: dict[str, ItemDefinition] = {}
        for item in items:
            self.add(item)

    def add(self, item: ItemDefinition) -> None:
        self._by_id[int(item.id)] = item
        self._by_name.setdefault(normalize_item_name(item.name), item)

    def get_id(self, name: str) -> int | None:
        item = self._by_name.get(normalize_item_name(name))
        return item.id if item else None

    def get_name(self, item_id: int) -> str | None:
        item = self._by_id.get(int(item_id))
        return item.name if item else None

    def get(self, item_id: int) -> ItemDefinition | None:
        return self._by_id.get(int(item_id))

    def require_id(self, name: str) -> int:
        item_id = self.get_id(name)
        if item_id is None:
            raise KeyError(f"Unknown item: {name}")
        return item_id

    def __len__(self) -> int:
        return len(self._by_id)

    @classmethod
    def from_builtin_ids(cls) -> "ItemCatalog":
        """Build a catalog from the checked-in RuneLite item ID constants."""
        from utilities.api import item_ids

        items = (
            ItemDefinition(value, key.replace("_", " ").title())
            for key, value in vars(item_ids).items()
            if key.isupper() and isinstance(value, int)
        )
        return cls(items)

    @classmethod
    def from_file(cls, path: str | Path) -> "ItemCatalog":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(ItemDefinition(int(row["id"]), row["name"], row.get("icon")) for row in data)

    def to_file(self, path: str | Path) -> Path:
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        rows = [asdict(self._by_id[item_id]) for item_id in sorted(self._by_id)]
        destination.write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return destination

    @classmethod
    def from_wiki_mapping(cls, mapping: Iterable[dict]) -> "ItemCatalog":
        return cls(
            ItemDefinition(int(row["id"]), str(row["name"]), row.get("icon"))
            for row in mapping
            if row.get("id") is not None and row.get("name")
        )

