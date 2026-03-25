from typing import List, Optional
from pydantic import BaseModel, field_validator


class StopOption(BaseModel):
    id: int
    option_type: str                 # direct, scenic, cultural, via_point
    region: str
    country: str
    drive_hours: float
    drive_km: float = 0.0
    nights: int
    highlights: List[str] = []
    teaser: str
    is_fixed: bool = False
    # Enriched fields
    population: Optional[str] = None
    altitude_m: Optional[int] = None
    language: Optional[str] = None
    climate_note: Optional[str] = None
    must_see: List[str] = []
    family_friendly: Optional[bool] = None
    maps_url: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    place_id: Optional[str] = None
    # AI quality validation fields (Phase 01)
    outside_corridor: bool = False
    corridor_distance_km: Optional[float] = None
    travel_style_match: bool = True
    is_ferry_required: bool = False


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
