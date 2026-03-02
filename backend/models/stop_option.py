from typing import List, Optional
from pydantic import BaseModel, field_validator


class StopOption(BaseModel):
    id: int
    option_type: str                 # direct, scenic, cultural, via_point
    region: str
    country: str
    drive_hours: float
    nights: int
    highlights: List[str] = []
    teaser: str
    is_fixed: bool = False


class StopOptionsResponse(BaseModel):
    options: List[StopOption]
    route_could_be_complete: bool
    days_remaining: int
    current_stop_number: int
    estimated_total_stops: int


class StopSelectRequest(BaseModel):
    option_index: int

    @field_validator('option_index')
    @classmethod
    def index_valid(cls, v):
        if not 0 <= v <= 2:
            raise ValueError('option_index must be 0, 1, or 2')
        return v
