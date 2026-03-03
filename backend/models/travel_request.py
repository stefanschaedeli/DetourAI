from typing import List, Optional
from pydantic import BaseModel, field_validator, model_validator, Field
from datetime import date


class Child(BaseModel):
    age: int

    @field_validator('age')
    @classmethod
    def age_valid(cls, v):
        if not 0 <= v <= 17:
            raise ValueError('age must be 0-17')
        return v


class ViaPoint(BaseModel):
    location: str = Field(max_length=200)
    fixed_date: Optional[date] = None
    notes: Optional[str] = Field(default=None, max_length=500)


class MandatoryActivity(BaseModel):
    name: str = Field(max_length=200)
    location: Optional[str] = Field(default=None, max_length=200)


class TravelRequest(BaseModel):
    # Route
    start_location: str = Field(max_length=200)
    via_points: List[ViaPoint] = Field(default=[], max_length=10)
    main_destination: str = Field(max_length=200)
    start_date: date
    end_date: date
    total_days: int

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

    # Route rules
    max_drive_hours_per_day: float = Field(default=4.5, ge=0.5, le=16)
    min_nights_per_stop: int = Field(default=1, ge=1, le=14)
    max_nights_per_stop: int = Field(default=5, ge=1, le=30)

    # Accommodation
    accommodation_styles: List[str] = Field(default=[], max_length=5)   # hotel, apartment, camping, hostel, airbnb
    accommodation_must_haves: List[str] = Field(default=[], max_length=10)  # pool, wifi, parking, kitchen, breakfast
    hotel_radius_km: int = Field(default=10, ge=1, le=100)

    # Budget
    budget_chf: float = Field(default=3000.0, ge=100, le=500_000)
    budget_buffer_percent: float = Field(default=10.0, ge=0, le=50)
    budget_accommodation_pct: int = Field(default=60, ge=0, le=100)
    budget_food_pct: int = Field(default=20, ge=0, le=100)
    budget_activities_pct: int = Field(default=20, ge=0, le=100)

    @model_validator(mode='after')
    def budget_pcts_sum_to_100(self):
        total = self.budget_accommodation_pct + self.budget_food_pct + self.budget_activities_pct
        if total != 100:
            raise ValueError(f'budget percentages must sum to 100 (got {total})')
        return self
