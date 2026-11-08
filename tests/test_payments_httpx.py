from datetime import datetime
from decimal import Decimal
import asyncio
from concurrent.futures import ThreadPoolExecutor
import threading
from uuid import uuid4

import httpx
from sqlalchemy import event
from sqlalchemy.orm import Session

from myproject.database.models import Payment, PaymentStatus


def _body(contract, **overrides):
    return {
        "request_id": str(uuid4()),
        "contract_id": contract.id,
        "amount": "100.00",
        "payment_method": "cash",
        "payment_month": "2026-10",
        **overrides,
    }


def test_student_and_admin_payment_creation(client, actors, auth_headers, contract_factory):
    contract = contract_factory()
    student_response = client.post("/payments/", headers=auth_headers(actors["student_user"]),
                                   json=_body(contract))
    assert student_response.status_code == 403

    admin_response = client.post("/payments/", headers=auth_headers(actors["admin"]),
                                 json=_body(contract, payment_month="2026-09"))
    assert admin_response.status_code == 201
    assert admin_response.json()["status"] == "confirmed"
    assert admin_response.json()["confirmed_by_admin_id"] == actors["admin"].id
    assert admin_response.json()["created_by_user_id"] == actors["admin"].id
    assert admin_response.json()["paid_at"] is not None
    payment_id = admin_response.json()["id"]
    assert client.delete(f"/payments/{payment_id}",
                         headers=auth_headers(actors["admin"])).status_code == 409
    assert client.get(f"/payments/{payment_id}",
                      headers=auth_headers(actors["admin"])).status_code == 200


def test_card_payment_method_is_rejected(client, actors, auth_headers, contract_factory):
    contract = contract_factory()
    response = client.post(
        "/payments/", headers=auth_headers(actors["student_user"]),
        json=_body(contract, payment_method="card")
    )
    assert response.status_code == 422


def test_admin_payment_endpoint_accepts_only_cash(client, actors, auth_headers, contract_factory):
    contract = contract_factory()
    headers = auth_headers(actors["admin"])
    for method in (None, "finik"):
        response = client.post(
            "/payments/", headers=headers,
            json=_body(contract, payment_method=method),
        )
        assert response.status_code == 422


def test_paid_month_rejected_but_partial_month_can_be_completed(client, actors, auth_headers, contract_factory):
    contract = contract_factory()
    headers = auth_headers(actors["admin"])
    first = client.post("/payments/", headers=headers,
                        json=_body(contract, amount="40.00"))
    assert first.status_code == 201

    second = client.post("/payments/", headers=headers,
                         json=_body(contract, amount="60.00", request_id=str(uuid4())))
    assert second.status_code == 201

    duplicate_month = client.post("/payments/", headers=headers,
                                  json=_body(contract, amount="1.00", request_id=str(uuid4())))
    assert duplicate_month.status_code == 409
    balance = client.get("/payments/my/balance", headers=auth_headers(actors["student_user"]))
    assert balance.json()[0]["remaining_amount"] == 900.0


def test_pending_blocks_month_and_rejected_allows_resubmission(
    client, actors, auth_headers, contract_factory, db_session
):
    contract = contract_factory()
    admin_headers = auth_headers(actors["admin"])
    from myproject.database.models import Payment, PaymentStatus

    payment = Payment(
        contract_id=contract.id, amount=Decimal("50.00"),
        status=PaymentStatus.PENDING, payment_method="cash",
        payment_month="2026-10", request_id=str(uuid4()),
        created_by_user_id=actors["student_user"].id,
    )
    db_session.add(payment)
    db_session.flush()
    blocked = client.post("/payments/", headers=admin_headers,
                          json=_body(contract, amount="20.00", request_id=str(uuid4())))
    assert blocked.status_code == 409

    rejected = client.patch(f"/payments/{payment.id}/status", headers=admin_headers,
                            json={"status": "rejected"})
    assert rejected.status_code == 200
    resubmitted = client.post("/payments/", headers=admin_headers,
                              json=_body(contract, amount="50.00", request_id=str(uuid4())))
    assert resubmitted.status_code == 201


def test_confirmation_checks_month_and_contract_caps(client, actors, auth_headers, contract_factory, db_session):
    from myproject.database.models import PaymentStatus

    month_contract = contract_factory()
    month_pending = Payment(
        contract_id=month_contract.id, amount=Decimal("40.00"),
        status=PaymentStatus.PENDING, payment_method="cash",
        payment_month="2026-10", request_id=str(uuid4()),
        created_by_user_id=actors["student_user"].id,
    )
    db_session.add(month_pending)
    db_session.flush()
    db_session.add(Payment(contract_id=month_contract.id, amount=Decimal("70.00"),
                           status=PaymentStatus.CONFIRMED, payment_method="cash", payment_month="2026-10"))
    db_session.flush()
    month_result = client.patch(f"/payments/{month_pending.id}/status",
                                headers=auth_headers(actors["admin"]), json={"status": "confirmed"})
    assert month_result.status_code == 409

    total_contract = contract_factory(total="1000.00", monthly="100.00")
    total_pending = Payment(
        contract_id=total_contract.id, amount=Decimal("50.00"),
        status=PaymentStatus.PENDING, payment_method="cash",
        payment_month="2026-10", request_id=str(uuid4()),
        created_by_user_id=actors["student_user"].id,
    )
    db_session.add(total_pending)
    db_session.flush()
    db_session.add(Payment(contract_id=total_contract.id, amount=Decimal("980.00"),
                           status=PaymentStatus.CONFIRMED, payment_method="cash", payment_month="2026-09"))
    db_session.flush()
    total_result = client.patch(f"/payments/{total_pending.id}/status",
                                headers=auth_headers(actors["admin"]), json={"status": "confirmed"})
    assert total_result.status_code == 409


def test_request_id_idempotency_and_payment_permissions(client, actors, auth_headers, contract_factory):
    contract = contract_factory()
    student_headers = auth_headers(actors["student_user"])
    admin_headers = auth_headers(actors["admin"])
    body = _body(contract, amount="25.00")
    created = client.post("/payments/", headers=admin_headers, json=body)
    duplicate = client.post("/payments/", headers=admin_headers, json=body)
    assert created.status_code == duplicate.status_code == 201
    assert created.json()["id"] == duplicate.json()["id"]
    changed = client.post("/payments/", headers=admin_headers, json={**body, "amount": "26.00"})
    assert changed.status_code == 409
    assert client.post("/payments/", headers=student_headers, json=body).status_code == 403

    assert client.post("/payments/", json=_body(contract)).status_code == 401
    assert client.get("/payments/", headers=student_headers).status_code == 403
    assert client.get("/payments/my", headers=auth_headers(actors["admin"])).status_code == 403


def test_college_payment_without_month_allows_partial_and_full(
    client, actors, auth_headers, contract_factory
):
    from myproject.database.models import ContractType

    contract = contract_factory(contract_type=ContractType.COLLEGE)
    admin_headers = auth_headers(actors["admin"])

    partial = client.post(
        "/payments/", headers=admin_headers,
        json=_body(contract, amount="30.00", payment_month=None)
    )
    assert partial.status_code == 201
    assert len(partial.json()["payment_month"]) == 7

    full = client.post(
        "/payments/", headers=admin_headers,
        json=_body(contract, amount="70.00", payment_month=None,
                   request_id=str(uuid4()))
    )
    assert full.status_code == 201

    balance = client.get("/payments/my/balance", headers=auth_headers(actors["student_user"]))
    college_balance = next(
        item for item in balance.json() if item["contract_id"] == contract.id
    )
    assert college_balance["paid_months"] is None
    assert college_balance["remaining_amount"] == 900.0


def test_full_financial_repayment_does_not_complete_study_contract(
    client, actors, auth_headers, contract_factory
):
    from myproject.database.models import ContractType

    contract = contract_factory(total="100.00", monthly="500.00",
                                contract_type=ContractType.COLLEGE)
    cash = client.post(
        "/payments/", headers=auth_headers(actors["admin"]),
        json=_body(contract, amount="100.00", payment_month=None),
    )
    assert cash.status_code == 201
    balance = client.get("/payments/my/balance",
                         headers=auth_headers(actors["student_user"])).json()
    contract_balance = next(item for item in balance if item["contract_id"] == contract.id)
    assert contract_balance["remaining_amount"] == 0
    assert contract.status.value == "active"


def test_academy_rejects_month_outside_contract_schedule(
    client, actors, auth_headers, contract_factory
):
    contract = contract_factory()
    response = client.post(
        "/payments/", headers=auth_headers(actors["admin"]),
        json=_body(contract, payment_month="2026-12")
    )
    assert response.status_code == 409


def test_confirmation_reread_does_not_use_stale_orm_state(
    client, actors, auth_headers, contract_factory, db_session, test_engine, monkeypatch
):
    """Exercise an identity-mapped pending Payment after another transaction confirms it."""
    from sqlalchemy.orm import Session
    from main import edu_app
    from myproject.database.db import get_db

    contract = contract_factory()
    payment = Payment(
        contract_id=contract.id, amount=Decimal("20.00"),
        status=PaymentStatus.PENDING, payment_method="cash",
        payment_month="2026-10", request_id=str(uuid4()),
        created_by_user_id=actors["student_user"].id,
    )
    db_session.add(payment)
    db_session.flush()
    payment_id = payment.id
    db_session.connection().commit()  # Make fixture rows visible to independent transactions.

    stale_session = Session(test_engine)
    stale_payment = stale_session.query(Payment).filter(Payment.id == payment_id).one()
    assert stale_payment.status == PaymentStatus.PENDING

    with Session(test_engine) as concurrent_session:
        concurrent_payment = concurrent_session.get(Payment, payment_id)
        concurrent_payment.status = PaymentStatus.CONFIRMED
        concurrent_payment.confirmed_by_admin_id = actors["admin"].id
        concurrent_payment.paid_at = datetime.utcnow()
        concurrent_session.commit()

    def override_db():
        yield stale_session

    edu_app.dependency_overrides[get_db] = override_db
    try:
        retried = client.patch(f"/payments/{payment_id}/status", headers=auth_headers(actors["admin"]),
                               json={"status": "confirmed"})
    finally:
        edu_app.dependency_overrides.pop(get_db, None)
        stale_session.close()

    assert retried.status_code == 409


def test_concurrent_confirmation_serializes_and_rechecks_status(
    client, actors, auth_headers, contract_factory, db_session, test_engine, monkeypatch
):
    from main import edu_app
    from myproject.database.db import get_db
    from myproject.database.models import Contract

    contract = contract_factory()
    payment = Payment(
        contract_id=contract.id, amount=Decimal("20.00"),
        status=PaymentStatus.PENDING, payment_method="cash",
        payment_month="2026-10", request_id=str(uuid4()),
        created_by_user_id=actors["student_user"].id,
    )
    db_session.add(payment)
    db_session.flush()
    payment_id = payment.id
    db_session.connection().commit()

    request_reads = 0
    read_lock = threading.Lock()
    both_read_pending = threading.Event()

    def observe_initial_payment_read(conn, cursor, statement, parameters, context, executemany):
        nonlocal request_reads
        sql = statement.lower()
        if "from payments" in sql and "where payments.id =" in sql and "for update" not in sql:
            with read_lock:
                request_reads += 1
                if request_reads == 2:
                    both_read_pending.set()

    event.listen(test_engine, "after_cursor_execute", observe_initial_payment_read)
    lock_session = Session(test_engine)
    lock_session.query(Contract).filter(Contract.id == contract.id).with_for_update().one()

    def override_db():
        with Session(test_engine) as session:
            yield session

    edu_app.dependency_overrides[get_db] = override_db

    async def send_confirmations():
        transport = httpx.ASGITransport(app=edu_app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as http_client:
            return await asyncio.gather(*[
                http_client.patch(f"/payments/{payment_id}/status",
                                  headers=auth_headers(actors["admin"]),
                                  json={"status": "confirmed"})
                for _ in range(2)
            ])

    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            requests = executor.submit(asyncio.run, send_confirmations())
            assert both_read_pending.wait(timeout=10), "Both requests did not read pending payment"
            lock_session.commit()
            statuses = [response.status_code for response in requests.result(timeout=15)]
    finally:
        lock_session.rollback()
        lock_session.close()
        event.remove(test_engine, "after_cursor_execute", observe_initial_payment_read)
        edu_app.dependency_overrides.pop(get_db, None)

    assert sorted(statuses) == [200, 409]
