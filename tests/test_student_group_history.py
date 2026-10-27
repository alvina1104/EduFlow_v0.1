"""Isolated API tests: in-memory SQLite, never the production database."""
from datetime import date

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from myproject.api.groups import groups_router
from myproject.api.students import students_router
from myproject.core.dependencies import get_current_user
from myproject.database.db import get_db
from myproject.database.models import (
    Base, Group, Student, StudentGroupHistory,
    StudentGroupHistoryKind, User, UserRole,
)


@pytest.fixture
def api():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(conn, record):
        cursor = conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    with Session.begin() as db:
        admin = User(username="admin_test", hashed_password="not-used", role=UserRole.ADMIN, is_active=True)
        learner = User(username="student_test", hashed_password="not-used", role=UserRole.STUDENT, is_active=True)
        old_group = Group(name="A", course_name="Python", start_date=date(2026, 9, 1))
        new_group = Group(name="B", course_name="Python", start_date=date(2026, 9, 1))
        db.add_all([admin, learner, old_group, new_group])
        db.flush()
        student = Student(user_id=learner.id, group_id=old_group.id, student_number="ST-TEST-1")
        other = Student(user_id=admin.id, group_id=None, student_number="ST-TEST-2")
        db.add_all([student, other])
        db.flush()
        db.add(StudentGroupHistory(
            student_id=student.id, group_id=old_group.id,
            kind=StudentGroupHistoryKind.ENROLLMENT, from_date=date(2026, 9, 1),
        ))
        ids = {
            "admin": admin.id, "learner": learner.id,
            "student": student.id, "other": other.id,
            "old_group": old_group.id, "new_group": new_group.id,
        }

    app = FastAPI()
    app.include_router(students_router)
    app.include_router(groups_router)

    def override_db():
        with Session() as db:
            yield db

    current = {"user_id": ids["admin"]}

    def override_user():
        with Session() as db:
            return db.get(User, current["user_id"])

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = override_user
    client = TestClient(app)
    yield client, Session, ids, current, app
    client.close()
    engine.dispose()


def test_transfer_and_history_are_atomic_and_repeat_is_idempotent(api):
    client, Session, ids, current, app = api
    url = f"/students/{ids['student']}"
    response = client.patch(url, json={"group_id": ids["new_group"], "student_number": "ST-NEW"})
    assert response.status_code == 200, response.text
    assert response.json()["group_id"] == ids["new_group"]
    assert response.json()["student_number"] == "ST-NEW"

    history = client.get(f"{url}/groups")
    assert history.status_code == 200
    entries = history.json()
    assert len(entries) == 2
    assert [entry["kind"] for entry in entries] == ["enrollment", "transfer"]
    assert entries[0]["to_date"] is not None
    assert entries[1]["to_date"] is None
    assert entries[1]["group"]["name"] == "B"

    assert client.patch(url, json={"group_id": ids["new_group"]}).status_code == 200
    assert len(client.get(f"{url}/groups").json()) == 2

    with Session() as db:
        student = db.get(Student, ids["student"])
        assert student.id == ids["student"]
        assert student.group_id == ids["new_group"]


def test_remove_group_then_reassign_keeps_full_history(api):
    client, Session, ids, current, app = api
    url = f"/students/{ids['student']}"
    assert client.patch(url, json={"group_id": None}).status_code == 200
    assert client.patch(url, json={"group_id": ids["new_group"]}).status_code == 200
    entries = client.get(f"{url}/groups").json()
    assert len(entries) == 2
    assert entries[0]["to_date"] is not None
    assert entries[1]["kind"] == "transfer"
    assert entries[1]["to_date"] is None


def test_invalid_updates_leave_data_unchanged(api):
    client, Session, ids, current, app = api
    url = f"/students/{ids['student']}"
    assert client.patch(url, json={"group_id": 999999}).status_code == 404
    assert client.patch(url, json={"student_number": "ST-TEST-2"}).status_code == 409
    assert client.patch(url, json={"student_number": None}).status_code == 422
    assert client.patch("/students/999999", json={"group_id": ids["new_group"]}).status_code == 404
    with Session() as db:
        student = db.get(Student, ids["student"])
        assert student.group_id == ids["old_group"]
        assert student.student_number == "ST-TEST-1"
        assert db.query(StudentGroupHistory).filter_by(student_id=student.id).count() == 1


def test_history_permissions_and_auth(api):
    client, Session, ids, current, app = api
    current["user_id"] = ids["learner"]
    assert client.patch(f"/students/{ids['student']}", json={"group_id": None}).status_code == 403
    assert client.get(f"/students/{ids['student']}/groups").status_code == 403
    own_history = client.get("/students/me/groups")
    assert own_history.status_code == 200
    assert len(own_history.json()) == 1

    # With the authentication override removed, an absent token must be 401.
    app.dependency_overrides.pop(get_current_user)
    assert client.get(f"/students/{ids['student']}/groups").status_code == 401


def test_cannot_delete_historical_group(api):
    client, Session, ids, current, app = api
    assert client.patch(f"/students/{ids['student']}", json={"group_id": ids["new_group"]}).status_code == 200
    result = client.delete(f"/groups/{ids['old_group']}")
    assert result.status_code == 409
    with Session() as db:
        assert db.get(Group, ids["old_group"]) is not None
