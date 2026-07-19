"""Incident triage: severity classification + escalation matrix.

The escalation matrix mirrors real stadium command structures: life safety
goes straight to medical dispatch and the venue control room; security risks
route to the nearest steward team; everything else is logged for ops review.
"""

from __future__ import annotations

import itertools
import re
import threading

from app.models import Incident, IncidentReport, Priority

_P1 = re.compile(
    r"\b(unconscious|collapsed|not breathing|cardiac|seizure|severe bleeding|"
    r"crush|stampede|fire|weapon|gun|knife|bomb)\b",
    re.IGNORECASE,
)
_P2 = re.compile(
    r"\b(fight|assault|threat|suspicious|unattended|intoxicated|harassment|"
    r"pitch invasion|flare)\b",
    re.IGNORECASE,
)
_P3 = re.compile(
    r"\b(spill|broken|blocked|leak|fault|outage|overcrowd|queue|lost child)\b",
    re.IGNORECASE,
)

_DISPATCH: dict[Priority, list[str]] = {
    Priority.P1: [
        "Dispatch nearest medical team immediately",
        "Notify venue control room (channel 1)",
        "Clear a corridor for emergency access",
    ],
    Priority.P2: [
        "Send nearest steward pair to assess",
        "Notify security supervisor (channel 2)",
        "Begin camera tracking of the area",
    ],
    Priority.P3: [
        "Log for facilities/ops team",
        "Assign roving steward within 10 minutes",
    ],
    Priority.P4: ["Log for end-of-day operations review"],
}


def triage(description: str) -> Priority:
    """Map free-text incident description to a response priority."""
    if _P1.search(description):
        return Priority.P1
    if _P2.search(description):
        return Priority.P2
    if _P3.search(description):
        return Priority.P3
    return Priority.P4


def dispatch_plan(priority: Priority) -> list[str]:
    return list(_DISPATCH[priority])


class IncidentLog:
    """Thread-safe in-memory incident store (stand-in for a real queue/DB)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._items: list[Incident] = []
        self._ids = itertools.count(1)

    def report(self, report: IncidentReport) -> Incident:
        priority = triage(report.description)
        incident = Incident(
            id=next(self._ids),
            description=report.description,
            zone=report.zone,
            reporter_role=report.reporter_role,
            priority=priority,
            dispatch=dispatch_plan(priority),
        )
        with self._lock:
            self._items.append(incident)
        return incident

    def all(self) -> list[Incident]:
        with self._lock:
            return list(self._items)
