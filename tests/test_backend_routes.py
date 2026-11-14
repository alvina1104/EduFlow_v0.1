"""Ensure the FastAPI application remains API-only after UI removal."""

from fastapi.testclient import TestClient

from main import edu_app


def test_legacy_frontend_is_not_served():
    with TestClient(edu_app) as client:
        assert client.get("/").status_code == 404
        assert client.get("/app/").status_code == 404
        assert client.get("/app/preview.html").status_code == 404
        assert client.get("/app/app.js").status_code == 404


def test_core_backend_routes_remain_registered():
    paths = {route.path for route in edu_app.routes}
    assert "/auth/login" in paths
    assert "/students/" in paths
    assert "/groups/" in paths
    assert "/health" in paths
    assert "/app" not in paths
