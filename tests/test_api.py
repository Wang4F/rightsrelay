from __future__ import annotations

from fastapi.testclient import TestClient

from rightsrelay.app import app


def test_health_surface() -> None:
    response = TestClient(app).get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert "b2_configured" in body
