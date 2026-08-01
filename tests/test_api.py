from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from rightsrelay.app import app, settings


def test_health_surface() -> None:
    response = TestClient(app).get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert "b2_configured" in body


@pytest.mark.parametrize(
    ("seed_status", "expected_problem"),
    [
        ("pending", "demo-seed-not-ready"),
        ("running", "demo-seed-not-ready"),
        ("error", "demo-seed-failed"),
    ],
)
def test_ready_waits_for_enabled_demo_seed(
    monkeypatch: pytest.MonkeyPatch,
    seed_status: str,
    expected_problem: str,
) -> None:
    monkeypatch.setattr(settings, "seed_demo", True)
    monkeypatch.setattr(app.state, "seed_status", seed_status, raising=False)

    response = TestClient(app).get("/ready")

    assert response.status_code == 503
    assert response.json()["problems"] == [expected_problem]


def test_ready_accepts_completed_demo_seed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "seed_demo", True)
    monkeypatch.setattr(app.state, "seed_status", "ready", raising=False)

    response = TestClient(app).get("/ready")

    assert response.status_code == 200
    assert response.json()["problems"] == []


def test_ready_ignores_seed_status_when_demo_seed_is_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "seed_demo", False)
    monkeypatch.setattr(app.state, "seed_status", "disabled", raising=False)

    response = TestClient(app).get("/ready")

    assert response.status_code == 200
    assert response.json()["problems"] == []
