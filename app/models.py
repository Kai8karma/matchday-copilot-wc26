"""Pydantic models shared across the API and decision engine."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class Role(str, Enum):
    """Who is talking to the assistant. Drives tone and available actions."""

    FAN = "fan"
    OPS = "ops"
    STEWARD = "steward"


class Language(str, Enum):
    """Host-nation languages for World Cup 2026 (USA / Canada / Mexico)."""

    EN = "en"
    ES = "es"
    FR = "fr"


class Intent(str, Enum):
    NAVIGATION = "navigation"
    EGRESS = "egress"
    FOOD = "food"
    MEDICAL = "medical"
    SECURITY = "security"
    CROWD = "crowd"
    MATCH_INFO = "match_info"
    ACCESSIBILITY = "accessibility"
    FAQ = "faq"
    UNKNOWN = "unknown"


class Priority(str, Enum):
    P1 = "P1"  # life safety — immediate dispatch
    P2 = "P2"  # security risk — steward response
    P3 = "P3"  # operational — monitor and act
    P4 = "P4"  # informational


class AssistRequest(BaseModel):
    """A single assistant turn. Everything except the message is context."""

    message: str = Field(min_length=1, max_length=500)
    role: Role = Role.FAN
    language: Language = Language.EN
    zone: str | None = Field(default=None, max_length=32)
    accessibility_needs: bool = False


class AssistResponse(BaseModel):
    intent: Intent
    priority: Priority
    message: str
    reasoning: list[str]
    actions: list[str] = []
    generated_by: str = "rules"  # "rules" or the LLM provider name


class IncidentReport(BaseModel):
    description: str = Field(min_length=3, max_length=500)
    zone: str = Field(max_length=32)
    reporter_role: Role = Role.STEWARD


class Incident(BaseModel):
    id: int
    description: str
    zone: str
    reporter_role: Role
    priority: Priority
    dispatch: list[str]
    status: str = "open"
