import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from pydantic import ValidationError
from models.travel_request import TravelRequest, Child, ViaPoint, MandatoryActivity
from models.travel_response import TravelPlan, TravelStop, DayPlan, CostEstimate, StopAccommodation, StopActivity, Restaurant, TravelGuide, TimeBlock
from models.stop_option import StopOption, StopOptionsResponse, StopSelectRequest
from models.accommodation_option import AccommodationOption, BudgetState, AccommodationSelectRequest, AccommodationResearchRequest


# ---------------------------------------------------------------------------
# TravelRequest
# ---------------------------------------------------------------------------

def test_travel_request_valid(sample_request):
    req = TravelRequest(**sample_request)
    assert req.adults == 2
    assert req.budget_chf == 5000.0
    assert req.start_location == "Liestal, Schweiz"
    assert req.main_destination == "Paris, Frankreich"


def _sample_leg():
    return TripLeg(
        leg_id="leg-0",
        start_location="Liestal, Schweiz",
        end_location="Paris, Frankreich",
        start_date=date(2026, 6, 1),
        end_date=date(2026, 6, 10),
        mode="transit",
    )


@pytest.fixture
def sample_request():
    return {
        "legs": [_sample_leg()],
        "adults": 2,
        "children": [],
        "budget_chf": 5000,
        "travel_styles": ["culture", "culinary"],
        "accommodation_preferences": ["romantisches Hotel", "Camping mit Aussicht"],
    }


def test_travel_request_accommodation_preferences():
    leg = TripLeg(
        leg_id="leg-0",
        start_location="Liestal",
        end_location="Paris",
        start_date=date(2026, 6, 1),
        end_date=date(2026, 6, 10),
        mode="transit",
    )
    req = TravelRequest(
        legs=[leg],
        accommodation_preferences=["romantisches Hotel", "Camping mit Aussicht"],
    )
    assert req.accommodation_preferences == ["romantisches Hotel", "Camping mit Aussicht"]


def test_travel_request_accommodation_preferences_too_many():
    leg = TripLeg(
        leg_id="leg-0",
        start_location="Liestal",
        end_location="Paris",
        start_date=date(2026, 6, 1),
        end_date=date(2026, 6, 10),
        mode="transit",
    )
    with pytest.raises(Exception):
        TravelRequest(
            legs=[leg],
            accommodation_preferences=["a", "b", "c", "d"],
        )


def test_travel_request_defaults():
    leg = TripLeg(
        leg_id="leg-0",
        start_location="Liestal",
        end_location="Paris",
        start_date=date(2026, 6, 1),
        end_date=date(2026, 6, 10),
        mode="transit",
    )
    req = TravelRequest(legs=[leg])
    assert req.adults == 2
    assert req.budget_chf == 3000.0
    assert req.max_drive_hours_per_day == 4.5
    assert req.via_points == []


def test_travel_request_with_via_points():
    leg = TripLeg(
        leg_id="leg-0",
        start_location="Liestal",
        end_location="Paris",
        start_date=date(2026, 6, 1),
        end_date=date(2026, 6, 10),
        mode="transit",
        via_points=[ViaPoint(location="Annecy"), ViaPoint(location="Lyon", fixed_date=date(2026, 6, 4))],
    )
    req = TravelRequest(legs=[leg])
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
    for acc_type in ["hotel", "apartment", "camping", "hostel", "bauernhof"]:
        opt = AccommodationOption(
            id=f"acc_1_{acc_type}",
            name="Test Hotel",
            type=acc_type,
            price_per_night_chf=100.0,
            total_price_chf=200.0,
            teaser="Ein gutes Hotel",
        )
        assert opt.type == acc_type


def test_accommodation_booking_url():
    opt = AccommodationOption(
        id="acc_1_1",
        name="Hotel Test",
        type="hotel",
        price_per_night_chf=150.0,
        total_price_chf=300.0,
        teaser="Komfortables Hotel",
        booking_url="https://www.booking.com/search.html?ss=Annecy&checkin=2026-06-02&checkout=2026-06-04&group_adults=2&group_children=0&no_rooms=1&lang=de",
    )
    assert opt.booking_url is not None
    assert "booking.com" in opt.booking_url


def test_accommodation_geheimtipp_fields():
    opt = AccommodationOption(
        id="acc_1_3",
        name="Berghof Alpenblick",
        type="bauernhof",
        price_per_night_chf=120.0,
        total_price_chf=240.0,
        teaser="Authentischer Bauernhof mit Panoramablick",
        booking_url=None,
        is_geheimtipp=True,
        booking_search_url="https://www.booking.com/searchresults.html?ss=Annecy%2C+FR",
        geheimtipp_hinweis="Buche direkt beim Hof oder über lokales Tourismusbüro.",
    )
    assert opt.booking_url is None
    assert opt.is_geheimtipp is True
    assert opt.geheimtipp_hinweis is not None
    assert opt.booking_search_url is not None


def test_accommodation_option_preference_index():
    opt = AccommodationOption(
        id="acc_1_1",
        name="Test Hotel",
        type="hotel",
        price_per_night_chf=100.0,
        total_price_chf=200.0,
        teaser="Test",
        preference_index=0,
    )
    assert opt.preference_index == 0

    opt_geheimtipp = AccommodationOption(
        id="acc_1_4",
        name="Geheimtipp",
        type="bauernhof",
        price_per_night_chf=100.0,
        total_price_chf=200.0,
        teaser="Geheimtipp",
        is_geheimtipp=True,
    )
    assert opt_geheimtipp.preference_index is None


def test_accommodation_option_defaults():
    opt = AccommodationOption(
        id="acc_1_1",
        name="Budget Inn",
        type="hostel",
        price_per_night_chf=60.0,
        total_price_chf=120.0,
        teaser="Günstig und central",
    )
    assert opt.separate_rooms_available is False
    assert opt.max_persons == 4
    assert opt.rating is None
    assert opt.suitable_for_children is False
    assert opt.is_geheimtipp is False
    assert opt.matched_must_haves == []
    assert opt.description == ""


def test_accommodation_description_and_must_haves():
    opt = AccommodationOption(
        id="acc_1_2",
        name="Test Hotel",
        type="hotel",
        price_per_night_chf=100,
        total_price_chf=200,
        teaser="Test",
        description="Komfortables Hotel mit WiFi und Parkplatz.",
        matched_must_haves=["WiFi", "Parkplatz"],
    )
    assert "WiFi" in opt.matched_must_haves
    assert opt.description != ""


def test_accommodation_hotel_website_url():
    opt = AccommodationOption(
        id="acc_1_2",
        name="Test Hotel",
        type="hotel",
        price_per_night_chf=150,
        total_price_chf=300,
        teaser="Test",
        hotel_website_url="https://example-hotel.com",
    )
    assert opt.hotel_website_url == "https://example-hotel.com"


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


def test_stop_option_place_id():
    opt = StopOption(
        id=1, option_type="direct", region="Bern", country="Schweiz",
        drive_hours=2.0, nights=2, teaser="Test",
        place_id="ChIJMz5dPRdMkEcRjnz1cE6JLGU",
    )
    assert opt.place_id == "ChIJMz5dPRdMkEcRjnz1cE6JLGU"


def test_stop_option_place_id_default_none():
    opt = StopOption(
        id=1, option_type="direct", region="Bern", country="Schweiz",
        drive_hours=2.0, nights=2, teaser="Test",
    )
    assert opt.place_id is None


def test_stop_option_tags():
    # Default: empty list
    opt = StopOption(
        id=1, option_type="direct", region="Bern", country="Schweiz",
        drive_hours=2.0, nights=2, teaser="Test",
    )
    assert opt.tags == []
    # Explicit tags
    opt_tags = StopOption(
        id=2, option_type="scenic", region="Annecy", country="FR",
        drive_hours=3.0, nights=2, teaser="Charmant",
        tags=["Strand", "Kultur"],
    )
    assert opt_tags.tags == ["Strand", "Kultur"]


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


# ---------------------------------------------------------------------------
# TravelGuide
# ---------------------------------------------------------------------------

def test_travel_guide_valid():
    guide = TravelGuide(
        intro_narrative="Annecy ist eine wunderschöne Stadt.",
        history_culture="Lange Geschichte aus dem Mittelalter.",
        food_specialties="Tartiflette und Reblochon-Käse.",
        local_tips="Am frühen Morgen die Altstadt erkunden.",
        insider_gems="Der Gorge du Fier ist weniger bekannt.",
        best_time_to_visit="Mai bis September ist ideal.",
    )
    assert guide.intro_narrative.startswith("Annecy")
    assert guide.history_culture != ""
    assert guide.best_time_to_visit != ""


# ---------------------------------------------------------------------------
# TimeBlock
# ---------------------------------------------------------------------------

def test_time_block_required_fields():
    tb = TimeBlock(
        time="09:00",
        activity_type="drive",
        title="Abfahrt nach Annecy",
        location="Autoroute A40",
        duration_minutes=150,
        description="Fahrt durch die Alpen",
    )
    assert tb.time == "09:00"
    assert tb.activity_type == "drive"
    assert tb.duration_minutes == 150
    assert tb.google_search_url is None
    assert tb.google_maps_url is None
    assert tb.price_chf is None


def test_time_block_meal_with_search_url():
    tb = TimeBlock(
        time="12:30",
        activity_type="meal",
        title="Mittagessen",
        location="Annecy Altstadt",
        duration_minutes=60,
        description="Lokale Spezialitäten",
        google_search_url="https://www.google.com/search?q=restaurant+annecy",
        price_chf=35.0,
    )
    assert tb.google_search_url is not None
    assert "google.com" in tb.google_search_url
    assert tb.price_chf == 35.0


def test_time_block_place_id():
    tb = TimeBlock(
        time="09:00", activity_type="activity", title="Museum",
        location="Bern", duration_minutes=120, description="Besuch",
        place_id="ChIJABC123",
    )
    assert tb.place_id == "ChIJABC123"


# ---------------------------------------------------------------------------
# TravelPlan start_place_id
# ---------------------------------------------------------------------------

def test_travel_plan_start_place_id():
    plan = TravelPlan(
        job_id="test", start_location="Liestal",
        start_place_id="ChIJMz5dPRdMkEcR123",
        stops=[], day_plans=[],
        cost_estimate=CostEstimate(
            accommodations_chf=0, activities_chf=0, food_chf=0,
            fuel_chf=0, total_chf=0, budget_remaining_chf=0,
        ),
    )
    assert plan.start_place_id == "ChIJMz5dPRdMkEcR123"


# ---------------------------------------------------------------------------
# TravelStop with new fields
# ---------------------------------------------------------------------------

def test_travel_stop_new_fields_default():
    stop = TravelStop(
        id=1, region="Annecy", country="FR",
        arrival_day=2, nights=2,
    )
    assert stop.travel_guide is None
    assert stop.further_activities == []
    assert stop.all_accommodation_options == []


def test_travel_stop_all_accommodation_options():
    stop = TravelStop(
        id=1, region="Annecy", country="FR",
        arrival_day=2, nights=2,
        all_accommodation_options=[{"name": "Hotel A"}, {"name": "Hotel B"}],
    )
    assert len(stop.all_accommodation_options) == 2


def test_travel_stop_with_travel_guide():
    guide = TravelGuide(
        intro_narrative="Intro",
        history_culture="History",
        food_specialties="Food",
        local_tips="Tips",
        insider_gems="Gems",
        best_time_to_visit="Summer",
    )
    stop = TravelStop(
        id=1, region="Annecy", country="FR",
        arrival_day=2, nights=2,
        travel_guide=guide,
    )
    assert stop.travel_guide is not None
    assert stop.travel_guide.intro_narrative == "Intro"


# ---------------------------------------------------------------------------
# TravelStop tags, teaser, highlights
# ---------------------------------------------------------------------------

def test_travel_stop_tags_teaser():
    """Tags, teaser, highlights: defaults and explicit values."""
    # defaults when omitted
    stop_default = TravelStop(
        id=1, region="Annecy", country="FR",
        arrival_day=2, nights=2,
    )
    assert stop_default.tags == []
    assert stop_default.teaser is None
    assert stop_default.highlights == []

    # explicit values
    stop_full = TravelStop(
        id=2, region="Luzern", country="CH",
        arrival_day=3, nights=1,
        tags=["Kultur", "See"],
        teaser="Charmante Altstadt am Vierwaldstaettersee",
        highlights=["Altstadt", "Seepromenade", "Kapellbruecke"],
    )
    assert stop_full.tags == ["Kultur", "See"]
    assert stop_full.teaser == "Charmante Altstadt am Vierwaldstaettersee"
    assert stop_full.highlights == ["Altstadt", "Seepromenade", "Kapellbruecke"]

    # backward compatibility: existing construction without new fields
    stop_compat = TravelStop(
        id=3, region="Annecy", country="FR",
        arrival_day=2, nights=2,
        drive_hours_from_prev=3.5,
        drive_km_from_prev=220.0,
        lat=45.899, lng=6.129,
    )
    assert stop_compat.tags == []
    assert stop_compat.teaser is None
    assert stop_compat.highlights == []


# ---------------------------------------------------------------------------
# DayPlan with time_blocks
# ---------------------------------------------------------------------------

def test_day_plan_time_blocks_default():
    dp = DayPlan(
        day=1, type="drive", title="Abreise", description="Erster Tag"
    )
    assert dp.time_blocks == []


def test_day_plan_with_time_blocks():
    tb = TimeBlock(
        time="08:00",
        activity_type="drive",
        title="Abfahrt",
        location="Liestal",
        duration_minutes=180,
        description="Fahrt nach Annecy",
    )
    dp = DayPlan(
        day=1, type="drive", title="Abreise", description="Erster Tag",
        time_blocks=[tb],
    )
    assert len(dp.time_blocks) == 1
    assert dp.time_blocks[0].activity_type == "drive"


# ---------------------------------------------------------------------------
# place_id field coverage
# ---------------------------------------------------------------------------

def test_place_id_defaults_to_none():
    from models.travel_response import StopActivity, Restaurant, StopAccommodation, TravelStop
    from models.accommodation_option import AccommodationOption

    act = StopActivity(name="Eiffelturm", description="Test", duration_hours=2.0)
    assert act.place_id is None

    rest = Restaurant(name="Café Test", cuisine="French", price_range="€€")
    assert rest.place_id is None

    acc = StopAccommodation(name="Hotel Test", type="hotel", price_per_night_chf=100, total_price_chf=200)
    assert acc.place_id is None

    stop = TravelStop(id=1, region="Paris", country="FR", arrival_day=1, nights=2)
    assert stop.place_id is None

    opt = AccommodationOption(id="acc_1", name="Test", type="hotel", price_per_night_chf=100,
                              total_price_chf=200, teaser="Nice")
    assert opt.place_id is None


def test_place_id_can_be_set():
    from models.travel_response import StopActivity
    act = StopActivity(name="Louvre", description="Museum", duration_hours=3.0,
                       place_id="ChIJD7fiBh9u5kcRYJSMaMOCCwQ")
    assert act.place_id == "ChIJD7fiBh9u5kcRYJSMaMOCCwQ"


# ---------------------------------------------------------------------------
# StopActivity age fields
# ---------------------------------------------------------------------------

def test_stop_activity_age_fields_default_none():
    from models.travel_response import StopActivity
    act = StopActivity(name="Streichelzoo", description="Tiere füttern", duration_hours=1.5)
    assert act.min_age is None
    assert act.age_group is None
    assert act.suitable_for_children is False


def test_stop_activity_age_fields_set():
    from models.travel_response import StopActivity
    act = StopActivity(
        name="Kindermuseum", description="Interaktives Museum",
        duration_hours=2.0, price_chf=15.0,
        suitable_for_children=True, min_age=3, age_group="ab 3 Jahre",
    )
    assert act.min_age == 3
    assert act.age_group == "ab 3 Jahre"
    assert act.suitable_for_children is True


# ---------------------------------------------------------------------------
# ZoneBBox
# ---------------------------------------------------------------------------

from models.trip_leg import (ZoneBBox, ExploreStop,
                              RegionPlanItem, RegionPlan, ReplaceRegionRequest, RecomputeRegionsRequest, TripLeg)
from models.via_point import ViaPoint
from datetime import date


class TestZoneBBox:
    def test_valid_bbox(self):
        bbox = ZoneBBox(north=42.0, south=36.0, east=28.0, west=20.0, zone_label="Griechenland")
        assert bbox.zone_label == "Griechenland"

    def test_south_must_be_less_than_north(self):
        with pytest.raises(ValueError, match="south must be less than north"):
            ZoneBBox(north=36.0, south=42.0, east=28.0, west=20.0, zone_label="X")

    def test_lat_bounds(self):
        with pytest.raises(ValueError):
            ZoneBBox(north=91.0, south=36.0, east=28.0, west=20.0, zone_label="X")


class TestExploreStop:
    def test_valid(self):
        s = ExploreStop(name="Athen", lat=37.97, lon=23.72,
                        suggested_nights=3, significance="anchor")
        assert s.significance == "anchor"
        assert s.logistics_note == ""

    def test_nights_bounds(self):
        with pytest.raises(ValueError):
            ExploreStop(name="X", lat=0, lon=0, suggested_nights=0, significance="anchor")

    def test_invalid_significance(self):
        with pytest.raises(ValueError):
            ExploreStop(name="X", lat=0, lon=0, suggested_nights=1, significance="unknown")


class TestRegionPlanItem:
    def test_valid(self):
        item = RegionPlanItem(name="Tessin", lat=46.2, lon=8.95, reason="Seen")
        assert item.name == "Tessin"

    def test_name_too_long(self):
        with pytest.raises(ValueError):
            RegionPlanItem(name="x" * 201, lat=46.2, lon=8.95, reason="ok")


class TestRegionPlan:
    def test_valid(self):
        plan = RegionPlan(
            regions=[RegionPlanItem(name="Tessin", lat=46.2, lon=8.95, reason="Seen")],
            summary="Kurztrip"
        )
        assert len(plan.regions) == 1

    def test_empty_regions_rejected(self):
        with pytest.raises(ValueError):
            RegionPlan(regions=[], summary="Leer")

    def test_summary_too_long(self):
        with pytest.raises(ValueError):
            RegionPlan(
                regions=[RegionPlanItem(name="X", lat=0, lon=0, reason="ok")],
                summary="x" * 1001
            )


class TestReplaceRegionRequest:
    def test_valid(self):
        r = ReplaceRegionRequest(index=0, instruction="Ersetze durch Wallis")
        assert r.index == 0

    def test_negative_index_rejected(self):
        with pytest.raises(ValueError):
            ReplaceRegionRequest(index=-1, instruction="test")


class TestRecomputeRegionsRequest:
    def test_valid(self):
        r = RecomputeRegionsRequest(instruction="Mehr Küste")
        assert r.instruction == "Mehr Küste"

    def test_empty_instruction_allowed(self):
        # Empty string is allowed — no min_length constraint
        r = RecomputeRegionsRequest(instruction="")
        assert r.instruction == ""


class TestTripLeg:
    def _transit_leg(self, **kwargs):
        defaults = dict(
            leg_id="leg-0",
            start_location="Liestal",
            end_location="Lyon",
            start_date=date(2026, 6, 12),
            end_date=date(2026, 6, 15),
            mode="transit",
        )
        defaults.update(kwargs)
        return TripLeg(**defaults)

    def test_valid_transit_leg(self):
        leg = self._transit_leg()
        assert leg.total_days == 3

    def test_end_before_start_rejected(self):
        with pytest.raises(ValueError, match="end_date must be after start_date"):
            self._transit_leg(end_date=date(2026, 6, 10))

    def test_explore_without_bbox_allowed(self):
        """Explore legs without zone_bbox are valid — bbox can be resolved later."""
        leg = TripLeg(
            leg_id="leg-1",
            start_date=date(2026, 6, 15), end_date=date(2026, 7, 15),
            mode="explore", explore_description="Alpen erkunden",
        )
        assert leg.zone_bbox is None

    def test_leg_id_pattern(self):
        with pytest.raises(ValueError):
            self._transit_leg(leg_id="bad-id")

    def test_valid_explore_leg(self):
        bbox = ZoneBBox(north=42, south=36, east=28, west=20, zone_label="Griechenland")
        leg = TripLeg(
            leg_id="leg-1",
            start_date=date(2026, 6, 15), end_date=date(2026, 7, 15),
            mode="explore", zone_bbox=bbox,
            explore_description="Griechische Inseln erkunden",
        )
        assert leg.total_days == 30

    def test_via_points_in_transit_leg(self):
        vp = ViaPoint(location="Bern")
        leg = self._transit_leg(via_points=[vp])
        assert len(leg.via_points) == 1
        assert leg.via_points[0].location == "Bern"


# ---------------------------------------------------------------------------
# TravelRequest with Legs
# ---------------------------------------------------------------------------

def _make_transit_leg(leg_id="leg-0", start="Liestal", end="Lyon",
                      s=date(2026, 6, 12), e=date(2026, 6, 15), **kwargs):
    return TripLeg(leg_id=leg_id, start_location=start, end_location=end,
                   start_date=s, end_date=e, mode="transit", **kwargs)


def _make_explore_leg(leg_id="leg-1", start="Lyon", end="Athen",
                      s=date(2026, 6, 15), e=date(2026, 7, 15)):
    bbox = ZoneBBox(north=42, south=36, east=28, west=20, zone_label="Griechenland")
    return TripLeg(leg_id=leg_id, start_location=start, end_location=end,
                   start_date=s, end_date=e, mode="explore", zone_bbox=bbox,
                   explore_description="Griechische Region erkunden")


class TestTravelRequestLegs:
    def _base_req(self, legs):
        return TravelRequest(legs=legs)

    def test_derived_properties(self):
        req = self._base_req([_make_transit_leg()])
        assert req.start_location == "Liestal"
        assert req.main_destination == "Lyon"
        assert req.total_days == 3
        assert req.start_date == date(2026, 6, 12)
        assert req.end_date == date(2026, 6, 15)

    def test_multi_leg_chain(self):
        leg0 = _make_transit_leg(end="Lyon", e=date(2026, 6, 15))
        leg1 = _make_explore_leg(start="Lyon", e=date(2026, 7, 15))
        req = self._base_req([leg0, leg1])
        assert req.total_days == 33

    def test_chain_validation_location_mismatch(self):
        leg0 = _make_transit_leg(end="Lyon", e=date(2026, 6, 15))
        leg1 = _make_explore_leg(start="Paris", s=date(2026, 6, 15), e=date(2026, 7, 15))
        with pytest.raises(ValueError, match="must match leg"):
            self._base_req([leg0, leg1])

    def test_chain_validation_date_mismatch(self):
        leg0 = _make_transit_leg(end="Lyon", e=date(2026, 6, 15))
        leg1 = _make_explore_leg(start="Lyon", s=date(2026, 6, 16), e=date(2026, 7, 15))
        with pytest.raises(ValueError, match="start_date must equal"):
            self._base_req([leg0, leg1])

    def test_via_points_property_flattens_transit_legs(self):
        leg0 = _make_transit_leg(via_points=[ViaPoint(location="Bern")])
        req = self._base_req([leg0])
        assert len(req.via_points) == 1
        assert req.via_points[0].location == "Bern"


# ---------------------------------------------------------------------------
# TripLeg location mode
# ---------------------------------------------------------------------------

def test_location_leg_valid():
    """A location leg requires only start_location."""
    leg = TripLeg(
        leg_id="leg-0",
        start_location="Paris, Frankreich",
        end_location="",
        start_date=date(2026, 6, 1),
        end_date=date(2026, 6, 8),
        mode="location",
    )
    assert leg.mode == "location"
    assert leg.start_location == "Paris, Frankreich"


def test_location_leg_requires_start_location():
    """A location leg without start_location must fail validation."""
    with pytest.raises(ValidationError):
        TripLeg(
            leg_id="leg-0",
            start_location="",
            end_location="",
            start_date=date(2026, 6, 1),
            end_date=date(2026, 6, 8),
            mode="location",
        )


def test_location_leg_no_explore_description_needed():
    """A location leg must not require explore_description."""
    leg = TripLeg(
        leg_id="leg-0",
        start_location="Lissabon, Portugal",
        end_location="",
        start_date=date(2026, 6, 1),
        end_date=date(2026, 6, 8),
        mode="location",
        explore_description=None,
    )
    assert leg.explore_description is None


def test_travel_request_single_location_leg():
    """A TravelRequest with a single location leg must be valid."""
    leg = TripLeg(
        leg_id="leg-0",
        start_location="Lissabon, Portugal",
        end_location="",
        start_date=date(2026, 6, 1),
        end_date=date(2026, 6, 8),
        mode="location",
    )
    req = TravelRequest(legs=[leg], adults=2)
    assert req.start_location == "Lissabon, Portugal"
    assert req.main_destination == "Lissabon, Portugal"


def test_travel_request_location_leg_start_location_property():
    """start_location and main_destination return start_location for a location leg."""
    leg = TripLeg(
        leg_id="leg-0",
        start_location="Amsterdam, Niederlande",
        end_location="",
        start_date=date(2026, 6, 1),
        end_date=date(2026, 6, 5),
        mode="location",
    )
    req = TravelRequest(legs=[leg], adults=1)
    assert req.start_location == "Amsterdam, Niederlande"
    assert req.main_destination == "Amsterdam, Niederlande"
