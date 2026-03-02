from typing import List, Optional
from pydantic import BaseModel


class AccommodationOption(BaseModel):
    id: str
    option_type: str                 # budget, comfort, premium
    name: str
    type: str                        # hotel, apartment, camping, hostel, airbnb
    price_per_night_chf: float
    total_price_chf: float
    price_range: str                 # €, €€, €€€
    separate_rooms_available: bool = False
    max_persons: int = 4
    rating: Optional[float] = None
    features: List[str] = []
    teaser: str
    suitable_for_children: bool = False
    booking_hint: str = ""
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
