"""Deterministic multilingual intent classification.

Keyword scoring keeps classification transparent, testable, and fast; the
LLM layer (app/llm.py) only rewrites the final answer, never the routing.
Safety-critical intents (medical, security) are checked first and win ties.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.models import Intent

# Safety-critical intents score double per matched term, so "where is the
# gate? my friend fainted" routes to medical even though navigation words
# outnumber medical ones. Order still breaks exact ties (earlier wins).
_WEIGHTS = {Intent.MEDICAL: 2, Intent.SECURITY: 2}

_KEYWORDS: list[tuple[Intent, frozenset[str]]] = [
    (
        Intent.MEDICAL,
        frozenset(
            "medic medical doctor ambulance hurt injured injury unconscious collapsed "
            "faint fainted chest pain bleeding seizure emergencia herido desmayo "
            "sangre medico blesse urgence malaise secours".split()
        ),
    ),
    (
        Intent.SECURITY,
        frozenset(
            "fight fighting weapon knife gun threat suspicious unattended stolen theft "
            "assault harassment pelea arma robo sospechoso bagarre arme vol suspect".split()
        ),
    ),
    (
        Intent.EGRESS,
        frozenset(
            "exit leave leaving egress way out salida salir sortie sortir partir".split()
        ),
    ),
    (
        Intent.ACCESSIBILITY,
        frozenset(
            "wheelchair accessible accessibility elevator ramp step-free stepfree "
            "disability sensory quiet silla rampa ascensor accesible fauteuil "
            "accessibilite ascenseur rampe".split()
        ),
    ),
    (
        Intent.NAVIGATION,
        frozenset(
            "gate seat section find where entrance enter directions route lost "
            "puerta asiento entrada donde porte siege entree ou perdu".split()
        ),
    ),
    (
        Intent.FOOD,
        frozenset(
            "food eat hungry drink beer water snack concession restaurant queue "
            "comida comer hambre bebida cerveza nourriture manger faim boisson".split()
        ),
    ),
    (
        Intent.CROWD,
        frozenset(
            "crowd occupancy density congestion busy full capacity flow surge "
            "multitud aforo lleno foule affluence dense".split()
        ),
    ),
    (
        Intent.MATCH_INFO,
        frozenset(
            "match game kickoff schedule score team play when partido equipo horario "
            "juego quien vs versus".split()
        ),
    ),
    (
        Intent.FAQ,
        frozenset(
            "bag ticket parking smoking rules allowed prohibited policy wifi lost "
            "found children water re-entry reentry bolsa boleto billet sac regle".split()
        ),
    ),
]

_TOKEN_RE = re.compile(r"[a-zàâçéèêëîïôûùüÿñáíóúü'-]+", re.IGNORECASE)


@dataclass(frozen=True)
class Classification:
    intent: Intent
    confidence: float
    matched: tuple[str, ...]


def classify(message: str) -> Classification:
    """Score the message against each intent's keyword set.

    Confidence is the share of tokens that matched the winning intent,
    clamped to [0, 1]. An empty or unmatched message yields UNKNOWN.
    """
    tokens = [t.lower() for t in _TOKEN_RE.findall(message)]
    if not tokens:
        return Classification(Intent.UNKNOWN, 0.0, ())

    best: tuple[Intent, list[str], int] | None = None
    for intent, keywords in _KEYWORDS:
        matched = [t for t in tokens if t in keywords]
        score = len(matched) * _WEIGHTS.get(intent, 1)
        if matched and (best is None or score > best[2]):
            best = (intent, matched, score)

    if best is None:
        return Classification(Intent.UNKNOWN, 0.0, ())

    intent, matched, _ = best
    confidence = min(1.0, len(matched) / max(1, len(tokens)) + 0.4)
    return Classification(intent, round(confidence, 2), tuple(dict.fromkeys(matched)))
