import random

from runtime import RouteNode, Tile, WaypointPathProvider


def test_waypoint_provider_finds_only_configured_traversable_routes():
    nodes = [
        RouteNode(Tile(0, 0), (Tile(1, 0),)),
        RouteNode(Tile(1, 0), (Tile(0, 0), Tile(2, 0))),
        RouteNode(Tile(2, 0), (Tile(1, 0),)),
    ]

    route = WaypointPathProvider(nodes, rng=random.Random(1)).path(Tile(0, 0), Tile(2, 0))
    assert route == [Tile(0, 0), Tile(1, 0), Tile(2, 0)]
    assert WaypointPathProvider(nodes).path(Tile(0, 0), Tile(99, 99)) == ()


def test_waypoint_provider_can_choose_a_valid_alternate_route():
    start, upper, lower, target = Tile(0, 0), Tile(1, 1), Tile(1, -1), Tile(2, 0)
    nodes = [
        RouteNode(start, (upper, lower)),
        RouteNode(upper, (start, target)),
        RouteNode(lower, (start, target)),
        RouteNode(target, (upper, lower)),
    ]
    provider = WaypointPathProvider(nodes, randomness=1.0, rng=random.Random(7))
    route = provider.path(start, target)
    assert route[0] == start and route[-1] == target
    assert route in ([start, upper, target], [start, lower, target])
