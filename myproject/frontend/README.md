# EduFlow Frontend — Motion Web

This frontend is a separate, responsive UI served by the **existing FastAPI app**.
It is built with plain HTML, CSS, and JavaScript: no Node build step or new frontend framework is required.

## What is included

- Login with the existing `POST /auth/login` and `GET /auth/me` API.
- Day / Night themes and six neon accent colors. Preferences are stored **locally per username on the browser**.
- Responsive desktop/mobile layout; on mobile the animated Motion Web branding appears above the login form.
- Admin dashboard, Students, Groups, Group detail, Student detail, Contracts, Contract detail, Payments, Schedule, Settings.
- Student dashboard, own Contracts, Payments, Schedule, Grades/Tabel, Profile with existing JPG/PNG photo upload and Settings.
- Clickable navigation: **Groups → Group → Students → Student → Contracts**, and Students → Student → Group.
- No fake student, contract, payment, or grade records. Missing data displays an empty state.

## Starting locally

Use the existing backend environment, without changing the deployment configuration:

```bash
# From repository root, after configuring your .env and PostgreSQL:
uvicorn main:edu_app --reload --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000/`.

For Docker Compose, deploy the same way you already deploy the backend and open your configured base URL. The static files are included in the backend Docker image. The existing Nginx proxy routes requests to FastAPI.

## Implementation details

- `myproject/frontend/index.html`: page shell and SVG icon sprites.
- `myproject/frontend/styles.css`: responsive layout and theme tokens.
- `myproject/frontend/app.js`: page rendering, navigation and API integration.
- `main.py`: GET `/` returns the frontend; `/app/*` serves assets.
- Existing API endpoints, database models, authentication rules, and Finik service are unchanged.

Tokens are held only in JavaScript memory and are not persisted to localStorage. Reloading the page requires a fresh login. Logout revokes the refresh token through the existing endpoint when possible.

### Permissions and known gaps

Only **admin** and **student** roles currently exist in the backend. A new Mentor or Manager role, Tabel SSO, and full editing forms are not part of this frontend change. The Tabel page is an external link; grades from `GET /study/me` are shown only when the backend integration is configured and returns data.

Admin payment balances on the interface are calculated from confirmed payments fetched through the existing API. In future a server-side aggregate endpoint may be preferable for large datasets. The user interface is read-only for financial records: payment creation and contract edits are not introduced in this PR.

Student photo upload uses the existing `PUT /students/me/photo` route, which accepts JPG/PNG up to 2 MB.

### Verification

A basic server-side static smoke test is included at `tests/test_frontend.py`. A browser walkthrough and backend-integrated API tests with the separate test database are still needed before production deployment. No production database should be changed for this UI work.


## Professional dark UI and safe design preview

The new Admin and Student dashboards use the former dark look as the baseline,
with compact payment summaries, practical navigation, accessible SVG icons and
Onest/Golos Text typography. A simplified login layout keeps the existing
FastAPI `POST /auth/login` and `GET /auth/me` calls unchanged.

Open `http://127.0.0.1:8000/app/preview.html` to see **fake admin and
student dashboard screens** side-by-side with the real CSS, without requiring
a working local login. All figures in the preview are examples. The preview
does not fetch any API, write to the database, obtain a token or bypass access
checks. The real UI is still available at `http://127.0.0.1:8000/`.

Production Vercel accounts may have different password hashes from the local
FastAPI `eduflow` database; no credentials or user records are transferred or
modified by this Frontend-only change.
