"""
Location intelligence facade — single entry point for the API layer.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from reckon.locations.geocoder import geocode_query
from reckon.locations.nuclear import nearest_nuclear_target
from reckon.locations.resources import find_resources
from reckon.schemas.location import LocationIntelOut, LocationProfileOut, SurvivalResourceOut


async def get_location_intel(query: str, db: AsyncSession) -> LocationIntelOut | None:
    profile = await geocode_query(query, db)
    if profile is None:
        return None

    lat, lon = profile.latitude, profile.longitude

    # Run resource lookup and nuclear proximity in parallel
    resources = await find_resources(lat, lon)
    nuclear_result = nearest_nuclear_target(lat, lon)

    resource_outs = [
        SurvivalResourceOut(
            resource_type=r.resource_type,
            name=r.name,
            latitude=r.latitude,
            longitude=r.longitude,
            distance_km=r.distance_km,
            notes=r.notes,
            source=r.source,
        )
        for r in resources
    ]

    freshwater_distances = [
        r.distance_km for r in resources if r.resource_type == "freshwater"
    ]

    return LocationIntelOut(
        location=LocationProfileOut(
            query=profile.query,
            display_name=profile.display_name,
            latitude=lat,
            longitude=lon,
            country_code=profile.country_code,
        ),
        resources=resource_outs,
        nuclear_target_proximity_km=round(nuclear_result[1], 1) if nuclear_result else None,
        nearest_freshwater_km=min(freshwater_distances) if freshwater_distances else None,
    )
