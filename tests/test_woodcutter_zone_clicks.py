from model.osrs.woodcutter import OSRSWoodcutter


def test_woodcutter_defaults_to_live_mode_and_ge_bank():
    bot = OSRSWoodcutter()
    assert bot.running_time == 10
    assert bot.test_mode is False
    assert bot.start_tile.x == 3158
    assert bot.start_tile.y == 3459
    assert bot.bank_location_name == "GE West Side"
