"""API integration tests (rules-only mode: no API keys, fully offline)."""

import pytest
from fastapi.testclient import TestClient

from app.main import app, rate_limiter


@pytest.fixture()
def client(monkeypatch) -> TestClient:
    monkeypatch.setenv("LLM_PROVIDER", "none")
    # Generous limit so ordinary tests never trip 429; the rate-limit test
    # tightens it explicitly.
    rate_limiter.limit = 10_000
    return TestClient(app)


def test_healthz_reports_rules_only(client: TestClient) -> None:
    res = client.get("/healthz")
    assert res.status_code == 200
    assert res.json() == {"status": "ok", "llm": "rules-only"}


def test_assist_happy_path(client: TestClient) -> None:
    res = client.post(
        "/api/assist",
        json={"message": "Which gate should I use?", "role": "fan", "zone": "north"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["intent"] == "navigation"
    assert body["generated_by"] == "rules"
    assert "Gate" in body["message"]
    assert body["reasoning"]


def test_assist_medical_returns_p1(client: TestClient) -> None:
    res = client.post(
        "/api/assist", json={"message": "someone collapsed help", "zone": "south"}
    )
    body = res.json()
    assert body["priority"] == "P1"
    assert body["actions"]


def test_assist_spanish_response(client: TestClient) -> None:
    res = client.post(
        "/api/assist",
        json={"message": "tengo hambre, quiero comida", "language": "es"},
    )
    assert res.status_code == 200
    assert "fila" in res.json()["message"].lower()


def test_assist_rejects_missing_message(client: TestClient) -> None:
    assert client.post("/api/assist", json={}).status_code == 422


def test_assist_rejects_oversized_message(client: TestClient) -> None:
    res = client.post("/api/assist", json={"message": "x" * 501})
    assert res.status_code == 422


def test_assist_rejects_invalid_role(client: TestClient) -> None:
    res = client.post("/api/assist", json={"message": "hi", "role": "hacker"})
    assert res.status_code == 422


def test_assist_neutralizes_html_injection(client: TestClient) -> None:
    res = client.post(
        "/api/assist",
        json={"message": "<img src=x onerror=alert(1)> where is the gate"},
    )
    assert res.status_code == 200
    assert "<img" not in res.json()["message"]


def test_assist_unknown_zone_degrades_gracefully(client: TestClient) -> None:
    res = client.post(
        "/api/assist", json={"message": "where is the gate", "zone": "moon-base"}
    )
    assert res.status_code == 200


def test_stadium_state_shape(client: TestClient) -> None:
    body = client.get("/api/stadium/state").json()
    assert {"zones", "gates", "concessions"} <= body.keys()
    assert all(0 <= z["occupancy"] <= 1 for z in body["zones"])


def test_matches_endpoints(client: TestClient) -> None:
    assert len(client.get("/api/matches").json()) == 5
    nxt = client.get("/api/matches/next")
    assert nxt.status_code in (200, 404)  # depends on wall-clock date


def test_incident_flow(client: TestClient) -> None:
    created = client.post(
        "/api/incidents",
        json={"description": "unattended bag near gate 2", "zone": "north"},
    )
    assert created.status_code == 201
    body = created.json()
    assert body["priority"] == "P2"
    assert body["dispatch"]
    listing = client.get("/api/incidents").json()
    assert any(i["id"] == body["id"] for i in listing)


def test_incident_rejects_unknown_zone(client: TestClient) -> None:
    res = client.post(
        "/api/incidents",
        json={"description": "spill on the stairs", "zone": "not-a-zone"},
    )
    assert res.status_code == 422


def test_rate_limit_returns_429_with_security_headers(client: TestClient) -> None:
    rate_limiter.limit = 3
    try:
        responses = [
            client.post("/api/assist", json={"message": "hello gate"})
            for _ in range(6)
        ]
        limited = [r for r in responses if r.status_code == 429]
        assert limited, "expected at least one 429 after exceeding the limit"
        # Hardening headers must survive the rate-limit short-circuit too.
        assert limited[0].headers["X-Content-Type-Options"] == "nosniff"
        assert "Content-Security-Policy" in limited[0].headers
    finally:
        rate_limiter.limit = 10_000


def test_security_headers_present(client: TestClient) -> None:
    res = client.get("/healthz")
    assert res.headers["X-Content-Type-Options"] == "nosniff"
    assert "Content-Security-Policy" in res.headers


def test_index_serves_ui(client: TestClient) -> None:
    res = client.get("/")
    assert res.status_code == 200
    assert "MatchDay Copilot" in res.text
