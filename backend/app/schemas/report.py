"""Report schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class ReportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    format: Literal["html", "md"] = "html"


class ReportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    experiment_id: str
    created_at: datetime
    format: str
    title: str
    size_bytes: int
