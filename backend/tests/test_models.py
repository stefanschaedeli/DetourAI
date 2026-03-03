import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from models.travel_request import TravelRequest, Child, ViaPoint, MandatoryActivity
from models.travel_response import TravelPlan, TravelStop, DayPlan, CostEstimate, StopAccommodation, StopActivity, Restaurant
from models.stop_option import StopOption, StopOptionsResponse, StopSelectRequest
from models.accommodation_option import AccommodationOption, BudgetState, AccommodationSelectRequest


# ---------------------------------------------------------------------------
# TravelRequest
# ---------------------------------------------------------------------------

def test_travel_request_valid(sample_request):
    req = TravelRequest(**sample_request)
    assert req.adults == 2
    assert req.budget_chf == 5000.0
    assert req.start_location == "Liestal, Schweiz"


@pytest.fixture
def sample_request():
    return {
        "start_location": "Liestal, Schweiz",
        "main_destination": "Paris, Frankreich",
        "start_date": "2026-06-01",
        "end_date": "2026-06-10",
        "total_days": 10,
        "adults": 2,
        "children": [],
        "budget_chf": 5000,
        "travel_styles": ["culture", "culinary"],
    }


def test_travel_request_defaults():
    req = TravelRequest(
        start_location="Liestal",
        main_destination="Paris",
        start_date="2026-06-01",
        end_date="2026-06-10",
        total_days=10,
    )
    assert req.adults == 2
    assert req.budget_chf == 3000.0
    assert req.max_drive_hours_per_day == 4.5
    assert req.via_points == []


def test_travel_request_with_via_points():
    req = TravelRequest(
        start_location="Liestal",
        main_destination="Paris",
        start_date="2026-06-01",
        end_date="2026-06-10",
        total_days=10,
        via_points=[{"location": "Annecy"}, {"location": "Lyon", "fixed_date": "2026-06-04"}],
    )
    assert len(req.via_points) == 2
    assert req.via_points[0].location == "Annecy"
    assert req.via_points[0].fixed_date is None
    assert req.via_points[1].fixed_date is not None


# ---------------------------------------------------------------------------
# Child age validation
# ---------------------------------------------------------------------------

def test_child_age_valid():
    child = Child(age=10)
    assert child.age == 10


def test_child_age_zero():
    child = Child(age=0)
    assert child.age == 0


def test_child_age_max():
    child = Child(age=17)
    assert child.age == 17


def test_child_age_invalid_too_old():
    with pytest.raises(ValueError):
        Child(age=18)


def test_child_age_invalid_negative():
    with pytest.raises(ValueError):
        Child(age=-1)


# ---------------------------------------------------------------------------
# ViaPoint
# ---------------------------------------------------------------------------

def test_via_point_required():
    vp = ViaPoint(location="Bern")
    assert vp.location == "Bern"
    assert vp.fixed_date is None
    assert vp.notes is None


def test_via_point_optional_date():
    vp = ViaPoint(location="Bern")
    assert vp.fixed_date is None


def test_via_point_with_date():
    vp = ViaPoint(location="Lyon", fixed_date="2026-06-05")
    assert vp.fixed_date is not None


# ---------------------------------------------------------------------------
# StopSelectRequest
# ---------------------------------------------------------------------------

def test_stop_select_valid():
    req = StopSelectRequest(option_index=0)
    assert req.option_index == 0


def test_stop_select_max_valid():
    req = StopSelectRequest(option_index=2)
    assert req.option_index == 2


def test_stop_select_invalid_high():
    with pytest.raises(ValueError):
        StopSelectRequest(option_index=3)


def test_stop_select_invalid_negative():
    with pytest.raises(ValueError):
        StopSelectRequest(option_index=-1)


# ---------------------------------------------------------------------------
# AccommodationOption
# ---------------------------------------------------------------------------

def test_accommodation_option_types():
    for opt_type in ["budget", "comfort", "premium", "geheimtipp"]:
        opt = AccommodationOption(
            id=f"acc_1_{opt_type}",
            option_type=opt_type,
            name="Test Hotel",
            type="hotel",
            price_per_night_chf=100.0,
            total_price_chf=200.0,
            price_range="€€",
            teaser="Ein gutes Hotel",
        )
        assert opt.option_type == opt_type


def test_accommodation_booking_url():
    opt = AccommodationOption(
        id="acc_1_comfort",
        option_type="comfort",
        name="Hotel Test",
        type="hotel",
        price_per_night_chf=150.0,
        total_price_chf=300.0,
        price_range="€€",
        teaser="Komfortables Hotel",
        booking_url="https://www.booking.com/search.html?ss=Annecy&checkin=2026-06-02&checkout=2026-06-04&group_adults=2&group_children=0&no_rooms=1&lang=de",
    )
    assert opt.booking_url is not None
    assert "booking.com" in opt.booking_url


def test_accommodation_geheimtipp_no_booking_url():
    opt = AccommodationOption(
        id="acc_1_geheimtipp",
        option_type="geheimtipp",
        name="Berghof Alpenblick",
        type="bauernhof",
        price_per_night_chf=120.0,
        total_price_chf=240.0,
        price_range="€€",
        teaser="Authentischer Bauernhof mit Panoramablick",
        booking_url=None,
        geheimtipp_hinweis="Buche direkt beim Hof oder über lokales Tourismusbüro.",
    )
    assert opt.booking_url is None
    assert opt.geheimtipp_hinweis is not None
    assert opt.option_type == "geheimtipp"


def test_accommodation_option_defaults():
    opt = AccommodationOption(
        id="acc_1_budget",
        option_type="budget",
        name="Budget Inn",
        type="hostel",
        price_per_night_chf=60.0,
        total_price_chf=120.0,
        price_range="€",
        teaser="Günstig und central",
    )
    assert opt.separate_rooms_available is False
    assert opt.max_persons == 4
    assert opt.rating is None
    assert opt.suitable_for_children is False


def test_accommodation_price_source_default():
    opt = AccommodationOption(
        id="acc_1_budget", option_type="budget", name="Test",
        type="hotel", price_per_night_chf=100, total_price_chf=200,
        price_range="€€", teaser="Test",
    )
    assert opt.price_source == "estimate"


def test_accommodation_price_source_real():
    opt = AccommodationOption(
        id="acc_1_comfort", option_type="comfort", name="Test",
        type="hotel", price_per_night_chf=150, total_price_chf=300,
        price_range="€€", teaser="Test", price_source="booking.com",
    )
    assert opt.price_source == "booking.com"


# ---------------------------------------------------------------------------
# BudgetState
# ---------------------------------------------------------------------------

def test_budget_state():
    bs = BudgetState(
        total_budget_chf=5000,
        accommodation_budget_chf=2250,
        spent_chf=500,
        remaining_chf=1750,
        nights_confirmed=2,
        total_nights=10,
        avg_per_night_chf=250.0,
        selected_count=1,
        total_stops=4,
    )
    assert bs.accommodation_budget_chf == 2250


# ---------------------------------------------------------------------------
# TravelStop
# ---------------------------------------------------------------------------

def test_travel_stop_defaults():
    stop = TravelStop(
        id=1, region="Annecy", country="FR",
        arrival_day=2, nights=2,
    )
    assert stop.drive_hours_from_prev == 0.0
    assert stop.accommodation is None
    assert stop.top_activities == []
    assert stop.restaurants == []


# ---------------------------------------------------------------------------
# StopOption
# ---------------------------------------------------------------------------

def test_stop_option_types():
    for opt_type in ["direct", "scenic", "cultural", "via_point"]:
        opt = StopOption(
            id=1, option_type=opt_type,
            region="Annecy", country="FR",
            drive_hours=3.5, nights=2,
            teaser="Test"
        )
        assert opt.option_type == opt_type


# ---------------------------------------------------------------------------
# CostEstimate
# ---------------------------------------------------------------------------

def test_cost_estimate():
    cost = CostEstimate(
        accommodations_chf=1800,
        activities_chf=400,
        food_chf=700,
        fuel_chf=200,
        total_chf=3100,
        budget_remaining_chf=1900,
    )
    assert cost.ferries_chf == 0.0
    assert cost.total_chf == 3100
