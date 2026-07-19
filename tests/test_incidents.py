"""Incident triage severity mapping and escalation plans."""

import pytest

from app.models import IncidentReport, Priority, Role
from app.services.incidents import IncidentLog, dispatch_plan, triage


@pytest.mark.parametrize(
    ("description", "expected"),
    [
        ("person unconscious near block 12", Priority.P1),
        ("small fire behind the concession", Priority.P1),
        ("someone has a knife", Priority.P1),
        ("fight between fan groups", Priority.P2),
        ("unattended bag by gate 3", Priority.P2),
        ("beer spill making stairs slippery", Priority.P3),
        ("lost child near the fan shop", Priority.P3),
        ("fan asked about parking", Priority.P4),
    ],
)
def test_triage_matrix(description: str, expected: Priority) -> None:
    assert triage(description) is expected


def test_dispatch_plans_scale_with_priority() -> None:
    assert len(dispatch_plan(Priority.P1)) > len(dispatch_plan(Priority.P4))
    assert any("medical" in step.lower() for step in dispatch_plan(Priority.P1))


def test_incident_log_assigns_ids_and_plans() -> None:
    log = IncidentLog()
    first = log.report(
        IncidentReport(
            description="person collapsed at block 4",
            zone="north",
            reporter_role=Role.STEWARD,
        )
    )
    second = log.report(
        IncidentReport(description="beer spill on stairs", zone="south")
    )
    assert (first.id, second.id) == (1, 2)
    assert first.priority is Priority.P1
    assert second.priority is Priority.P3
    assert len(log.all()) == 2
