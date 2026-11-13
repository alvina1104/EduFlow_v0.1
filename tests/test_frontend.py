"""Smoke checks for the new frontend. Do not require production data or a DB connection."""
from pathlib import Path

from fastapi.testclient import TestClient

from main import edu_app


def test_frontend_entry_is_served():
    with TestClient(edu_app) as client:
        response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Motion Web" in response.text
    assert "/app/app.js" in response.text


def test_frontend_static_assets_are_served():
    with TestClient(edu_app) as client:
        js = client.get("/app/app.js")
        css = client.get("/app/styles.css")
    assert js.status_code == 200
    assert css.status_code == 200
    assert "function detailStudentView()" in js.text
    assert "function groupView()" in js.text
    assert "data-theme=light" in css.text
    assert "data-theme=dark" in css.text


def test_frontend_files_exist():
    root = Path(__file__).resolve().parents[1] / "myproject" / "frontend"
    for filename in ("index.html", "styles.css", "app.js"):
        assert (root / filename).is_file()
