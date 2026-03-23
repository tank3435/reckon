from reckon.locations.nuclear import nearest_nuclear_target, haversine_km


def test_haversine_same_point():
    assert haversine_km(40.0, -74.0, 40.0, -74.0) == 0.0


def test_haversine_known_distance():
    # NYC to LA is roughly 3940 km
    dist = haversine_km(40.7128, -74.0060, 34.0522, -118.2437)
    assert 3900 < dist < 4000


def test_nearest_target_returns_result():
    # From Denver — nearest should be something in the West
    result = nearest_nuclear_target(39.7392, -104.9903)
    assert result is not None
    target, dist_km = result
    assert dist_km > 0
    assert target.name


def test_nearest_target_dc():
    # From DC itself — distance to Pentagon should be very small
    result = nearest_nuclear_target(38.8719, -77.0563)
    assert result is not None
    target, dist_km = result
    assert dist_km < 5.0
