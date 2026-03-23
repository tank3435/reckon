from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from reckon.db import get_db
from reckon.locations.intel import get_location_intel
from reckon.schemas.location import LocationIntelOut

router = APIRouter(prefix="/locations", tags=["locations"])


@router.get("/intel", response_model=LocationIntelOut)
async def location_intel(
    q: str = Query(..., description="City name, zip code, or address"),
    db: AsyncSession = Depends(get_db),
) -> LocationIntelOut:
    """
    Return geographic survival intelligence for a given location query.
    Includes nearby freshwater, shelters, and nuclear target proximity.
    """
    result = await get_location_intel(q, db)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Could not geocode: {q!r}")
    return result
