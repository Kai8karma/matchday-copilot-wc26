"""Match schedule lookups."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

_DATA = Path(__file__).resolve().parent.parent / "data"


@lru_cache(maxsize=1)
def matches() -> list[dict[str, Any]]:
    return json.loads((_DATA / "matches.json").read_text(encoding="utf-8"))


def next_match(now: datetime | None = None) -> dict[str, Any] | None:
    """First fixture with a kickoff at or after `now` (defaults to real time)."""
    now = now or datetime.now(timezone.utc)
    upcoming = [
        m for m in matches() if datetime.fromisoformat(m["kickoff"]) >= now
    ]
    return min(upcoming, key=lambda m: m["kickoff"]) if upcoming else None
