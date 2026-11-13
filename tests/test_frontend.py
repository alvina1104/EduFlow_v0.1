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

    assert 'data-theme="dark" data-accent="violet"' in html
    assert 'family=Onest' in css
    assert 'family=Golos+Text' in css
    assert '--font-display:' in css
    assert 'body[data-theme=dark]' in css
    assert 'body[data-theme=light]' in css
    assert ':"violet"};' in js


def test_login_does_not_show_education_platform_badge():
    root = Path(__file__).resolve().parents[1] / "myproject" / "frontend"
    js = (root / "app.js").read_text(encoding="utf-8")
    start = js.index("function loginView(){")
    end = js.index("function render(){", start)
    login_html = js[start:end]
    assert "Платформа для обучения" not in login_html
    assert 'brand()' in login_html


def test_dark_admin_student_preview_is_static_and_clearly_labelled():
    root = Path(__file__).resolve().parents[1] / "myproject" / "frontend"
    preview = (root / "preview.html").read_text(encoding="utf-8")
    app = (root / "app.js").read_text(encoding="utf-8")
    css = (root / "styles.css").read_text(encoding="utf-8")
    assert 'ДИЗАЙН-ПРЕВЬЮ' in preview
    assert 'Нет доступа к аккаунтам, платежам или базе данных' in preview
    assert 'id="admin-screen"' in preview
    assert 'id="student-screen"' in preview
    assert 'id="admin-tab"' in preview
    assert 'id="student-tab"' in preview
    assert '<script src="/app/app.js"' not in preview
    assert 'fetch(' not in preview
    assert 'localStorage' not in preview
    assert 'data-theme="dark"' in preview
    assert 'href="/app/preview.html"' in app
    assert '.dashboard-finance' in css
    assert '.login-minimal' in css


def test_preview_static_html_is_served():
    with TestClient(edu_app) as client:
        response = client.get("/app/preview.html")
    assert response.status_code == 200
    assert "ДИЗАЙН-ПРЕВЬЮ" in response.text
    assert "admin-screen" in response.text
