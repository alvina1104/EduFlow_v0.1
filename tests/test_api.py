from datetime import date
from uuid import uuid4

import pytest


@pytest.fixture
def payment_body(contract_factory):
    contract = contract_factory()
    return contract, {"request_id": str(uuid4()), "contract_id": contract.id,
                      "amount": "100.00", "payment_method": "card", "payment_month": "2026-10"}


def test_auth_login_refresh_logout_and_bad_password(client, actors):
    login = client.post("/auth/login", json={"username": actors["student_user"].username,
                                             "password": actors["password"]})
    assert login.status_code == 200
    token = login.json()
    refreshed = client.post("/auth/refresh", json={"refresh_token": token["refresh_token"]})
    assert refreshed.status_code == 200
    logout = client.post("/auth/logout", json={"refresh_token": refreshed.json()["refresh_token"]},
                         headers={"Authorization": f"Bearer {refreshed.json()['access_token']}"})
    assert logout.status_code == 200
    bad = client.post("/auth/login", json={"username": actors["student_user"].username, "password": "wrong"})
    assert bad.status_code == 401


def test_jwt_and_admin_student_permissions(client, actors, auth_headers):
    assert client.get("/students/").status_code == 401
    assert client.get("/students/", headers=auth_headers(actors["student_user"])).status_code == 403
    assert client.get("/students/", headers=auth_headers(actors["admin"])).status_code == 200
    assert client.get("/students/me", headers=auth_headers(actors["student_user"])).status_code == 200


def test_student_create_read_update_and_group_history(client, actors, auth_headers, db_session):
    suffix = uuid4().hex
    response = client.post("/students/", headers=auth_headers(actors["admin"]), json={
        "username": f"new_{suffix}", "password": "Student-password-2", "student_number": f"N{suffix}",
        "group_id": actors["group_a"].id,
    })
    assert response.status_code == 201
    student_id = response.json()["id"]
    assert client.get(f"/students/{student_id}", headers=auth_headers(actors["admin"])).status_code == 200
    updated = client.patch(f"/students/{student_id}", headers=auth_headers(actors["admin"]), json={
        "group_id": actors["group_b"].id, "student_number": f"U{suffix}"
    })
    assert updated.status_code == 200
    from myproject.database.models import StudentGroupHistory
    history = db_session.query(StudentGroupHistory).filter_by(student_id=student_id).all()
    assert len(history) == 2


def test_student_photo_upload(client, actors, auth_headers):
    from io import BytesIO
    from PIL import Image

    image = Image.new("RGB", (2, 2), color="red")
    file = BytesIO()
    image.save(file, format="JPEG")
    response = client.put("/students/me/photo", headers=auth_headers(actors["student_user"]),
                          files={"file": ("photo.jpg", file.getvalue(), "image/jpeg")})
    assert response.status_code == 200


def test_group_update_and_protect_delete_with_student(client, actors, auth_headers):
    group = actors["group_b"]
    update = client.put(f"/groups/{group.id}", headers=auth_headers(actors["admin"]), json={
        "name": "Renamed", "course_name": "Course", "start_date": "2025-01-01", "end_date": None
    })
    assert update.status_code == 200
    assert client.delete(f"/groups/{actors['group_a'].id}", headers=auth_headers(actors["admin"])).status_code == 409


def test_schedule_create_update_conflict_and_group_delete_guard(client, actors, auth_headers):
    payload = {"group_id": actors["group_b"].id, "title": "Math", "weekday": "Monday",
               "start_time": "10:00:00", "end_time": "11:00:00"}
    first = client.post("/schedules/", headers=auth_headers(actors["admin"]), json=payload)
    assert first.status_code == 201
    conflict = client.post("/schedules/", headers=auth_headers(actors["admin"]), json={**payload, "title": "Physics",
                            "start_time": "10:30:00", "end_time": "11:30:00"})
    assert conflict.status_code == 409
    updated = client.put(f"/schedules/{first.json()['id']}", headers=auth_headers(actors["admin"]),
                          json={**payload, "title": "Advanced Math"})
    assert updated.status_code == 200
    assert client.delete(f"/groups/{actors['group_b'].id}", headers=auth_headers(actors["admin"])).status_code == 409


def test_personal_info_create_update_review_and_permissions(client, actors, auth_headers):
    data = {"first_name": "Test", "last_name": "Student", "phone": "+996555123456", "birth_date": "2000-01-01"}
    response = client.put("/personal-info/me", headers=auth_headers(actors["student_user"]), json=data)
    assert response.status_code == 200
    assert client.get("/personal-info/me", headers=auth_headers(actors["admin"])).status_code == 403
    review = client.patch(f"/personal-info/{actors['student'].id}/review", headers=auth_headers(actors["admin"]),
                          json={"status": "approved"})
    assert review.status_code == 200
    assert review.json()["status"] == "approved"


def test_contract_creation_variants_payment_day_and_delete_guard(client, actors, auth_headers, contract_factory):
    payload = {"student_id": actors["student"].id, "total_amount": "1500.00", "monthly_payment": "150.00",
               "duration_months": 10, "start_date": "2025-01-01", "payment_day": 20}
    response = client.post("/contracts/", headers=auth_headers(actors["admin"]), json=payload)
    assert response.status_code == 201
    assert response.json()["payment_day"] == 20
    assert client.post("/contracts/", headers=auth_headers(actors["admin"]), json={**payload,
                           "total_amount": "900.00", "duration_months": 6, "payment_day": None}).status_code == 201
    contract = contract_factory()
    body = {"request_id": str(uuid4()), "contract_id": contract.id, "amount": "10.00", "payment_month": "2026-10"}
    assert client.post("/payments/", headers=auth_headers(actors["student_user"]), json=body).status_code == 201
    assert client.delete(f"/contracts/{contract.id}", headers=auth_headers(actors["admin"])).status_code == 409


def test_payment_idempotency_confirmation_rejection_balance_and_limits(client, actors, auth_headers, contract_factory):
    contract, body = payment_body(contract_factory)
    student_headers = auth_headers(actors["student_user"])
    admin_headers = auth_headers(actors["admin"])
    created = client.post("/payments/", headers=student_headers, json=body)
    assert created.status_code == 201
    duplicate = client.post("/payments/", headers=student_headers, json=body)
    assert duplicate.status_code == 201
    assert duplicate.json()["id"] == created.json()["id"]
    payment_id = created.json()["id"]
    confirmed = client.patch(f"/payments/{payment_id}/status", headers=admin_headers,
                             json={"status": "confirmed"})
    assert confirmed.status_code == 200
    assert client.patch(f"/payments/{payment_id}/status", headers=admin_headers,
                        json={"status": "confirmed"}).status_code == 409
    balance = client.get("/payments/my/balance", headers=student_headers)
    assert balance.status_code == 200
    assert str(balance.json()[0]["remaining_amount"]) == "900.00"

    rejected_body = {**body, "request_id": str(uuid4()), "amount": "50.00"}
    rejected = client.post("/payments/", headers=student_headers, json=rejected_body)
    assert rejected.status_code == 201
    assert client.patch(f"/payments/{rejected.json()['id']}/status", headers=admin_headers,
                        json={"status": "rejected"}).status_code == 200

    excessive = {**body, "request_id": str(uuid4()), "amount": "1001.00"}
    over_limit = client.post("/payments/", headers=admin_headers, json=excessive)
    assert over_limit.status_code == 409


def test_academic_leave_validation_overlap_and_cancellation(client, actors, auth_headers, contract_factory, db_session):
    contract = contract_factory()
    admin_headers = auth_headers(actors["admin"])
    endpoint = f"/contracts/{contract.id}/leaves"
    invalid = client.post(endpoint, headers=admin_headers, json={"start_date": "2026-10-03", "end_date": "2026-10-01"})
    assert invalid.status_code == 422
    payload = {"start_date": "2026-10-01", "end_date": "2026-10-20", "reason": "study"}
    created = client.post(endpoint, headers=admin_headers, json=payload)
    assert created.status_code == 201
    assert client.post(endpoint, headers=admin_headers,
                       json={"start_date": "2026-10-10", "end_date": "2026-10-30"}).status_code == 409
    leave_id = created.json()["id"]
    assert client.delete(f"{endpoint}/{leave_id}", headers=admin_headers).status_code == 204
    from myproject.database.models import AcademicLeave
    leave = db_session.query(AcademicLeave).filter_by(id=leave_id).one()
    assert leave.cancelled_at is not None


def test_study_api_returns_503_without_configuration(client, actors, auth_headers, monkeypatch):
    monkeypatch.delenv("PORTAL_STUDY_URL_TEMPLATE", raising=False)
    monkeypatch.delenv("PORTAL_STUDY_API_TOKEN", raising=False)
    response = client.get("/study/me", headers=auth_headers(actors["student_user"]), timeout=2)
    assert response.status_code == 503
