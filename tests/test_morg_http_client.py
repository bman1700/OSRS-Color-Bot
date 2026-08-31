import pytest

from utilities.api.morg_http_client import MorgHTTPSocket


def test_world_position_projection_fails_closed_without_required_coordinate_data():
    with pytest.raises(NotImplementedError, match="lacks a target point"):
        MorgHTTPSocket().convert_player_position_to_pixels()
