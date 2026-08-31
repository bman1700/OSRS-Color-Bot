import json

import pytest

from runtime import BankLocation, BankLocationRegistry, Tile


def test_bank_location_registry_round_trip(tmp_path):
    path = tmp_path / "banks.json"
    registry = BankLocationRegistry([BankLocation("Lumbridge", Tile(3210, 3218), "west bank")])
    registry.save(path)

    loaded = BankLocationRegistry.load(path)
    assert loaded.names() == ("Lumbridge",)
    assert loaded.get("Lumbridge").tile == Tile(3210, 3218)


def test_bank_location_registry_supports_upsert_and_lookup():
    registry = BankLocationRegistry()
    registry.upsert(BankLocation("Varrock", Tile(3185, 3436)))
    registry.upsert(BankLocation("Varrock", Tile(3186, 3436)))

    assert registry.get("Varrock").tile == Tile(3186, 3436)
    assert registry.find("missing") is None


def test_bank_location_registry_rejects_invalid_payload(tmp_path):
    path = tmp_path / "banks.json"
    path.write_text(json.dumps({"locations": [{"name": "Broken", "x": "bad", "y": 1}]}), encoding="utf-8")

    with pytest.raises(ValueError):
        BankLocationRegistry.load(path)
