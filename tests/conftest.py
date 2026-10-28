import os
from pathlib import Path

import pytest

# Prevent application imports from loading any .env file during collection.
import dotenv

dotenv.load_dotenv = lambda *args, **kwargs: False
os.environ.setdefault("SECRET_KEY", "pytest-only-secret-key")
os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://pytest:pytest@localhost:5432/eduflow_test",
)


def _ssh_tunnel_present() -> bool:
    proc = Path("/proc")
    if not proc.exists():
        return True
    for command_file in proc.glob("[0-9]*/comm"):
        try:
            if command_file.read_text().strip() in {"ssh", "autossh"}:
                return True
        except (OSError, PermissionError):
            continue
    return False


@pytest.fixture(scope="session")
def test_engine():
    """Only connect to an explicitly configured, local eduflow_test database."""
    from sqlalchemy import create_engine, text
    from sqlalchemy.engine import make_url

    database_url = os.environ.get("TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("TEST_DATABASE_URL is not set; database tests are disabled")

    url = make_url(database_url)
    if not url.drivername.startswith("postgresql"):
        pytest.fail("TEST_DATABASE_URL must use PostgreSQL")
    if url.database != "eduflow_test":
        pytest.fail("TEST_DATABASE_URL database must be exactly eduflow_test")
    if url.host not in {"localhost", "127.0.0.1"}:
        pytest.fail("TEST_DATABASE_URL host must be localhost or 127.0.0.1")
    if _ssh_tunnel_present():
        pytest.fail("SSH tunnel process detected; refusing database tests")

    engine = create_engine(url)
    try:
        with engine.connect() as connection:
            actual_database = connection.execute(text("SELECT current_database()")).scalar_one()
        if actual_database != "eduflow_test":
            pytest.fail("Connected PostgreSQL database is not eduflow_test")
    except Exception:
        engine.dispose()
        raise

    yield engine
    engine.dispose()


@pytest.fixture
def db_session(test_engine):
    from sqlalchemy.orm import Session

    connection = test_engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        if transaction.is_active:
            transaction.rollback()
        connection.close()


@pytest.fixture
def client(monkeypatch, db_session, test_engine):
    """Import FastAPI only after setting the verified test URL; never load .env."""
    import dotenv

    monkeypatch.setattr(dotenv, "load_dotenv", lambda *args, **kwargs: False)
    monkeypatch.setenv("DATABASE_URL", os.environ["TEST_DATABASE_URL"])
    monkeypatch.setenv("SECRET_KEY", "pytest-only-secret-key")

    from fastapi.testclient import TestClient
    from main import edu_app
    from myproject.database.db import engine as app_engine, get_db
    from sqlalchemy.engine import make_url

    expected_url = make_url(os.environ["TEST_DATABASE_URL"])
    if app_engine.url != expected_url or app_engine.url.database != "eduflow_test":
        pytest.fail("FastAPI SQLAlchemy engine is not configured for verified eduflow_test")

    def override_get_db():
        yield db_session

    edu_app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(edu_app) as test_client:
            yield test_client
    finally:
        edu_app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def actors(db_session):
    from datetime import date
    from myproject.core.security import hash_password
    from myproject.database.models import Group, Student, StudentGroupHistory, StudentGroupHistoryKind, User, UserRole

    suffix = os.urandom(8).hex()
    admin = User(username=f"admin_{suffix}", hashed_password=hash_password("Admin-password-1"), role=UserRole.ADMIN)
    student_user = User(username=f"student_{suffix}", hashed_password=hash_password("Student-password-1"), role=UserRole.STUDENT)
    group_a = Group(name=f"Group A {suffix}", course_name="Course", start_date=date(2025, 1, 1))
    group_b = Group(name=f"Group B {suffix}", course_name="Course", start_date=date(2025, 1, 1))
    db_session.add_all([admin, student_user, group_a, group_b])
    db_session.flush()
    student = Student(user_id=student_user.id, student_number=f"S{suffix}", group_id=group_a.id)
    db_session.add(student)
    db_session.flush()
    db_session.add(StudentGroupHistory(student_id=student.id, group_id=group_a.id,
                                       kind=StudentGroupHistoryKind.ENROLLMENT, from_date=date.today()))
    db_session.flush()
    return {"admin": admin, "student_user": student_user, "student": student,
            "group_a": group_a, "group_b": group_b, "password": "Student-password-1"}


@pytest.fixture
def auth_headers(actors):
    from myproject.core.security import create_access_token

    def headers(user):
        return {"Authorization": f"Bearer {create_access_token(user.id)}"}

    return headers


@pytest.fixture
def contract_factory(db_session, actors):
    from datetime import date
    from decimal import Decimal
    from myproject.database.models import Contract

    def create(total="1000.00", monthly="100.00", months=10, payment_day=15):
        contract = Contract(student_id=actors["student"].id, total_amount=Decimal(total),
                            monthly_payment=Decimal(monthly), duration_months=months,
                            start_date=date(2025, 1, 1), payment_day=payment_day)
        db_session.add(contract)
        db_session.flush()
        return contract

    return create
