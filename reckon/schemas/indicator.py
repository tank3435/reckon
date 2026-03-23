from datetime import datetime

from pydantic import BaseModel


class IndicatorOut(BaseModel):
    id: int
    tier: str
    name: str
    source: str
    raw_value: float
    unit: str
    collected_at: datetime

    model_config = {"from_attributes": True}


class BaselineOut(BaseModel):
    indicator_name: str
    tier: str
    mean: float
    stddev: float
    weight: float

    model_config = {"from_attributes": True}


class BaselineIn(BaseModel):
    indicator_name: str
    tier: str
    mean: float
    stddev: float
    weight: float = 1.0
