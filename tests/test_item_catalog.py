from runtime.sensors import SensorSnapshot
from utilities.item_catalog import ItemCatalog, ItemDefinition, normalize_item_name


def test_catalog_normalizes_names_and_resolves_ids():
    catalog = ItemCatalog([ItemDefinition(1511, "Logs")])
    assert normalize_item_name("  LOGS ") == "logs"
    assert catalog.get_id("logs") == 1511
    assert catalog.get_name(1511) == "Logs"


def test_sensor_can_use_name_at_configuration_boundary():
    snapshot = SensorSnapshot(inventory=({"id": 1511, "index": 3, "amount": 2},))
    catalog = ItemCatalog([ItemDefinition(1511, "Logs")])
    assert snapshot.item_indices_by_name("Logs", catalog) == [3]

