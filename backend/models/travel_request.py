from typing import List, Optional
from pydantic import BaseModel, field_validator
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
    location: str
    fixed_date: Optional[date] = None
    notes: Optional[str] = None


class MandatoryActivity(BaseModel):
    name: str
    location: Optional[str] = None


class TravelRequest(BaseModel):
    # Route
    start_location: str
    via_points: List[ViaPoint] = []
    main_destination: str
    start_date: date
    end_date: date
    total_days: int

    # Travellers
    adults: int = 2
    children: List[Child] = []
    travel_styles: List[str] = []        # adventure, relaxation, culture, romantic,
                                          # culinary, road_trip, nature, city, wellness,
                                          # sport, group, kids, slow_travel, party
    travel_description: str = ""

    # Activities
    mandatory_activities: List[MandatoryActivity] = []
    preferred_activities: List[str] = []
    max_activities_per_stop: int = 5
    max_restaurants_per_stop: int = 3
    activities_radius_km: int = 30

    # Route rules
    max_drive_hours_per_day: float = 4.5
    min_nights_per_stop: int = 1
    max_nights_per_stop: int = 5

    # Accommodation
    accommodation_styles: List[str] = []  # hotel, apartment, camping, hostel, airbnb
    accommodation_must_haves: List[str] = []  # pool, wifi, parking, kitchen, breakfast
    hotel_radius_km: int = 10

    # Budget
    budget_chf: float = 3000.0
    budget_buffer_percent: float = 10.0
