"""Decision engine: context-sensitive, explainable decisions."""

from app.core import engine
from app.models import AssistRequest, Intent, Priority, Role


def make_request(**overrides) -> AssistRequest:
    base = {"message": "where is the gate", "role": Role.FAN}
    base.update(overrides)
    return AssistRequest(**base)


def test_every_decision_has_reasoning() -> None:
    decision = engine.decide(make_request(), tick=3)
    assert decision.reasoning, "explainability trace must never be empty"
    assert "Intent" in decision.reasoning[0]


def test_navigation_picks_least_loaded_gate() -> None:
    from app.services import stadium

    decision = engine.decide(make_request(), tick=3)
    chosen = decision.facts["gate"]
    loads = stadium.gate_loads(3)
    assert chosen["load"] == min(loads.values())


def test_accessibility_needs_forces_step_free_gate() -> None:
    for tick in range(0, 40, 4):  # across many telemetry states
        decision = engine.decide(
            make_request(accessibility_needs=True), tick=tick
        )
        assert decision.facts["gate"]["step_free"] is True


def test_zone_preference_limits_gate_choice() -> None:
    decision = engine.decide(make_request(zone="south"), tick=5)
    assert decision.facts["gate"]["zone"] == "south"


def test_medical_is_always_p1_with_dispatch_actions() -> None:
    decision = engine.decide(
        make_request(message="my friend collapsed", zone="east"), tick=1
    )
    assert decision.intent is Intent.MEDICAL
    assert decision.priority is Priority.P1
    assert any("medical team" in a.lower() for a in decision.actions)


def test_medical_station_prefers_user_zone() -> None:
    decision = engine.decide(
        make_request(message="need a medic", zone="north"), tick=1
    )
    assert decision.facts["station"]["zone"] == "north"


def test_medical_station_falls_back_to_adjacent_zone() -> None:
    # East stand has no medical post; north is adjacent and does.
    decision = engine.decide(
        make_request(message="need a medic", zone="east"), tick=1
    )
    assert decision.facts["station"]["zone"] in ("north", "south")


def test_egress_flags_surge_when_zone_is_packed() -> None:
    from app.services import stadium

    surge_tick = next(
        t for t in range(200) if stadium.occupancy(t)["north"] >= engine.SURGE_ZONE
    )
    decision = engine.decide(
        make_request(message="I want to exit now", zone="north"), tick=surge_tick
    )
    assert decision.facts["surge"] is True
    assert decision.priority is Priority.P3
    assert decision.actions


def test_crowd_query_gives_ops_interventions_but_not_fans() -> None:
    from app.services import stadium

    hot_tick = next(
        t
        for t in range(200)
        if any(v >= engine.SURGE_ZONE for v in stadium.occupancy(t).values())
    )
    ops = engine.decide(
        make_request(message="how is crowd density", role=Role.OPS), tick=hot_tick
    )
    fan = engine.decide(
        make_request(message="how is crowd density", role=Role.FAN), tick=hot_tick
    )
    assert ops.actions, "ops should get intervention playbook"
    assert not fan.actions, "fans should not receive ops interventions"


def test_food_picks_shortest_queue_in_zone() -> None:
    from app.services import stadium

    decision = engine.decide(
        make_request(message="I'm hungry, food please", zone="north"), tick=7
    )
    stand = decision.facts["stand"]
    assert stand["zone"] == "north"
    queues = stadium.queue_lengths(7)
    north_stand_ids = [
        c["id"] for c in stadium.layout()["concessions"] if c["zone"] == "north"
    ]
    assert stand["queue"] == min(queues[i] for i in north_stand_ids)


def test_unknown_intent_offers_help_menu() -> None:
    decision = engine.decide(make_request(message="xyzzy plugh"), tick=0)
    assert decision.intent is Intent.UNKNOWN
    assert decision.priority is Priority.P4
