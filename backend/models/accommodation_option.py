from typing import List, Optional
from pydantic import BaseModel


class AccommodationOption(BaseModel):
    id: str
    name: str
    type: str                        # hotel, apartment, camping, hostel, airbnb, bauernhof, etc.
    price_per_night_chf: float
    total_price_chf: float
    separate_rooms_available: bool = False
    max_persons: int = 4
    rating: Optional[float] = None
    features: List[str] = []
    teaser: str
    description: str = ""            # 1-2 Absätze: Zimmerausstattung, Aktivitäten, Services
    suitable_for_children: bool = False
    geheimtipp_hinweis: Optional[str] = None
    is_geheimtipp: bool = False
    matched_must_haves: List[str] = []
    preference_index: Optional[int] = None
    booking_url: Optional[str] = None        # Booking.com deeplink (mit Hotelname)
    hotel_website_url: Optional[str] = None  # Direkte Hotelwebseite
    booking_search_url: Optional[str] = None  # Booking.com Suchlink (nur Stadt, für Geheimtipp)
    image_overview: Optional[str] = None
    image_mood: Optional[str] = None
    image_customer: Optional[str] = None


class BudgetState(BaseModel):
    total_budget_chf: float
    accommodation_budget_chf: float  # 45% of total
    spent_chf: float
    remaining_chf: float
    nights_confirmed: int
    total_nights: int
    avg_per_night_chf: float
    selected_count: int
    total_stops: int


class AccommodationSelectRequest(BaseModel):
    stop_id: int
    option_index: int


class AccommodationResearchRequest(BaseModel):
    stop_id: str
    extra_instructions: str = ""
