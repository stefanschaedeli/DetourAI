from typing import List, Optional
from pydantic import BaseModel, field_validator, model_validator, Field
from datetime import date
from models.via_point import ViaPoint  # noqa: F401 — re-exported for backward compat
from models.trip_leg import TripLeg


class Child(BaseModel):
    age: int

    @field_validator('age')
    @classmethod
    def age_valid(cls, v):
        if not 0 <= v <= 17:
            raise ValueError('age must be 0-17')
        return v


class MandatoryActivity(BaseModel):
    name: str = Field(max_length=200)
    location: Optional[str] = Field(default=None, max_length=200)


class TravelRequest(BaseModel):
    # Route — now defined as legs
    legs: List[TripLeg] = Field(min_length=1, max_length=20)

    # Travellers
    adults: int = Field(default=2, ge=1, le=20)
    children: List[Child] = Field(default=[], max_length=10)
    travel_styles: List[str] = Field(default=[], max_length=14)  # adventure, relaxation, culture, romantic,
                                                                  # culinary, road_trip, nature, city, wellness,
                                                                  # sport, group, kids, slow_travel, party
    travel_description: str = Field(default="", max_length=2000)

    # Activities
    mandatory_activities: List[MandatoryActivity] = Field(default=[], max_length=20)
    preferred_activities: List[str] = Field(default=[], max_length=20)
    max_activities_per_stop: int = Field(default=5, ge=1, le=20)
    max_restaurants_per_stop: int = Field(default=3, ge=1, le=10)
    activities_radius_km: int = Field(default=30, ge=1, le=200)

    # Route rules (global — apply to all legs)
    max_drive_hours_per_day: float = Field(default=4.5, ge=0.5, le=16)
    min_nights_per_stop: int = Field(default=1, ge=1, le=14)
    max_nights_per_stop: int = Field(default=5, ge=1, le=30)
    proximity_origin_pct: int = Field(default=10, ge=0, le=30)   # % of segment km — min distance from trip start
    proximity_target_pct: int = Field(default=15, ge=0, le=30)   # % of segment km — min distance from segment target

    # Accommodation
    accommodation_preferences: List[str] = Field(default=[], max_length=3)
    hotel_radius_km: int = Field(default=10, ge=1, le=100)

    # Budget
    budget_chf: float = Field(default=3000.0, ge=100, le=500_000)
    budget_buffer_percent: float = Field(default=10.0, ge=0, le=50)
    budget_accommodation_pct: int = Field(default=60, ge=0, le=100)
    budget_food_pct: int = Field(default=20, ge=0, le=100)
    budget_activities_pct: int = Field(default=20, ge=0, le=100)

    # --- Derived properties (replace removed explicit fields) ---

    @property
    def start_location(self) -> str:
        return self.legs[0].start_location.strip()

    @property
    def main_destination(self) -> str:
        return self.legs[-1].end_location.strip()

    @property
    def start_date(self) -> date:
        return self.legs[0].start_date

    @property
    def end_date(self) -> date:
        return self.legs[-1].end_date

    @property
    def total_days(self) -> int:
        return sum(leg.total_days for leg in self.legs)

    @property
    def via_points(self) -> List[ViaPoint]:
        """Flattened via_points across all transit legs."""
        return [vp for leg in self.legs if leg.mode == "transit" for vp in leg.via_points]

    @model_validator(mode='after')
    def budget_pcts_sum_to_100(self):
        total = self.budget_accommodation_pct + self.budget_food_pct + self.budget_activities_pct
        if total != 100:
            raise ValueError(f'budget percentages must sum to 100 (got {total})')
        return self

    @model_validator(mode='after')
    def validate_legs_chain(self):
        for i in range(1, len(self.legs)):
            prev, curr = self.legs[i - 1], self.legs[i]
            # Skip location chain check if either leg is explore (locations optional)
            prev_end = prev.end_location.strip().lower() if prev.end_location else ""
            curr_start = curr.start_location.strip().lower() if curr.start_location else ""
            if prev_end and curr_start and prev_end != curr_start:
                raise ValueError(
                    f"Leg {i} start_location must match leg {i-1} end_location "
                    f"(got '{curr.start_location}' vs '{prev.end_location}')"
                )
            if curr.start_date != prev.end_date:
                raise ValueError(
                    f"Leg {i} start_date must equal leg {i-1} end_date"
                )
        return self
