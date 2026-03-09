from typing import List, Optional
from pydantic import BaseModel


class TravelGuide(BaseModel):
    intro_narrative: str
    history_culture: str
    food_specialties: str
    local_tips: str
    insider_gems: str
    best_time_to_visit: str


class TimeBlock(BaseModel):
    time: str                          # "09:00"
    activity_type: str                 # drive, activity, meal, break, check_in
    title: str
    location: str
    duration_minutes: int
    description: str
    google_search_url: Optional[str] = None
    google_maps_url: Optional[str] = None
    price_chf: Optional[float] = None


class StopAccommodation(BaseModel):
    name: str
    type: str                        # hotel, apartment, camping, hostel, airbnb
    price_per_night_chf: float
    total_price_chf: float
    rating: Optional[float] = None
    features: List[str] = []
    description: Optional[str] = None
    is_geheimtipp: bool = False
    matched_must_haves: List[str] = []
    preference_index: Optional[int] = None
    booking_url: Optional[str] = None
    hotel_website_url: Optional[str] = None
    booking_search_url: Optional[str] = None
    image_overview: Optional[str] = None
    image_mood: Optional[str] = None
    image_customer: Optional[str] = None


class StopActivity(BaseModel):
    name: str
    description: str
    duration_hours: float
    price_chf: float = 0.0
    suitable_for_children: bool = False
    notes: Optional[str] = None
    address: Optional[str] = None
    google_maps_url: Optional[str] = None
    image_overview: Optional[str] = None
    image_mood: Optional[str] = None
    image_customer: Optional[str] = None


class Restaurant(BaseModel):
    name: str
    cuisine: str
    price_range: str                 # €, €€, €€€
    family_friendly: bool = False
    notes: Optional[str] = None
    image_overview: Optional[str] = None
    image_mood: Optional[str] = None
    image_customer: Optional[str] = None


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
    all_accommodation_options: List[dict] = []
    top_activities: List[StopActivity] = []
    restaurants: List[Restaurant] = []
    travel_guide: Optional[TravelGuide] = None
    further_activities: List[StopActivity] = []
    google_maps_url: Optional[str] = None
    notes: Optional[str] = None
    image_overview: Optional[str] = None
    image_mood: Optional[str] = None
    image_customer: Optional[str] = None


class DayPlan(BaseModel):
    day: int
    date: Optional[str] = None
    type: str                        # drive, rest, activity, mixed
    title: str
    description: str
    stops_on_route: List[str] = []
    google_maps_route_url: Optional[str] = None
    time_blocks: List[TimeBlock] = []


class CostEstimate(BaseModel):
    accommodations_chf: float
    ferries_chf: float = 0.0
    activities_chf: float
    food_chf: float
    fuel_chf: float
    total_chf: float
    budget_remaining_chf: float


class ImprovementSuggestion(BaseModel):
    title: str
    description: str
    impact: str  # "high", "medium", "low"


class TripAnalysis(BaseModel):
    settings_summary: str
    requirements_match_score: int       # 1–10
    requirements_analysis: str
    strengths: List[str] = []
    weaknesses: List[str] = []
    improvement_suggestions: List[ImprovementSuggestion] = []


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
    trip_analysis: Optional[TripAnalysis] = None
