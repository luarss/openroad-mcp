"""Timing analysis data models"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class LoadResult(BaseModel):
    """Result of ODB loading operation"""

    success: bool
    design_name: str
    odb_path: str
    sdc_path: str | None
    message: str
    loaded_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    error: str | None = None


class TimingResult(BaseModel):
    """Result of timing query execution"""

    command: str
    data: dict[str, Any]
    cached: bool
    execution_time: float
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
    error: str | None = None


class PathInfo(BaseModel):
    """Basic timing path information"""

    startpoint: str
    endpoint: str
    path_group: str
    slack: float
    path_type: str | None = None
    arrival: float | None = None
    required: float | None = None


class TimingSummary(BaseModel):
    """Quick timing summary"""

    design_name: str
    wns: float | None = None
    tns: float | None = None
    failing_endpoints: int | None = None
    total_endpoints: int | None = None
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
