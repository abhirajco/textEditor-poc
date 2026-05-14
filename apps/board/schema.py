"""
board/schemas.py
Pydantic v2 schemas for request validation in the board app.

Usage in views:
    from .schemas import CampaignCreateSchema, TaskCreateSchema, ...
    from pydantic import ValidationError as PydanticValidationError

    def post(self, request):
        try:
            payload = CampaignCreateSchema.model_validate(request.data)
        except PydanticValidationError as e:
            return Response({"errors": e.errors()}, status=400)
        # use payload.title, payload.start_date, etc.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from typing import Literal, Optional

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    UUID4,
    field_validator,
    model_validator,
)


# ---------------------------------------------------------------------------
# Shared enums / literals
# ---------------------------------------------------------------------------

PriorityType = Literal["low", "medium", "high"]
CampaignStatusType = Literal["planning", "in_progress", "upcoming"]
TaskStatusType = Literal["to_do", "in_progress", "completed", "in_review"]


# ---------------------------------------------------------------------------
# Campaign schemas
# ---------------------------------------------------------------------------

class CampaignCreateSchema(BaseModel):
    """Validates POST /campaigns/ request body."""

    model_config = ConfigDict(str_strip_whitespace=True)

    title: str = Field(..., min_length=1, max_length=255)
    description: str = Field(..., min_length=1)
    campaign_type: str = Field(default="", max_length=255)
    priority: PriorityType = Field(default="medium")
    status: CampaignStatusType = Field(default="planning")
    location: str = Field(default="", max_length=255)
    tags: str = Field(
        default="",
        max_length=500,
        description="Comma-separated tags e.g. design,ux,launch",
    )
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    max_hierarchy_level: int = Field(default=2, ge=1)

    @model_validator(mode="after")
    def end_after_start(self) -> "CampaignCreateSchema":
        if self.start_date and self.end_date:
            if self.end_date < self.start_date:
                raise ValueError("end_date must be on or after start_date.")
        return self


class CampaignUpdateSchema(BaseModel):
    """Validates PATCH /campaigns/<id>/ request body (all fields optional)."""

    model_config = ConfigDict(str_strip_whitespace=True)

    title: Optional[str] = Field(default=None, min_length=1, max_length=255)
    description: Optional[str] = Field(default=None, min_length=1)
    campaign_type: Optional[str] = Field(default=None, max_length=255)
    priority: Optional[PriorityType] = None
    status: Optional[CampaignStatusType] = None
    location: Optional[str] = Field(default=None, max_length=255)
    tags: Optional[str] = Field(default=None, max_length=500)
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    max_hierarchy_level: Optional[int] = Field(default=None, ge=1)

    @model_validator(mode="after")
    def end_after_start(self) -> "CampaignUpdateSchema":
        if self.start_date and self.end_date:
            if self.end_date < self.start_date:
                raise ValueError("end_date must be on or after start_date.")
        return self


# ---------------------------------------------------------------------------
# Event schemas
# ---------------------------------------------------------------------------

class EventCreateSchema(BaseModel):
    """Validates POST /campaigns/<id>/events/ request body."""

    model_config = ConfigDict(str_strip_whitespace=True)

    title: str = Field(..., min_length=1, max_length=255)
    description: str = Field(default="")
    event_type: str = Field(default="", max_length=255)
    priority: PriorityType = Field(default="medium")
    status: CampaignStatusType = Field(default="planning")
    location: str = Field(default="", max_length=255)
    tags: str = Field(default="", max_length=500)
    start_date: Optional[date] = None
    end_date: Optional[date] = None

    @model_validator(mode="after")
    def end_after_start(self) -> "EventCreateSchema":
        if self.start_date and self.end_date:
            if self.end_date < self.start_date:
                raise ValueError("end_date must be on or after start_date.")
        return self


class EventUpdateSchema(BaseModel):
    """Validates PATCH /events/<id>/ request body."""

    model_config = ConfigDict(str_strip_whitespace=True)

    title: Optional[str] = Field(default=None, min_length=1, max_length=255)
    description: Optional[str] = None
    event_type: Optional[str] = Field(default=None, max_length=255)
    priority: Optional[PriorityType] = None
    status: Optional[CampaignStatusType] = None
    location: Optional[str] = Field(default=None, max_length=255)
    tags: Optional[str] = Field(default=None, max_length=500)
    start_date: Optional[date] = None
    end_date: Optional[date] = None

    @model_validator(mode="after")
    def end_after_start(self) -> "EventUpdateSchema":
        if self.start_date and self.end_date:
            if self.end_date < self.start_date:
                raise ValueError("end_date must be on or after start_date.")
        return self


# ---------------------------------------------------------------------------
# Task schemas
# ---------------------------------------------------------------------------

def _parse_duration(value: object) -> Optional[timedelta]:
    """
    Accept either a timedelta or an ISO-8601 duration string
    like "PT2H30M" or a plain seconds integer.
    Returns None if value is None/empty string.
    """
    if value is None or value == "":
        return None
    if isinstance(value, timedelta):
        return value
    if isinstance(value, (int, float)):
        return timedelta(seconds=value)
    if isinstance(value, str):
        # support "HH:MM:SS" (Django DurationField default representation)
        parts = value.split(":")
        if len(parts) == 3:
            try:
                h, m, s = int(parts[0]), int(parts[1]), float(parts[2])
                return timedelta(hours=h, minutes=m, seconds=s)
            except ValueError:
                pass
        # support plain seconds as string
        try:
            return timedelta(seconds=float(value))
        except ValueError:
            pass
    raise ValueError(
        f"Cannot parse duration from {value!r}. "
        "Use 'HH:MM:SS', seconds as number, or a timedelta."
    )


class TaskCreateSchema(BaseModel):
    """Validates POST /tasks/ (or /campaigns/<id>/tasks/) request body."""

    model_config = ConfigDict(str_strip_whitespace=True)

    title: str = Field(..., min_length=1, max_length=255)
    description: str = Field(default="")
    campaign: UUID4
    event: Optional[UUID4] = None
    parent_task: Optional[UUID4] = None
    tags: str = Field(default="", max_length=500)
    priority: PriorityType = Field(default="medium")
    marketing_type: str = Field(default="", max_length=255)
    status: TaskStatusType = Field(default="to_do")
    due_date: Optional[date] = None
    launch_date: Optional[date] = None
    estimated_hours: Optional[timedelta] = None
    completed_hours: Optional[timedelta] = None
    assigned_to: Optional[UUID4] = None

    @field_validator("estimated_hours", "completed_hours", mode="before")
    @classmethod
    def coerce_duration(cls, v: object) -> Optional[timedelta]:
        return _parse_duration(v)

    @model_validator(mode="after")
    def launch_after_due(self) -> "TaskCreateSchema":
        if self.due_date and self.launch_date:
            if self.launch_date < self.due_date:
                raise ValueError("launch_date should not be before due_date.")
        return self


class TaskUpdateSchema(BaseModel):
    """
    Validates PATCH /tasks/<id>/ request body.
    Only the fields that views.TaskUpdateView allows to be edited.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    title: Optional[str] = Field(default=None, min_length=1, max_length=255)
    description: Optional[str] = None
    tags: Optional[str] = Field(default=None, max_length=500)
    priority: Optional[PriorityType] = None
    marketing_type: Optional[str] = Field(default=None, max_length=255)
    status: Optional[TaskStatusType] = None
    due_date: Optional[date] = None
    launch_date: Optional[date] = None
    estimated_hours: Optional[timedelta] = None
    completed_hours: Optional[timedelta] = None

    @field_validator("estimated_hours", "completed_hours", mode="before")
    @classmethod
    def coerce_duration(cls, v: object) -> Optional[timedelta]:
        return _parse_duration(v)


class TaskTransferSchema(BaseModel):
    """Validates POST /tasks/<id>/transfer/ request body."""

    transfer_to: UUID4


# ---------------------------------------------------------------------------
# Discussion schemas
# ---------------------------------------------------------------------------

class DiscussionCreateSchema(BaseModel):
    """Validates POST /tasks/<id>/discussion/ request body."""

    model_config = ConfigDict(str_strip_whitespace=True)

    message: str = Field(..., min_length=1)


# ---------------------------------------------------------------------------
# Query-param schemas  (use model_validate(dict(request.query_params)))
# ---------------------------------------------------------------------------

class TaskFilterSchema(BaseModel):
    """
    Validates GET /tasks/filter/ query parameters.
    All fields are optional; unset means "no filter".
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    search: Optional[str] = None
    status: Optional[TaskStatusType] = None
    priority: Optional[PriorityType] = None
    campaign_id: Optional[UUID4] = None
    event_id: Optional[UUID4] = None
    assigned_to: Optional[UUID4] = None
    marketing_type: Optional[str] = None
    tags: Optional[str] = None
    due_date: Optional[date] = None
    due_before: Optional[date] = None
    due_after: Optional[date] = None
    launch_date: Optional[date] = None
    launch_before: Optional[date] = None
    launch_after: Optional[date] = None
    root_only: bool = False

    @field_validator("root_only", mode="before")
    @classmethod
    def parse_bool(cls, v: object) -> bool:
        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            return v.lower() in ("true", "1", "yes")
        return bool(v)