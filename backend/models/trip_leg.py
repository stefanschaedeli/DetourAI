from __future__ import annotations
from typing import Literal, Optional
from pydantic import BaseModel, Field, model_validator
from datetime import date
from models.via_point import ViaPoint  # no circular import — via_point has no deps


class ZoneBBox(BaseModel):
    north: float = Field(ge=-90, le=90)
    south: float = Field(ge=-90, le=90)
    east: float = Field(ge=-180, le=180)
    west: float = Field(ge=-180, le=180)
    zone_label: str = Field(max_length=100)

    @model_validator(mode="after")
    def validate_bbox(self) -> "ZoneBBox":
        if self.south >= self.north:
            raise ValueError("south must be less than north")
        return self


class ExploreStop(BaseModel):
    name: str = Field(max_length=200)
    lat: float
    lon: float
    suggested_nights: int = Field(ge=1, le=14)
    significance: Literal["anchor", "scenic", "hidden_gem"]
    logistics_note: str = Field(default="", max_length=500)


class ExploreZoneAnalysis(BaseModel):
    zone_characteristics: str = Field(max_length=2000)
    preliminary_anchors: list[str] = Field(default=[])
    guided_questions: list[str] = Field(min_length=1, max_length=3)


class ExploreAnswersRequest(BaseModel):
    answers: list[str] = Field(min_length=1, max_length=3)


class TripLeg(BaseModel):
    leg_id: str = Field(pattern=r"^leg-\d+$")
    start_location: str = Field(max_length=200)
    end_location: str = Field(max_length=200)
    start_date: date
    end_date: date
    mode: Literal["transit", "explore"]
    via_points: list[ViaPoint] = Field(default=[])
    zone_bbox: Optional[ZoneBBox] = None
    zone_guidance: list[str] = Field(default=[])

    @model_validator(mode="after")
    def validate_leg(self) -> "TripLeg":
        if self.end_date <= self.start_date:
            raise ValueError("end_date must be after start_date")
        return self

    @property
    def total_days(self) -> int:
        return (self.end_date - self.start_date).days
