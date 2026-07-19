"""Stadium state: static layout + simulated live occupancy telemetry.

Real deployments would ingest turnstile counts and CV crowd estimates; here a
deterministic simulator (seeded, time-stepped) stands in so the whole system
runs — and is testable — with zero external services.
"""

from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path
from typing import Any

_DATA = Path(__file__).resolve().parent.parent / "data"


@lru_cache(maxsize=1)
def layout() -> dict[str, Any]:
    """Static stadium layout, loaded once."""
    return json.loads((_DATA / "stadium.json").read_text(encoding="utf-8"))


def zone_ids() -> list[str]:
    return [z["id"] for z in layout()["zones"]]


def occupancy(tick: int) -> dict[str, float]:
    """Fraction full (0..1) per zone at a simulation tick.

    Deterministic: a slow sine wave (arrival/egress cycle) plus a per-zone
    phase offset. Same tick always gives the same picture, which makes
    decision paths reproducible in tests.
    """
    result: dict[str, float] = {}
    for i, zone in enumerate(layout()["zones"]):
        phase = i * 1.3
        wave = 0.55 + 0.4 * math.sin(tick / 7.0 + phase)
        result[zone["id"]] = round(min(1.0, max(0.05, wave)), 2)
    return result


def gate_loads(tick: int) -> dict[str, float]:
    """Load (0..1) per gate, derived from its zone's occupancy."""
    occ = occupancy(tick)
    loads: dict[str, float] = {}
    for j, gate in enumerate(layout()["gates"]):
        jitter = 0.15 * math.sin(tick / 5.0 + j * 2.1)
        loads[gate["id"]] = round(min(1.0, max(0.0, occ[gate["zone"]] + jitter)), 2)
    return loads


def queue_lengths(tick: int) -> dict[str, int]:
    """Estimated people waiting per concession stand."""
    occ = occupancy(tick)
    return {
        c["id"]: int(occ[c["zone"]] * 40 + (tick + k * 7) % 9)
        for k, c in enumerate(layout()["concessions"])
    }


def state(tick: int) -> dict[str, Any]:
    """Full live snapshot used by the ops dashboard and decision engine."""
    lay = layout()
    occ = occupancy(tick)
    loads = gate_loads(tick)
    queues = queue_lengths(tick)
    return {
        "stadium": lay["name"],
        "tick": tick,
        "zones": [
            {**z, "occupancy": occ[z["id"]], "alert": occ[z["id"]] >= 0.9}
            for z in lay["zones"]
        ],
        "gates": [{**g, "load": loads[g["id"]]} for g in lay["gates"]],
        "concessions": [{**c, "queue": queues[c["id"]]} for c in lay["concessions"]],
    }
