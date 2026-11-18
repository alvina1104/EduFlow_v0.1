from datetime import date
from uuid import uuid4

import pytest


@pytest.fixture
def payment_body(contract_factory):
    contract = contract_factory()
    return contract, {"request_id": str(uuid4()), "contract_id": contract.id,
                      "amount": "100.00", "payment_method": "cash", "payment_month": "2026-01"}


def test_auth_login_refresh_logout_and_bad_password(client, actors):
    login = client.post("/auth/login", json={"username": actors["student_user"].username,
                                             "password": actors["password"]})
    assert login.status_code == 200
    token = login.json()
    refreshed = client.post("/auth/refresh", json={"refresh_token": token["refresh_token"]})
    assert refreshed.status_code == 200
    replay = client.post("/auth/refresh", json={"refresh_token": token["refresh_token"]})
    assert replay.status_code == 401
    logout = client.post("/auth/logout", json={"refresh_token": refreshed.json()["refresh_token"]},
                         headers={"Authorization": f"Bearer {refreshed.json()['access_token']}"})
    assert logout.status_code == 200
    bad = client.post("/auth/login", json={"username": actors["student_user"].username, "password": "wrong"})
    assert bad.status_code == 401


def test_deactivated_user_access_and_refresh_tokens_are_rejected(
    client, actors, auth_headers
):
    login = client.post("/auth/login", json={
        "username": actors["student_user"].username,
        "password": actors["password"],
    })
    assert login.status_code == 200
    tokens = login.json()
    changed = client.put(
        f"/users/{actors['student_user'].id}",
        headers=auth_headers(actors["admin"]), json={"is_active": False},
    )
    assert changed.status_code == 200
    assert client.get("/auth/me", headers={
        "Authorization": f"Bearer {tokens['access_token']}"
    }).status_code == 401
    assert client.post("/auth/refresh", json={
        "refresh_token": tokens["refresh_token"]
    }).status_code == 401


def test_jwt_and_admin_student_permissions(client, actors, auth_headers):
    assert client.get("/students/").status_code == 401
    assert client.get("/students/", headers=auth_headers(actors["student_user"])).status_code == 403
    assert client.get("/students/", headers=auth_headers(actors["admin"])).status_code == 200
    assert client.get("/students/me", headers=auth_headers(actors["student_user"])).status_code == 200


def test_student_create_read_update_and_group_history(client, actors, auth_headers, db_session):
    suffix = uuid4().hex
    response = client.post("/students/", headers=auth_headers(actors["admin"]), json={
        "username": f"new_{suffix}", "password": "Student-password-2", "student_number": f"N{suffix[:29]}",
        "group_id": actors["group_a"].id,
    })
    assert response.status_code == 201
    student_id = response.json()["id"]
    assert client.get(f"/students/{student_id}", headers=auth_headers(actors["admin"])).status_code == 200
    updated = client.patch(f"/students/{student_id}", headers=auth_headers(actors["admin"]), json={
        "group_id": actors["group_b"].id, "student_number": f"U{suffix[:29]}"
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


def test_concurrent_schedule_moves_detect_stale_group_snapshot(
    client, actors, auth_headers, db_session, test_engine
):
    import asyncio
    import threading
    from concurrent.futures import ThreadPoolExecutor
    from datetime import date
    from datetime import time as time_of_day

    import httpx
    from sqlalchemy import event
    from sqlalchemy.orm import Session

    from main import edu_app
    from myproject.database.db import get_db
    from myproject.database.models import Group, Schedule

    suffix = uuid4().hex
    target_c = Group(
        name=f"Group C {suffix}", course_name="Course",
        start_date=date(2025, 1, 1),
    )
    db_session.add(target_c)
    db_session.flush()
    schedule = Schedule(
        group_id=actors["group_a"].id, title="Concurrent move",
        weekday="Tuesday", start_time=time_of_day(10), end_time=time_of_day(11),
    )
    db_session.add(schedule)
    db_session.flush()
    schedule_id = schedule.id
    group_a_id = actors["group_a"].id
    target_b_id = actors["group_b"].id
    target_c_id = target_c.id
    admin_headers = auth_headers(actors["admin"])
    db_session.connection().commit()

    holder = Session(test_engine)
    holder.query(Group).filter(Group.id == group_a_id).with_for_update().one()
    waiting_count = 0
    waiting_lock = threading.Lock()
    both_waiting = threading.Event()

    def observe_group_locks(conn, cursor, statement, parameters, context, executemany):
        nonlocal waiting_count
        sql = statement.lower()
        if "from groups" in sql and "for update" in sql:
            with waiting_lock:
                waiting_count += 1
                if waiting_count == 2:
                    both_waiting.set()

    event.listen(test_engine, "before_cursor_execute", observe_group_locks)

    def override_db():
        with Session(test_engine) as session:
            yield session

    edu_app.dependency_overrides[get_db] = override_db

    async def move_to(group_id, title):
        transport = httpx.ASGITransport(app=edu_app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as http_client:
            return await http_client.put(
                f"/schedules/{schedule_id}", headers=admin_headers,
                json={
                    "group_id": group_id, "title": title, "weekday": "Tuesday",
                    "start_time": "10:00:00", "end_time": "11:00:00",
                },
            )

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            move_b = executor.submit(asyncio.run, move_to(target_b_id, "Moved B"))
            move_c = executor.submit(asyncio.run, move_to(target_c_id, "Moved C"))
            assert both_waiting.wait(timeout=10), "Both updates did not reach the group lock"
            holder.commit()
            response_b = move_b.result(timeout=15)
            response_c = move_c.result(timeout=15)
    finally:
        holder.rollback()
        holder.close()
        event.remove(test_engine, "before_cursor_execute", observe_group_locks)
        edu_app.dependency_overrides.pop(get_db, None)

    assert sorted([response_b.status_code, response_c.status_code]) == [200, 409]
    with Session(test_engine) as session:
        final_schedule = session.get(Schedule, schedule_id)
        assert final_schedule.group_id in {target_b_id, target_c_id}


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
    body = {"request_id": str(uuid4()), "contract_id": contract.id, "amount": "10.00",
            "payment_method": "cash", "payment_month": "2026-01"}
    assert client.post("/payments/", headers=auth_headers(actors["admin"]), json=body).status_code == 201
    assert client.delete(f"/contracts/{contract.id}", headers=auth_headers(actors["admin"])).status_code == 409


def test_payment_idempotency_confirmation_rejection_balance_and_limits(
    client, actors, auth_headers, payment_body, db_session
):
    from decimal import Decimal
    from myproject.database.models import Payment, PaymentStatus

    contract, body = payment_body
    student_headers = auth_headers(actors["student_user"])
    admin_headers = auth_headers(actors["admin"])
    created = client.post("/payments/", headers=admin_headers, json=body)
    assert created.status_code == 201
    assert created.json()["status"] == "confirmed"
    duplicate = client.post("/payments/", headers=admin_headers, json=body)
    assert duplicate.status_code == 201
    assert duplicate.json()["id"] == created.json()["id"]
    payment_id = created.json()["id"]
    assert client.post("/payments/", headers=student_headers, json=body).status_code == 403
    assert client.patch(f"/payments/{payment_id}/status", headers=admin_headers,
                        json={"status": "confirmed"}).status_code == 409
    balance = client.get("/payments/my/balance", headers=student_headers)
    assert balance.status_code == 200
    assert balance.json()[0]["remaining_amount"] == pytest.approx(900.0)

    legacy_pending = Payment(
        contract_id=contract.id, amount=Decimal("50.00"), status=PaymentStatus.PENDING,
        payment_method="cash", payment_month="2026-09", request_id=str(uuid4()),
        created_by_user_id=actors["student_user"].id,
    )
    db_session.add(legacy_pending)
    db_session.flush()
    assert client.patch(f"/payments/{legacy_pending.id}/status", headers=admin_headers,
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
