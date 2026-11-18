from datetime import date
from uuid import uuid4

from myproject.database.models import Notification, User, UserRole
from myproject.services.notifications import send_payment_reminders, create_notification


def test_cash_payment_notifies_student_once(client, actors, auth_headers, contract_factory):
    contract = contract_factory()
    body = {
        "request_id": str(uuid4()), "contract_id": contract.id,
        "amount": "100.00", "payment_method": "cash"
    }
    payment = client.post("/payments/", headers=auth_headers(actors["admin"]), json=body)
    assert payment.status_code == 201
    student_headers = auth_headers(actors["student_user"])
    notifications = client.get("/notifications/", headers=student_headers)
    assert notifications.status_code == 200
    assert len(notifications.json()) == 1
    assert notifications.json()[0]["type"] == "payment_confirmed"
    assert client.get("/notifications/unread-count", headers=student_headers).json() == {"count": 1}
    assert client.get("/notifications/", headers=auth_headers(actors["admin"])).json() == []
    assert client.post("/payments/", headers=auth_headers(actors["admin"]), json=body).status_code == 201
    assert len(client.get("/notifications/", headers=student_headers).json()) == 1


def test_notification_access_is_private(client, db_session, actors, auth_headers):
    create_notification(db_session, actors["student_user"].id, "payment_due", "Срок оплаты", "Тест")
    db_session.flush()
    notification = db_session.query(Notification).filter(
        Notification.user_id == actors["student_user"].id
    ).first()
    other = User(username=f"other_{uuid4().hex[:12]}", hashed_password="not-used", role=UserRole.STUDENT)
    db_session.add(other)
    db_session.flush()
    assert client.get("/notifications/").status_code in (401, 403)
    assert client.patch(f"/notifications/{notification.id}/read", headers=auth_headers(other)).status_code == 404
    assert client.patch(f"/notifications/{notification.id}/read", headers=auth_headers(actors["student_user"])).status_code == 200
    assert client.get("/notifications/?unread_only=true", headers=auth_headers(actors["student_user"])).json() == []
    assert client.get("/notifications/unread-count", headers=auth_headers(actors["student_user"])).json() == {"count": 0}
    assert client.patch("/notifications/read-all", headers=auth_headers(other)).json() == {"updated": 0}


def test_payment_reminders_once(db_session, actors, contract_factory):
    from myproject.database.models import Contract, ContractStatus, ContractType
    from myproject.services.payment_allocation import payment_plan

    contract = contract_factory()
    contract.start_date = date(2031, 1, 1)
    db_session.flush()
    assert contract.status == ContractStatus.ACTIVE
    assert contract.type == ContractType.ACADEMY
    assert payment_plan(contract)[0]["due_date"] == date(2031, 1, 15)
    assert send_payment_reminders(db_session, today=date(2031, 1, 12)) == 1
    assert send_payment_reminders(db_session, today=date(2031, 1, 12)) == 0
    assert send_payment_reminders(db_session, today=date(2031, 1, 16)) == 1
    assert send_payment_reminders(db_session, today=date(2031, 1, 16)) == 0
    notifications = db_session.query(Notification).filter(
        Notification.event_key.in_([
            f"payment_due:{contract.id}:2031-01",
            f"payment_overdue:{contract.id}:2031-01"
        ])
    ).order_by(Notification.id).all()
    assert [n.type for n in notifications] == ["payment_due", "payment_overdue"]


def test_schedule_edit_notifies_group_not_noop(client, actors, auth_headers):
    headers = auth_headers(actors["admin"])
    payload = {
        "group_id": actors["group_a"].id, "title": "Python",
        "weekday": "Monday", "start_time": "10:00:00", "end_time": "11:00:00"
    }
    schedule = client.post("/schedules/", headers=headers, json=payload)
    assert schedule.status_code == 201
    schedule_id = schedule.json()["id"]
    assert client.put(f"/schedules/{schedule_id}", headers=headers, json=payload).status_code == 200
    assert client.get("/notifications/", headers=auth_headers(actors["student_user"])).json() == []
    changed = {**payload, "start_time": "11:00:00", "end_time": "12:00:00"}
    assert client.put(f"/schedules/{schedule_id}", headers=headers, json=changed).status_code == 200
    notifications = client.get("/notifications/", headers=auth_headers(actors["student_user"])).json()
    assert len(notifications) == 1
    assert notifications[0]["type"] == "schedule_changed"


def test_old_unpaid_months_do_not_trigger_mass_reminders(db_session, contract_factory):
    contract = contract_factory()
    before = db_session.query(Notification).filter(
        Notification.event_key.like(f"%:{contract.id}:%")
    ).count()
    assert send_payment_reminders(db_session, today=date(2026, 11, 18)) == 0
    assert db_session.query(Notification).filter(
        Notification.event_key.like(f"%:{contract.id}:%")
    ).count() == before


def test_payment_reminders_do_not_send_before_three_day_window(db_session, contract_factory):
    contract = contract_factory()
    contract.start_date = date(2032, 1, 1)
    db_session.flush()
    before = db_session.query(Notification).filter(
        Notification.event_key.like(f"%:{contract.id}:%")
    ).count()
    assert send_payment_reminders(db_session, today=date(2032, 1, 11)) == 0
    assert db_session.query(Notification).filter(
        Notification.event_key.like(f"%:{contract.id}:%")
    ).count() == before
