"""Project input and result models."""

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel, Field

from app.core.enums import InputType


class ProjectInput(BaseModel):
    """User-provided input that starts a documentary project."""

    input_type: InputType
    content: str = Field(..., min_length=1, description="Topic text, URL, or transcript.")
    title: str | None = Field(default=None, description="Optional display title override.")


class ProjectResult(BaseModel):
    """Summary of a completed pipeline run."""

    project_id: str = Field(default_factory=lambda: uuid4().hex[:12])
    slug: str
    project_dir: Path
    input: ProjectInput
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    research_dir: Path | None = None
    script_dir: Path | None = None
    status: str = "phase1_complete"
    notes: list[str] = Field(default_factory=list)
