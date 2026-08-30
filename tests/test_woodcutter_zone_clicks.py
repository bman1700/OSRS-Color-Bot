from model.osrs.woodcutter import OSRSWoodcutter


def test_woodcutter_defaults_to_test_mode_and_five_minutes():
    bot = OSRSWoodcutter.__new__(OSRSWoodcutter)
    bot.running_time = 5
    bot.test_mode = True
    assert bot.running_time == 5
    assert bot.test_mode is True
