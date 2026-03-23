from pydantic import BaseModel


class SurvivalResourceOut(BaseModel):
    resource_type: str
    name: str
    latitude: float
    longitude: float
    distance_km: float
    notes: str
    source: str

    model_config = {"from_attributes": True}


class LocationProfileOut(BaseModel):
    query: str
    display_name: str
    latitude: float
    longitude: float
    country_code: str

    model_config = {"from_attributes": True}


class LocationIntelOut(BaseModel):
    location: LocationProfileOut
    resources: list[SurvivalResourceOut]
    nuclear_target_proximity_km: float | None
    nearest_freshwater_km: float | None
