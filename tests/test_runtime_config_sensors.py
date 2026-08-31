import json

import pytest

from runtime import BotRuntime, RuntimeConfig, SensorService, SensorSnapshot
from runtime.config import InputSettings, SessionSettings, VerificationSettings
from runtime.navigation import NavigationPolicy
from runtime.session import SessionBudget
from utilities.mouse import Mouse
from utilities.windmouse import WindMouseSettings


class ConfigWindow:
    zones = object()


def test_runtime_config_round_trip(tmp_path):
    path = tmp_path / "runtime.json"
    config = RuntimeConfig(1234, "input.dll", WindMouseSettings(gravity=4.0))
    config.save(path)
    assert RuntimeConfig.load(path) == config


@pytest.mark.parametrize("payload", [
    {"windmouse": {"max_step": 0}},
    {"input": {"cadence_hz": float("inf")}},
    {"verification": {"max_attempts": 1.5}},
    {"verification": {"retry_delay_seconds": float("nan")}},
    {"telemetry_capacity": 1.5},
    {"telemetry_enabled": "yes"},
    {"process_id": True},
])
def test_runtime_config_load_rejects_invalid_typed_values(tmp_path, payload):
    path = tmp_path / "runtime.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError):
        RuntimeConfig.load(path)


def test_runtime_load_config_reports_malformed_json_without_applying(tmp_path):
    path = tmp_path / "runtime.json"
    path.write_text("{not valid json", encoding="utf-8")
    runtime = BotRuntime(ConfigWindow(), Mouse())
    errors = []
    runtime.events.subscribe("config_error", lambda event: errors.append(event.payload))

    assert runtime.load_config(path) is None
    assert errors == [f"Unable to load runtime configuration: {path}"]


def test_runtime_apply_config_updates_all_runtime_services():
    runtime = BotRuntime(ConfigWindow(), Mouse())
    config = RuntimeConfig(
        windmouse=WindMouseSettings(gravity=4.0, wind=1.0, max_step=8.0),
        input=InputSettings(120.0),
        verification=VerificationSettings(max_attempts=3, retry_delay_seconds=0.25),
        navigation=NavigationPolicy(horizon_min=2, horizon_max=4),
        session=SessionSettings(enabled=True, budget=SessionBudget(max_session_seconds=30.0)),
        telemetry_enabled=True,
        telemetry_capacity=8,
    )

    runtime.apply_config(config)

    assert runtime.mouse.windmouse_settings == config.windmouse
    assert runtime.mouse.input_executor.cadence_hz == 120.0
    assert runtime.verification_policy == config.verification.as_policy()
    assert runtime.navigation_policy == config.navigation
    assert runtime.session_planner.budget == config.session.budget
    assert runtime.telemetry.enabled and runtime.telemetry.capacity == 8


def test_sensor_snapshot_normalizes_status_payload():
    snapshot = SensorService().snapshot({
        "tick": 12,
        "runEnergy": 87,
        "hitpoints": 42,
        "prayerPoints": 15,
        "specialEnergy": 100,
        "activeTab": "INVENTORY",
        "chatText": "Welcome",
        "minimap": {"x": 10, "y": 20},
        "npcs": [{"name": "Goblin"}],
        "objects": [{"name": "Tree"}],
        "prayers": ["PROTECT_ITEM"],
        "inventory": [{"index": 0, "id": 1511}],
        "equipment": [{"slot": 3, "id": 1351}],
        "attack": {"animationId": -1},
    })

    assert isinstance(snapshot, SensorSnapshot)
    assert snapshot.inventory_count == 1
    assert snapshot.hitpoints == 42
    assert snapshot.prayer_points == 15
    assert snapshot.special_energy == 100
    assert snapshot.active_tab == "INVENTORY"
    assert snapshot.chat_text == "Welcome"
    assert snapshot.minimap["x"] == 10
    assert snapshot.nearby_npcs[0]["name"] == "Goblin"
    assert snapshot.nearby_objects[0]["name"] == "Tree"
    assert not snapshot.inventory_full
    assert snapshot.player_idle
    assert snapshot.prayer_active
    assert snapshot.has_equipped(1351)
    assert snapshot.equipped_item_ids() == (1351,)


def test_sensor_snapshot_supports_inventory_queries():
    snapshot = SensorService().snapshot({
        "inventory": [
            {"index": 2, "id": 100, "amount": 3},
            {"index": 7, "id": 200, "quantity": 9},
            {"index": 12, "id": 100, "amount": 4},
        ]
    })

    assert snapshot.item_indices(100) == [2, 12]
    assert snapshot.item_indices([100, 200]) == [2, 7, 12]
    assert snapshot.item_stack_amount(200) == 9
    assert snapshot.item_stack_amount(999) == 0
