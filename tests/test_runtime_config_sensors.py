from runtime import RuntimeConfig, SensorService, SensorSnapshot
from utilities.windmouse import WindMouseSettings


def test_runtime_config_round_trip(tmp_path):
    path = tmp_path / "runtime.json"
    config = RuntimeConfig(1234, "input.dll", WindMouseSettings(gravity=4.0))
    config.save(path)
    assert RuntimeConfig.load(path) == config


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
