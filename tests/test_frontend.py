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


def test_login_has_accessible_password_toggle_and_error_message():
    root = Path(__file__).resolve().parents[1] / "myproject" / "frontend"
    html = (root / "index.html").read_text(encoding="utf-8")
    js = (root / "app.js").read_text(encoding="utf-8")
    css = (root / "styles.css").read_text(encoding="utf-8")

    assert 'id="i-lock"' in html
    assert 'id="i-eye"' in html
    assert 'id="i-eye-off"' in html
    assert 'data-action="toggle-password"' in js
    assert 'aria-live="polite"' in js
    assert 'id="login-error"' in js
    assert 'response.status===401' in js
    assert 'response.status===403' in js
    assert 'type="password"' in js
    assert '.login-form-wrap' in css
    assert '.password-toggle' in css
    assert 'function logo(){' in js
    assert 'eduflow-brand-mark' in js


def test_clean_campus_theme_and_fonts():
    root = Path(__file__).resolve().parents[1] / "myproject" / "frontend"
    html = (root / "index.html").read_text(encoding="utf-8")
    css = (root / "styles.css").read_text(encoding="utf-8")
    js = (root / "app.js").read_text(encoding="utf-8")

    assert 'data-theme="light" data-accent="blue"' in html
    assert 'family=Onest' in css
    assert 'family=Golos+Text' in css
    assert '--font-display:' in css
    assert 'body[data-theme=dark]' in css
    assert 'body[data-theme=light]' in css
    assert ':"blue"};' in js
