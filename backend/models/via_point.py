"""Pydantic model for an intermediate waypoint in a trip route."""

from typing import Optional
from pydantic import BaseModel, Field
from datetime import date


class ViaPoint(BaseModel):
    location: str = Field(max_length=200)
    fixed_date: Optional[date] = None
    notes: Optional[str] = Field(default=None, max_length=500)
