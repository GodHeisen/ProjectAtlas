"""Timeline event models."""

from datetime import datetime

from pydantic import BaseModel, Field


class TimelineEvent(BaseModel):
    """A single chronological event in a geopolitical story."""

    date: str = Field(..., description="ISO date or human-readable date label.")
    title: str
    description: str
    significance: str | None = None
    sources: list[str] = Field(default_factory=list)
    sort_key: datetime | None = Field(
        default=None,
        description="Optional parsed datetime for ordering.",
    )
