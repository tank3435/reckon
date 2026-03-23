"""
Geocoding wrapper using Nominatim (OSM) — no API key required for low volume.
Results are cached in location_profiles to avoid hammering the geocoding service.
"""

from datetime import datetime, timedelta

from geopy.geocoders import Nominatim
from geopy.exc import GeocoderServiceError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from reckon.models.location import LocationProfile

CACHE_TTL_HOURS = 24
_geocoder = Nominatim(user_agent="reckon-app/0.1")


async def geocode_query(query: str, db: AsyncSession) -> LocationProfile | None:
    """Return a cached or freshly geocoded LocationProfile for the query string."""
    # Check cache
    stmt = select(LocationProfile).where(LocationProfile.query == query.lower().strip())
    cached = (await db.execute(stmt)).scalar_one_or_none()
    if cached:
        age = datetime.utcnow() - cached.cached_at.replace(tzinfo=None)
        if age < timedelta(hours=CACHE_TTL_HOURS):
            return cached

    # Geocode via Nominatim (sync call — wrap in executor for async context)
    import asyncio
    loop = asyncio.get_event_loop()
    try:
        location = await loop.run_in_executor(
            None, lambda: _geocoder.geocode(query, language="en", addressdetails=True)
        )
    except GeocoderServiceError:
        return None

    if location is None:
        return None

    address = location.raw.get("address", {})
    profile = LocationProfile(
        query=query.lower().strip(),
        display_name=location.address,
        latitude=location.latitude,
        longitude=location.longitude,
        country_code=address.get("country_code", "").upper(),
        cached_at=datetime.utcnow(),
    )

    if cached:
        cached.display_name = profile.display_name
        cached.latitude = profile.latitude
        cached.longitude = profile.longitude
        cached.country_code = profile.country_code
        cached.cached_at = profile.cached_at
        await db.commit()
        return cached

    db.add(profile)
    await db.commit()
    await db.refresh(profile)
    return profile
