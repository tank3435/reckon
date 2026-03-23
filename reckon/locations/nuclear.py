"""
Nuclear target proximity calculator.

Uses a curated static dataset of high-probability US nuclear target coordinates
(ICBM silos, major command centers, population centers >500k).
Returns distance in km to the nearest target.

Sources:
  - Federation of American Scientists target analysis
  - FEMA nuclear planning zones
  - Historical SIOP target categories
"""

from dataclasses import dataclass
from math import atan2, cos, radians, sin, sqrt


@dataclass
class NuclearTarget:
    name: str
    lat: float
    lon: float
    category: str  # "silo", "command", "urban", "port"


# Curated high-confidence US targets (illustrative, not exhaustive)
KNOWN_TARGETS: list[NuclearTarget] = [
    NuclearTarget("Minot AFB (ICBM)", 48.4154, -101.3581, "silo"),
    NuclearTarget("Malmstrom AFB (ICBM)", 47.5097, -111.1838, "silo"),
    NuclearTarget("F.E. Warren AFB (ICBM)", 41.1413, -104.8212, "silo"),
    NuclearTarget("Offutt AFB (STRATCOM)", 41.1182, -95.9124, "command"),
    NuclearTarget("Cheyenne Mountain (NORAD)", 38.7444, -104.8461, "command"),
    NuclearTarget("Pentagon", 38.8719, -77.0563, "command"),
    NuclearTarget("New York City", 40.7128, -74.0060, "urban"),
    NuclearTarget("Los Angeles", 34.0522, -118.2437, "urban"),
    NuclearTarget("Chicago", 41.8781, -87.6298, "urban"),
    NuclearTarget("Washington DC", 38.9072, -77.0369, "urban"),
    NuclearTarget("San Francisco", 37.7749, -122.4194, "urban"),
    NuclearTarget("Houston", 29.7604, -95.3698, "urban"),
    NuclearTarget("Seattle", 47.6062, -122.3321, "urban"),
    NuclearTarget("Norfolk Naval Station", 36.9459, -76.3089, "port"),
    NuclearTarget("Pearl Harbor", 21.3450, -157.9779, "port"),
    NuclearTarget("Bangor Naval Base (Trident)", 47.7348, -122.6987, "port"),
    NuclearTarget("Kings Bay Naval Base (Trident)", 30.7976, -81.5565, "port"),
]


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    φ1, φ2 = radians(lat1), radians(lat2)
    Δφ = radians(lat2 - lat1)
    Δλ = radians(lon2 - lon1)
    a = sin(Δφ / 2) ** 2 + cos(φ1) * cos(φ2) * sin(Δλ / 2) ** 2
    return R * 2 * atan2(sqrt(a), sqrt(1 - a))


def nearest_nuclear_target(lat: float, lon: float) -> tuple[NuclearTarget, float] | None:
    if not KNOWN_TARGETS:
        return None
    results = [
        (t, haversine_km(lat, lon, t.lat, t.lon)) for t in KNOWN_TARGETS
    ]
    return min(results, key=lambda x: x[1])
