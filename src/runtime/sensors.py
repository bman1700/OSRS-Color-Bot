"""Small, testable state-snapshot layer for script decisions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass(frozen=True)
class SensorSnapshot:
    tick: int | None = None
    run_energy: int | None = None
    hitpoints: int | None = None
    prayer_points: int | None = None
    special_energy: int | None = None
    prayer_active: bool | None = None
    active_tab: str | None = None
    chat_text: str | None = None
    minimap: dict[str, Any] = field(default_factory=dict)
    nearby_npcs: tuple[dict[str, Any], ...] = ()
    nearby_objects: tuple[dict[str, Any], ...] = ()
    inventory_count: int = 0
    inventory: tuple[dict[str, Any], ...] = ()
    equipment: tuple[dict[str, Any], ...] = ()
    player_idle: bool | None = None
    animation_id: int | None = None
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @property
    def inventory_full(self) -> bool:
        return self.inventory_count >= 28

    def item_indices(self, item_ids: int | list[int] | tuple[int, ...]) -> list[int]:
        """Return inventory slots containing one of the requested item IDs."""
        wanted = {item_ids} if isinstance(item_ids, int) else set(item_ids)
        return [item["index"] for item in self.inventory if item.get("id") in wanted and "index" in item]

    def item_stack_amount(self, item_ids: int | list[int] | tuple[int, ...]) -> int:
        """Return the stack amount for the first matching inventory item."""
        wanted = {item_ids} if isinstance(item_ids, int) else set(item_ids)
        item = next((item for item in self.inventory if item.get("id") in wanted), None)
        if item is None:
            return 0
        return int(item.get("amount", item.get("quantity", 0)))

    def item_indices_by_name(self, name: str, catalog) -> list[int]:
        """Resolve a configured item name through a catalog, then inspect IDs.

        Runtime matching remains ID-based; names are only a configuration
        convenience and unknown names safely produce no matches.
        """
        item_id = catalog.get_id(name)
        return self.item_indices(item_id) if item_id is not None else []

    def equipped_item_ids(self) -> tuple[int, ...]:
        """Return item IDs currently reported in the equipment tab."""
        return tuple(item["id"] for item in self.equipment if "id" in item)

    def has_equipped(self, item_ids: int | list[int] | tuple[int, ...]) -> bool:
        """Return whether any requested item ID is equipped."""
        wanted = {item_ids} if isinstance(item_ids, int) else set(item_ids)
        return any(item.get("id") in wanted for item in self.equipment)


class SensorService:
    """Normalize a status-socket-shaped payload without requiring a live socket."""

    def __init__(self, source: Callable[[], dict[str, Any]] | None = None) -> None:
        self.source = source

    def attach_source(self, source: Callable[[], dict[str, Any]]) -> None:
        self.source = source

    def snapshot(self, data: dict[str, Any] | None = None) -> SensorSnapshot:
        payload = dict(data if data is not None else (self.source() if self.source else {}))
        inventory = tuple(payload.get("inventory") or ())
        equipment = tuple(payload.get("equipment") or ())
        attack = payload.get("attack") or {}
        animation_id = attack.get("animationId")
        return SensorSnapshot(
            tick=payload.get("tick"),
            run_energy=payload.get("runEnergy"),
            hitpoints=payload.get("hitpoints", payload.get("hp")),
            prayer_points=payload.get("prayerPoints", payload.get("prayer")),
            special_energy=payload.get("specialEnergy", payload.get("specEnergy")),
            prayer_active=bool(payload.get("prayers")) if "prayers" in payload else None,
            active_tab=payload.get("activeTab"),
            chat_text=payload.get("chatText", payload.get("chat")),
            minimap=dict(payload.get("minimap") or {}),
            nearby_npcs=tuple(payload.get("nearbyNpcs", payload.get("npcs")) or ()),
            nearby_objects=tuple(payload.get("nearbyObjects", payload.get("objects")) or ()),
            inventory_count=len(inventory),
            inventory=inventory,
            equipment=equipment,
            player_idle=animation_id == -1 if animation_id is not None else None,
            animation_id=animation_id,
            raw=payload,
        )

    def temporal(self, *, stale_after: float | None = None):
        """Create temporal predicates over this service without changing snapshots."""
        from runtime.temporal import TemporalSensors
        return TemporalSensors(self.snapshot, stale_after=stale_after)
