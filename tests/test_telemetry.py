from collections import namedtuple

from runtime import BotRuntime, TelemetryRecorder
from utilities.mouse import Mouse
from utilities.zones import ZoneSet


Point = namedtuple("Point", "x y")


class FakeRectangle:
    left = top = 0
    width = height = 1


class FakeWindow:
    padding_top = 0

    def __init__(self):
        self.game_view = self.control_panel = self.minimap = self.chat = self.mouseover = FakeRectangle()
        self.zones = ZoneSet(self)

    def position(self):
        return Point(0, 0)

    def rectangle(self):
        return FakeRectangle()


def test_recorder_is_disabled_by_default_and_preserves_metadata_snapshot():
    recorder = TelemetryRecorder(capacity=2)
    metadata = {"confidence": 0.7}

    assert recorder.record("detection", data=metadata) is None
    recorder.set_enabled(True)
    record = recorder.record("detection", data=metadata)
    metadata["confidence"] = 0.1

    assert record is not None
    assert record.data["confidence"] == 0.7
    assert recorder.snapshot() == (record,)


def test_recorder_is_a_bounded_oldest_to_newest_replay_buffer():
    recorder = TelemetryRecorder(capacity=2, enabled=True)
    recorder.action_intent("chop", target="tree")
    recorder.wait("idle", 0.25, "verified")
    recorder.verification("chop", succeeded=True, attempts=1, reason="verified")

    records = recorder.snapshot()
    assert [record.kind for record in records] == ["wait", "verification"]
    assert [record.sequence for record in records] == [2, 3]
    assert dict(records[0].data) == {"predicate": "idle", "elapsed_seconds": 0.25, "outcome": "verified"}


def test_runtime_emits_only_enabled_telemetry_and_captures_all_mechanics():
    runtime = BotRuntime(FakeWindow(), Mouse())
    events = []
    runtime.events.subscribe("telemetry", events.append)

    assert runtime.record_action_intent("chop", target="tree") is None
    runtime.enable_telemetry(capacity=5)
    runtime.record_action_intent("chop", target="tree")
    runtime.record_detection("tree", 0.93, metadata={"zone": "game_view"})
    runtime.record_wait("player_idle", 1.2, "verified")
    runtime.record_verification("chop", succeeded=True, attempts=1, reason="verified")
    runtime.record_recovery("chop", "target_lost")

    records = runtime.telemetry.snapshot()
    assert [record.kind for record in records] == ["action_intent", "detection", "wait", "verification", "recovery"]
    assert dict(records[1].data) == {"zone": "game_view", "name": "tree", "confidence": 0.93}
    assert records[3].data["succeeded"] is True
    assert records[4].data["reason"] == "target_lost"
    assert [event.payload for event in events] == list(records)
