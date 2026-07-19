"""Context-aware decision engine.

Every branch returns a Decision with a human-readable `reasoning` trace —
the rules that fired and the live data they used. The LLM layer may rephrase
the message, but decisions themselves are always deterministic and auditable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.core import intents
from app.models import AssistRequest, Intent, Priority, Role
from app.services import incidents as incident_rules
from app.services import schedule, stadium

CROWDED_GATE = 0.75
SURGE_ZONE = 0.90


@dataclass
class Decision:
    intent: Intent
    priority: Priority
    facts: dict[str, Any]
    reasoning: list[str] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)


def decide(req: AssistRequest, tick: int) -> Decision:
    """Route a classified request through the matching rule set."""
    cls = intents.classify(req.message)
    handler = _HANDLERS.get(cls.intent, _handle_unknown)
    decision = handler(req, tick)
    decision.reasoning.insert(
        0,
        f"Intent '{cls.intent.value}' (confidence {cls.confidence}) "
        f"from terms {list(cls.matched) or 'none'}; role={req.role.value}, "
        f"zone={req.zone or 'unknown'}",
    )
    return decision


def _nearest(zone: str | None, items: list[dict[str, Any]]) -> dict[str, Any]:
    """Item in the user's zone, else in an adjacent zone, else the first."""
    if zone:
        by_zone = {i["zone"]: i for i in items}
        if zone in by_zone:
            return by_zone[zone]
        adjacency = {z["id"]: z["adjacent"] for z in stadium.layout()["zones"]}
        for adj in adjacency.get(zone, []):
            if adj in by_zone:
                return by_zone[adj]
    return items[0]


def _handle_medical(req: AssistRequest, tick: int) -> Decision:
    station = _nearest(req.zone, stadium.layout()["medic_stations"])
    return Decision(
        intent=Intent.MEDICAL,
        priority=Priority.P1,
        facts={"station": station},
        reasoning=[
            "Medical keywords always escalate to P1 regardless of phrasing",
            f"Nearest medical point to zone '{req.zone or 'unknown'}': "
            f"{station['name']} ({station['zone']})",
        ],
        actions=incident_rules.dispatch_plan(Priority.P1),
    )


def _handle_security(req: AssistRequest, tick: int) -> Decision:
    priority = incident_rules.triage(req.message)
    if priority is Priority.P4:  # security phrasing but no triage match
        priority = Priority.P2
    return Decision(
        intent=Intent.SECURITY,
        priority=priority,
        facts={"zone": req.zone},
        reasoning=[
            f"Security report triaged as {priority.value} by escalation matrix"
        ],
        actions=incident_rules.dispatch_plan(priority),
    )


def _pick_gate(req: AssistRequest, tick: int, reasoning: list[str]) -> dict[str, Any]:
    """Least-loaded suitable gate; step-free is a hard filter when needed."""
    gates = stadium.state(tick)["gates"]
    if req.accessibility_needs:
        step_free = [g for g in gates if g["step_free"]]
        reasoning.append(
            f"Accessibility needs set: restricting to step-free gates "
            f"{[g['id'] for g in step_free]}"
        )
        gates = step_free or gates
    if req.zone:
        in_zone = [g for g in gates if g["zone"] == req.zone]
        if in_zone:
            gates = in_zone
            reasoning.append(f"Preferring gates serving zone '{req.zone}'")
    best = min(gates, key=lambda g: g["load"])
    if best["load"] >= CROWDED_GATE:
        reasoning.append(
            f"All candidate gates above {CROWDED_GATE:.0%} load; "
            f"{best['id']} is still the least loaded ({best['load']:.0%})"
        )
    else:
        reasoning.append(
            f"Selected {best['id']} with lowest live load {best['load']:.0%}"
        )
    return best


def _handle_navigation(req: AssistRequest, tick: int) -> Decision:
    reasoning: list[str] = []
    gate = _pick_gate(req, tick, reasoning)
    return Decision(
        intent=Intent.NAVIGATION,
        priority=Priority.P4,
        facts={"gate": gate},
        reasoning=reasoning,
    )


def _handle_egress(req: AssistRequest, tick: int) -> Decision:
    reasoning: list[str] = []
    occ = stadium.occupancy(tick)
    zone_occ = occ.get(req.zone or "", 0.0)
    gate = _pick_gate(req, tick, reasoning)
    actions: list[str] = []
    surge = zone_occ >= SURGE_ZONE
    if surge:
        reasoning.append(
            f"Zone '{req.zone}' at {zone_occ:.0%} occupancy (≥ {SURGE_ZONE:.0%}): "
            "staggered egress advised to avoid crowd crush"
        )
        actions.append("Advise 10-minute wait or alternate route")
    return Decision(
        intent=Intent.EGRESS,
        priority=Priority.P3 if surge else Priority.P4,
        facts={"gate": gate, "surge": surge, "zone_occupancy": zone_occ},
        reasoning=reasoning,
        actions=actions,
    )


def _handle_food(req: AssistRequest, tick: int) -> Decision:
    stands = stadium.state(tick)["concessions"]
    near = [s for s in stands if req.zone in (s["zone"], None)] or stands
    best = min(near, key=lambda s: s["queue"])
    overall_best = min(stands, key=lambda s: s["queue"])
    reasoning = [
        f"Shortest queue near zone '{req.zone or 'any'}': "
        f"{best['name']} ({best['queue']} waiting)"
    ]
    if overall_best["id"] != best["id"]:
        reasoning.append(
            f"Stadium-wide shortest queue is {overall_best['name']} "
            f"({overall_best['queue']} waiting) if you're willing to walk"
        )
    return Decision(
        intent=Intent.FOOD,
        priority=Priority.P4,
        facts={"stand": best, "alternative": overall_best},
        reasoning=reasoning,
    )


def _handle_crowd(req: AssistRequest, tick: int) -> Decision:
    snapshot = stadium.state(tick)
    hot = [z for z in snapshot["zones"] if z["occupancy"] >= SURGE_ZONE]
    reasoning = [
        f"{len(hot)} zone(s) at/above {SURGE_ZONE:.0%} occupancy: "
        f"{[z['id'] for z in hot] or 'none'}"
    ]
    actions = []
    if hot and req.role in (Role.OPS, Role.STEWARD):
        actions = [
            f"Open auxiliary gates for {', '.join(z['id'] for z in hot)}",
            "Redeploy stewards to surge zones",
            "Trigger concourse PA flow guidance",
        ]
        reasoning.append("Ops role: recommending active crowd-flow interventions")
    return Decision(
        intent=Intent.CROWD,
        priority=Priority.P3 if hot else Priority.P4,
        facts={"zones": snapshot["zones"], "hot": [z["id"] for z in hot]},
        reasoning=reasoning,
        actions=actions,
    )


def _handle_match(req: AssistRequest, tick: int) -> Decision:
    match = schedule.next_match()
    return Decision(
        intent=Intent.MATCH_INFO,
        priority=Priority.P4,
        facts={"match": match},
        reasoning=["Looked up next fixture at this stadium"],
    )


def _handle_accessibility(req: AssistRequest, tick: int) -> Decision:
    acc = stadium.layout()["accessibility"]
    return Decision(
        intent=Intent.ACCESSIBILITY,
        priority=Priority.P4,
        facts={"accessibility": acc},
        reasoning=[
            f"Step-free gates: {', '.join(acc['step_free_gates'])}; "
            f"assistance desk: {acc['assistance_desk']['name']}"
        ],
    )


def _handle_faq(req: AssistRequest, tick: int) -> Decision:
    return Decision(
        intent=Intent.FAQ,
        priority=Priority.P4,
        facts={},
        reasoning=["Matched venue policy/FAQ topic"],
    )


def _handle_unknown(req: AssistRequest, tick: int) -> Decision:
    return Decision(
        intent=Intent.UNKNOWN,
        priority=Priority.P4,
        facts={},
        reasoning=["No intent matched; offering menu of things I can help with"],
    )


_HANDLERS = {
    Intent.MEDICAL: _handle_medical,
    Intent.SECURITY: _handle_security,
    Intent.NAVIGATION: _handle_navigation,
    Intent.EGRESS: _handle_egress,
    Intent.FOOD: _handle_food,
    Intent.CROWD: _handle_crowd,
    Intent.MATCH_INFO: _handle_match,
    Intent.ACCESSIBILITY: _handle_accessibility,
    Intent.FAQ: _handle_faq,
}
