"""
Survival resource finder.

Uses Overpass API (OpenStreetMap) to find nearby:
  - Freshwater sources (rivers, lakes, springs)
  - Hospitals
  - Emergency shelters

Nuclear target proximity is handled separately in nuclear.py.
"""

import asyncio
from dataclasses import dataclass

import httpx

from reckon.locations.nuclear import haversine_km

OVERPASS_URL = "https://overpass-api.de/api/interpreter"


@dataclass
class ResourceResult:
    resource_type: str
    name: str
    latitude: float
    longitude: float
    distance_km: float
    notes: str = ""
    source: str = "OpenStreetMap"


_FRESHWATER_QUERY = """
[out:json][timeout:25];
(
  node["natural"="spring"](around:{radius},{lat},{lon});
  way["natural"="water"](around:{radius},{lat},{lon});
  way["waterway"="river"](around:{radius},{lat},{lon});
  relation["natural"="water"](around:{radius},{lat},{lon});
);
out center 10;
"""

_SHELTER_QUERY = """
[out:json][timeout:25];
(
  node["amenity"="shelter"](around:{radius},{lat},{lon});
  node["amenity"="hospital"](around:{radius},{lat},{lon});
  node["emergency"="assembly_point"](around:{radius},{lat},{lon});
);
out center 10;
"""


async def find_resources(
    lat: float, lon: float, radius_m: int = 50000
) -> list[ResourceResult]:
    results: list[ResourceResult] = []
    async with httpx.AsyncClient(timeout=30.0) as client:
        fw, sh = await asyncio.gather(
            _query_overpass(client, _FRESHWATER_QUERY, lat, lon, radius_m),
            _query_overpass(client, _SHELTER_QUERY, lat, lon, radius_m),
            return_exceptions=True,
        )
        if isinstance(fw, list):
            results.extend(_parse_elements(fw, "freshwater", lat, lon))
        if isinstance(sh, list):
            results.extend(_parse_elements(sh, "shelter", lat, lon))

    results.sort(key=lambda r: r.distance_km)
    return results


async def _query_overpass(
    client: httpx.AsyncClient, query_template: str, lat: float, lon: float, radius: int
) -> list[dict]:
    query = query_template.format(lat=lat, lon=lon, radius=radius)
    resp = await client.post(OVERPASS_URL, data={"data": query})
    resp.raise_for_status()
    return resp.json().get("elements", [])


def _parse_elements(
    elements: list[dict], resource_type: str, origin_lat: float, origin_lon: float
) -> list[ResourceResult]:
    out: list[ResourceResult] = []
    for el in elements:
        if "center" in el:
            elat, elon = el["center"]["lat"], el["center"]["lon"]
        elif "lat" in el:
            elat, elon = el["lat"], el["lon"]
        else:
            continue
        tags = el.get("tags", {})
        name = tags.get("name") or tags.get("amenity") or resource_type
        dist = haversine_km(origin_lat, origin_lon, elat, elon)
        out.append(
            ResourceResult(
                resource_type=resource_type,
                name=name,
                latitude=elat,
                longitude=elon,
                distance_km=round(dist, 2),
                notes=tags.get("description", ""),
            )
        )
    return out
