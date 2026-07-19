"""Intent classifier: multilingual routing and safety-first precedence."""

import pytest

from app.core.intents import classify
from app.models import Intent


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("Where is the nearest gate to my seat?", Intent.NAVIGATION),
        ("I want to leave, what's the best exit?", Intent.EGRESS),
        ("I'm hungry, where can I grab food?", Intent.FOOD),
        ("Someone collapsed and is bleeding!", Intent.MEDICAL),
        ("There's a fight breaking out in my section", Intent.SECURITY),
        ("How busy is the stadium right now?", Intent.CROWD),
        ("When is kickoff for the next match?", Intent.MATCH_INFO),
        ("Is there a wheelchair accessible entrance?", Intent.ACCESSIBILITY),
        ("What's the bag policy?", Intent.FAQ),
        ("blorp zephyr quux", Intent.UNKNOWN),
    ],
)
def test_english_intents(message: str, expected: Intent) -> None:
    assert classify(message).intent is expected


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("¿Dónde está la puerta más cercana?", Intent.NAVIGATION),
        ("Hay un herido, necesita un medico", Intent.MEDICAL),
        ("Tengo hambre, ¿dónde hay comida?", Intent.FOOD),
        ("Où est la sortie la plus proche ?", Intent.EGRESS),
        ("Il y a une bagarre dans les tribunes", Intent.SECURITY),
        ("J'ai faim, où manger ?", Intent.FOOD),
    ],
)
def test_spanish_and_french_intents(message: str, expected: Intent) -> None:
    assert classify(message).intent is expected


def test_medical_beats_navigation_on_mixed_message() -> None:
    # Safety-critical intent wins even when navigation words also appear.
    result = classify("Where is the gate? My friend fainted and is hurt near the entrance")
    assert result.intent is Intent.MEDICAL


def test_empty_message_is_unknown() -> None:
    result = classify("   !!! 123 ")
    assert result.intent is Intent.UNKNOWN
    assert result.confidence == 0.0


def test_confidence_bounds() -> None:
    result = classify("medic medic medic")
    assert 0.0 < result.confidence <= 1.0
    assert "medic" in result.matched
