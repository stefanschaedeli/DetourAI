from typing import List, Optional
from pydantic import BaseModel


class StopAccommodation(BaseModel):
    name: str
    type: str                        # hotel, apartment, camping, hostel, airbnb
    price_per_night_chf: float
    total_price_chf: float
    rating: Optional[float] = None
    features: List[str] = []
    booking_url: Optional[str] = None


class StopActivity(BaseModel):
    name: str
    description: str
    duration_hours: float
    price_chf: float = 0.0
    suitable_for_children: bool = False
    notes: Optional[str] = None
    address: Optional[str] = None
    google_maps_url: Optional[str] = None
    image_url: Optional[str] = None
    image_urls: List[str] = []


class Restaurant(BaseModel):
    name: str
    cuisine: str
    price_range: str                 # €, €€, €€€
    family_friendly: bool = False
    notes: Optional[str] = None


class TravelStop(BaseModel):
    id: int
    region: str
    country: str
    arrival_day: int
    nights: int
    drive_hours_from_prev: float = 0.0
    drive_km_from_prev: float = 0.0
    lat: Optional[float] = None
    lng: Optional[float] = None
    accommodation: Optional[StopAccommodation] = None
    top_activities: List[StopActivity] = []
    restaurants: List[Restaurant] = []
    google_maps_url: Optional[str] = None
    notes: Optional[str] = None


class DayPlan(BaseModel):
    day: int
    date: Optional[str] = None
    type: str                        # drive, rest, activity, mixed
    title: str
    description: str
    stops_on_route: List[str] = []
    google_maps_route_url: Optional[str] = None


class CostEstimate(BaseModel):
    accommodations_chf: float
    ferries_chf: float = 0.0
    activities_chf: float
    food_chf: float
    fuel_chf: float
    total_chf: float
    budget_remaining_chf: float


class TravelPlan(BaseModel):
    job_id: str
    start_location: str
    start_lat: Optional[float] = None
    start_lng: Optional[float] = None
    stops: List[TravelStop]
    day_plans: List[DayPlan]
    cost_estimate: CostEstimate
    google_maps_overview_url: Optional[str] = None
    outputs: dict = {}
