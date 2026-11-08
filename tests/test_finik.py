import base64
import time
from uuid import uuid4

from myproject.database.models import (
    FinikTransaction, Payment, PaymentStatus
)


def _body(contract, amount="100.00", month="2026-10"):
    return {
        "request_id": str(uuid4()),
        "contract_id": contract.id,
        "amount": amount,
        "payment_month": month,
    }


def _patch_finik(monkeypatch, create):
    import myproject.api.finik as finik_api

    monkeypatch.setattr(finik_api, "ensure_config", lambda: None)
    monkeypatch.setattr(finik_api, "create_finik_payment", create)
    return finik_api


def _transaction(db_session, payment_id):
    return db_session.query(FinikTransaction).filter(
        FinikTransaction.payment_id == payment_id
    ).one()


def test_finik_retry_reuses_payment_id_after_unknown(
    client, actors, auth_headers, contract_factory, db_session, monkeypatch
):
    contract = contract_factory()
    calls = {"count": 0}

    def create(payment_id, amount, contract_id):
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("temporary failure")
        return "https://qr.finik/retry"

    _patch_finik(monkeypatch, create)
    body = _body(contract)
    headers = auth_headers(actors["student_user"])

    first = client.post("/finik/payments", headers=headers, json=body)
    assert first.status_code == 502
    payment = db_session.query(Payment).filter(
        Payment.request_id == body["request_id"]
    ).one()
    transaction = _transaction(db_session, payment.id)
    assert transaction.status == "unknown"
    provider_payment_id = transaction.provider_payment_id

    second = client.post("/finik/payments", headers=headers, json=body)
    assert second.status_code == 201
    assert second.json()["payment_url"] == "https://qr.finik/retry"

    db_session.refresh(transaction)
    assert transaction.status == "ready"
    assert transaction.provider_payment_id == provider_payment_id


def test_finik_admin_can_confirm_reviewed_payment(
    client, actors, auth_headers, contract_factory, db_session, monkeypatch
):
    contract = contract_factory()
    _patch_finik(monkeypatch, lambda *args: "https://qr.finik/review")
    headers = auth_headers(actors["student_user"])
    body = _body(contract)

    created = client.post("/finik/payments", headers=headers, json=body)
    assert created.status_code == 201
    payment_id = created.json()["payment_id"]
    transaction = _transaction(db_session, payment_id)
    transaction.status = "review"
    transaction.review_reason = "amount_mismatch"
    db_session.flush()

    missing_evidence = client.post(
        f"/finik/transactions/{transaction.id}/resolve",
        headers=auth_headers(actors["admin"]),
        json={"action": "confirm", "provider_transaction_id": "finik-tx-1",
              "comment": "checked in Finik"},
    )
    assert missing_evidence.status_code == 422
    assert db_session.query(Payment).filter(Payment.id == payment_id).one().status == PaymentStatus.PENDING

    resolved = client.post(
        f"/finik/transactions/{transaction.id}/resolve",
        headers=auth_headers(actors["admin"]),
        json={
            "action": "confirm",
            "provider_transaction_id": "finik-tx-1",
            "evidence_reference": "portal transaction finik-tx-1",
            "comment": "checked in Finik",
        },
    )
    assert resolved.status_code == 200
    assert resolved.json()["status"] == "confirmed"
    assert resolved.json()["resolved_by_admin_id"] == actors["admin"].id

    payment = db_session.query(Payment).filter(Payment.id == payment_id).one()
    assert payment.status == PaymentStatus.CONFIRMED


def test_finik_admin_can_reject_pending_payment(
    client, actors, auth_headers, contract_factory, db_session, monkeypatch
):
    contract = contract_factory()
    _patch_finik(monkeypatch, lambda *args: "https://qr.finik/reject")
    headers = auth_headers(actors["student_user"])

    created = client.post("/finik/payments", headers=headers, json=_body(contract))
    assert created.status_code == 201
    payment_id = created.json()["payment_id"]
    transaction = _transaction(db_session, payment_id)

    resolved = client.post(
        f"/finik/transactions/{transaction.id}/resolve",
        headers=auth_headers(actors["admin"]),
        json={"action": "reject", "comment": "not paid"},
    )
    assert resolved.status_code == 200
    assert resolved.json()["status"] == "rejected"

    payment = db_session.query(Payment).filter(Payment.id == payment_id).one()
    assert payment.status == PaymentStatus.REJECTED


def test_student_cannot_create_qr_for_another_students_contract(
    client, actors, auth_headers, db_session, monkeypatch
):
    from datetime import date
    from decimal import Decimal

    from myproject.core.security import hash_password
    from myproject.database.models import Contract, Student, User, UserRole

    second_user = User(username=f"other_{uuid4().hex}",
                       hashed_password=hash_password("Other-password-1"),
                       role=UserRole.STUDENT)
    db_session.add(second_user)
    db_session.flush()
    second_student = Student(user_id=second_user.id,
                             student_number=f"S{uuid4().hex[:20]}",
                             group_id=actors["group_b"].id)
    db_session.add(second_student)
    db_session.flush()
    contract = Contract(
        student_id=second_student.id, total_amount=Decimal("1000.00"),
        monthly_payment=Decimal("100.00"), duration_months=10,
        start_date=date(2026, 1, 1),
    )
    db_session.add(contract)
    db_session.flush()
    _patch_finik(monkeypatch, lambda *args: "https://qr.finik/should-not-create")

    response = client.post(
        "/finik/payments", headers=auth_headers(actors["student_user"]),
        json=_body(contract),
    )
    assert response.status_code == 404


def test_finik_webhook_confirms_and_is_idempotent(
    client, actors, auth_headers, contract_factory, db_session, monkeypatch
):
    contract = contract_factory()
    finik_api = _patch_finik(monkeypatch, lambda *args: "https://qr.finik/ok")
    monkeypatch.setattr(finik_api, "verify_webhook", lambda *args: True)
    headers = auth_headers(actors["student_user"])

    created = client.post("/finik/payments", headers=headers, json=_body(contract))
    assert created.status_code == 201
    payment_id = created.json()["payment_id"]
    transaction = _transaction(db_session, payment_id)

    webhook = {
        "status": "success",
        "transactionId": "finik-tx-ok",
        "id": "finik-op-1",
        "amount": 100,
        "fields": {"paymentId": transaction.provider_payment_id, "amount": 100},
    }

    confirmed = client.post("/webhooks/finik", json=webhook)
    assert confirmed.status_code == 200
    assert confirmed.json()["status"] == "confirmed"

    duplicate = client.post("/webhooks/finik", json=webhook)
    assert duplicate.status_code == 200
    assert duplicate.json()["status"] == "duplicate"

    conflict = client.post(
        "/webhooks/finik", json={**webhook, "transactionId": "finik-tx-other"}
    )
    assert conflict.status_code == 409
    amount_conflict = client.post(
        "/webhooks/finik", json={**webhook, "amount": 99,
                                "fields": {**webhook["fields"], "amount": 99}}
    )
    assert amount_conflict.status_code == 409

    payment = db_session.query(Payment).filter(Payment.id == payment_id).one()
    assert payment.status == PaymentStatus.CONFIRMED


def test_pending_qr_does_not_change_balance_and_cash_and_finik_share_balance(
    client, actors, auth_headers, contract_factory, db_session, monkeypatch
):
    contract = contract_factory()
    finik_api = _patch_finik(monkeypatch, lambda *args: "https://qr.finik/mixed")
    monkeypatch.setattr(finik_api, "verify_webhook", lambda *args: True)
    admin_headers = auth_headers(actors["admin"])
    student_headers = auth_headers(actors["student_user"])

    cash = client.post("/payments/", headers=admin_headers,
                       json={**_body(contract), "payment_method": "cash", "amount": "20.00"})
    assert cash.status_code == 201
    before_qr = client.get("/payments/my/balance", headers=student_headers).json()[0]
    assert before_qr["paid_amount"] == 20.0

    body = _body(contract, amount="30.00")
    created = client.post("/finik/payments", headers=student_headers, json=body)
    assert created.status_code == 201
    assert created.json()["status"] == "pending"
    assert created.json()["payment_url"] == "https://qr.finik/mixed"
    pending_balance = client.get("/payments/my/balance", headers=student_headers).json()[0]
    assert pending_balance["paid_amount"] == 20.0
    assert pending_balance["remaining_amount"] == 980.0

    transaction = _transaction(db_session, created.json()["payment_id"])
    webhook = {
        "status": "succeeded",
        "transactionId": "finik-mixed-tx",
        "id": "finik-mixed-op_DEBIT",
        "amount": 30,
        "fields": {"paymentId": transaction.provider_payment_id, "amount": 30},
    }
    confirmed = client.post("/webhooks/finik", json=webhook)
    assert confirmed.status_code == 200
    assert confirmed.json()["status"] == "confirmed"
    after_webhook = client.get("/payments/my/balance", headers=student_headers).json()[0]
    assert after_webhook["paid_amount"] == 50.0
    assert after_webhook["remaining_amount"] == 950.0

    duplicate = client.post("/webhooks/finik", json=webhook)
    assert duplicate.status_code == 200
    final_balance = client.get("/payments/my/balance", headers=student_headers).json()[0]
    assert final_balance["paid_amount"] == 50.0


def test_finik_webhook_mismatch_goes_to_review(
    client, actors, auth_headers, contract_factory, db_session, monkeypatch
):
    contract = contract_factory()
    finik_api = _patch_finik(monkeypatch, lambda *args: "https://qr.finik/review")
    monkeypatch.setattr(finik_api, "verify_webhook", lambda *args: True)
    headers = auth_headers(actors["student_user"])

    created = client.post("/finik/payments", headers=headers, json=_body(contract))
    assert created.status_code == 201
    payment_id = created.json()["payment_id"]
    transaction = _transaction(db_session, payment_id)

    response = client.post("/webhooks/finik", json={
        "status": "success",
        "transactionId": "finik-tx-mismatch",
        "amount": 100,
        "fields": {"paymentId": transaction.provider_payment_id, "amount": 50},
    })

    assert response.status_code == 200
    assert response.json()["status"] == "review"

    db_session.refresh(transaction)
    assert "form_amount_mismatch" in transaction.review_reason

    payment = db_session.query(Payment).filter(Payment.id == payment_id).one()
    assert payment.status == PaymentStatus.PENDING


def test_finik_webhook_signature_failure_does_not_change_balance(
    client, actors, auth_headers, contract_factory, db_session, monkeypatch
):
    contract = contract_factory()
    finik_api = _patch_finik(monkeypatch, lambda *args: "https://qr.finik/invalid-signature")
    monkeypatch.setattr(finik_api, "verify_webhook", lambda *args: False)
    created = client.post("/finik/payments", headers=auth_headers(actors["student_user"]),
                          json=_body(contract))
    assert created.status_code == 201
    transaction = _transaction(db_session, created.json()["payment_id"])

    response = client.post("/webhooks/finik", json={
        "status": "success", "transactionId": "fake-tx", "amount": 100,
        "fields": {"paymentId": transaction.provider_payment_id, "amount": 100},
    })
    assert response.status_code == 401
    payment = db_session.query(Payment).filter(Payment.id == created.json()["payment_id"]).one()
    assert payment.status == PaymentStatus.PENDING
    balance = client.get("/payments/my/balance", headers=auth_headers(actors["student_user"]))
    assert balance.json()[0]["paid_amount"] == 0


def test_finik_payment_url_must_be_official_host():
    from myproject.services.finik import validate_payment_url

    assert validate_payment_url("https://qr.finik/payment/abc") == "https://qr.finik/payment/abc"
    for url in (
        "http://qr.finik/payment/abc",
        "https://attacker.example/payment/abc",
        "https://qr.finik.attacker.example/payment/abc",
        "https://user@qr.finik/payment/abc",
    ):
        try:
            validate_payment_url(url)
        except ValueError:
            pass
        else:
            raise AssertionError(f"accepted untrusted payment URL: {url}")


def test_undocumented_failure_webhook_does_not_change_payment_or_release_month(
    client, actors, auth_headers, contract_factory, db_session, monkeypatch
):
    contract = contract_factory()
    finik_api = _patch_finik(monkeypatch, lambda *args: "https://qr.finik/fail")
    monkeypatch.setattr(finik_api, "verify_webhook", lambda *args: True)
    headers = auth_headers(actors["student_user"])

    created = client.post("/finik/payments", headers=headers, json=_body(contract))
    assert created.status_code == 201
    payment_id = created.json()["payment_id"]
    transaction = _transaction(db_session, payment_id)
    transaction.payment_url = "https://qr.finik/previous"
    db_session.flush()

    failed = client.post("/webhooks/finik", json={
        "status": "failed",
        "transactionId": "finik-tx-failed",
        "fields": {"paymentId": transaction.provider_payment_id},
    })
    assert failed.status_code == 200
    assert failed.json()["status"] == "ignored"

    db_session.refresh(transaction)
    assert transaction.payment_url == "https://qr.finik/previous"

    payment = db_session.query(Payment).filter(Payment.id == payment_id).one()
    assert payment.status == PaymentStatus.PENDING

    rejected = client.post(
        f"/finik/transactions/{transaction.id}/resolve",
        headers=auth_headers(actors["admin"]),
        json={"action": "reject", "comment": "Verified unsuccessful in Finik portal"},
    )
    assert rejected.status_code == 200
    balance = client.get("/payments/my/balance", headers=headers).json()[0]
    assert balance["paid_amount"] == 0
    retried = client.post("/finik/payments", headers=headers,
                          json=_body(contract, amount="100.00", month="2026-10"))
    assert retried.status_code == 201
    assert client.get("/payments/my/balance", headers=headers).json()[0]["paid_amount"] == 0


def test_finik_late_success_can_be_confirmed_by_admin(
    client, actors, auth_headers, contract_factory, db_session, monkeypatch
):
    contract = contract_factory()
    finik_api = _patch_finik(monkeypatch, lambda *args: "https://qr.finik/late")
    monkeypatch.setattr(finik_api, "verify_webhook", lambda *args: True)
    headers = auth_headers(actors["student_user"])

    created = client.post("/finik/payments", headers=headers, json=_body(contract))
    assert created.status_code == 201
    payment_id = created.json()["payment_id"]
    transaction = _transaction(db_session, payment_id)

    rejected = client.post(
        f"/finik/transactions/{transaction.id}/resolve",
        headers=auth_headers(actors["admin"]),
        json={"action": "reject", "comment": "Verified unsuccessful in Finik portal"},
    )
    assert rejected.status_code == 200

    late = client.post("/webhooks/finik", json={
        "status": "success",
        "transactionId": "finik-tx-late",
        "amount": 100,
        "fields": {"paymentId": transaction.provider_payment_id, "amount": 100},
    })
    assert late.status_code == 200
    assert late.json()["status"] == "review"

    db_session.refresh(transaction)
    assert transaction.review_reason == "late_success"
    assert transaction.provider_transaction_id == "finik-tx-late"

    payment = db_session.query(Payment).filter(Payment.id == payment_id).one()
    assert payment.status == PaymentStatus.REJECTED

    resolved = client.post(
        f"/finik/transactions/{transaction.id}/resolve",
        headers=auth_headers(actors["admin"]),
        json={"action": "confirm", "comment": "late success checked",
              "evidence_reference": "portal transaction finik-tx-late"},
    )
    assert resolved.status_code == 200
    assert resolved.json()["status"] == "confirmed"

    db_session.refresh(payment)
    assert payment.status == PaymentStatus.CONFIRMED


def test_webhook_and_admin_resolve_serialize_without_double_credit(
    client, actors, auth_headers, contract_factory, db_session, test_engine, monkeypatch
):
    import asyncio
    import threading
    from concurrent.futures import ThreadPoolExecutor

    import httpx
    from sqlalchemy import event
    from sqlalchemy.orm import Session

    from main import edu_app
    from myproject.database.db import get_db

    contract = contract_factory()
    finik_api = _patch_finik(monkeypatch, lambda *args: "https://qr.finik/concurrent")
    monkeypatch.setattr(finik_api, "verify_webhook", lambda *args: True)
    created = client.post("/finik/payments", headers=auth_headers(actors["student_user"]),
                          json=_body(contract))
    assert created.status_code == 201
    transaction = _transaction(db_session, created.json()["payment_id"])
    transaction_id = f"finik-race-{uuid4()}"
    webhook = {
        "status": "success", "transactionId": transaction_id,
        "id": f"{transaction_id}-op_DEBIT", "amount": 100,
        "fields": {"paymentId": transaction.provider_payment_id, "amount": 100},
    }
    db_session.connection().commit()

    lock_session = Session(test_engine)
    lock_session.query(type(contract)).filter_by(id=contract.id).with_for_update().one()
    lock_attempts = 0
    lock_guard = threading.Lock()
    both_waiting_for_contract = threading.Event()

    def observe_contract_lock(conn, cursor, statement, parameters, context, executemany):
        nonlocal lock_attempts
        sql = statement.lower()
        if "from contracts" in sql and "for update" in sql:
            with lock_guard:
                lock_attempts += 1
                if lock_attempts == 2:
                    both_waiting_for_contract.set()

    event.listen(test_engine, "before_cursor_execute", observe_contract_lock)

    def override_db():
        with Session(test_engine) as session:
            yield session

    edu_app.dependency_overrides[get_db] = override_db

    async def send_webhook():
        transport = httpx.ASGITransport(app=edu_app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as http_client:
            return await http_client.post("/webhooks/finik", json=webhook)

    async def resolve_manually():
        transport = httpx.ASGITransport(app=edu_app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as http_client:
            return await http_client.post(
                f"/finik/transactions/{transaction.id}/resolve",
                headers=auth_headers(actors["admin"]),
                json={"action": "confirm", "provider_transaction_id": transaction_id,
                      "evidence_reference": "portal transaction finik-race-tx",
                      "comment": "verified against Finik portal"},
            )

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            webhook_request = executor.submit(asyncio.run, send_webhook())
            resolve_request = executor.submit(asyncio.run, resolve_manually())
            assert both_waiting_for_contract.wait(timeout=10), "Both operations did not reach the contract lock"
            lock_session.commit()
            webhook_response = webhook_request.result(timeout=15)
            resolve_response = resolve_request.result(timeout=15)
    finally:
        lock_session.rollback()
        lock_session.close()
        event.remove(test_engine, "before_cursor_execute", observe_contract_lock)
        edu_app.dependency_overrides.pop(get_db, None)

    assert webhook_response.status_code == 200, webhook_response.text
    assert resolve_response.status_code == 200, resolve_response.text
    with Session(test_engine) as session:
        payment = session.get(Payment, created.json()["payment_id"])
        assert payment.status == PaymentStatus.CONFIRMED
        assert payment.amount == 100
        confirmed_total = session.query(Payment.amount).filter(
            Payment.contract_id == contract.id,
            Payment.status == PaymentStatus.CONFIRMED,
        ).all()
        assert sum((row[0] for row in confirmed_total), start=0) == 100


def test_finik_webhook_rsa_signature(tmp_path, monkeypatch):
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding, rsa
    from myproject.services.finik import canonical, verify_webhook

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_path = tmp_path / "private.pem"
    public_path = tmp_path / "public.pem"
    private_path.write_bytes(private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ))
    public_path.write_bytes(private_key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ))

    monkeypatch.setattr(
        "myproject.services.finik.FINIK_PUBLIC_KEY_PATH", str(public_path)
    )

    body = {"status": "success", "amount": 100}
    headers = {
        "Host": "example.test",
        "x-api-key": "test-key",
        "x-api-timestamp": str(int(time.time() * 1000)),
    }
    signature = private_key.sign(
        canonical("POST", "/webhooks/finik", headers, body),
        padding.PKCS1v15(),
        hashes.SHA256(),
    )
    headers["signature"] = base64.b64encode(signature).decode()

    assert verify_webhook(headers, body, "/webhooks/finik")
    assert not verify_webhook(
        headers, {**body, "amount": 1}, "/webhooks/finik"
    )

    headers["x-api-timestamp"] = str(int(time.time() * 1000) - 301_000)
    stale_signature = private_key.sign(
        canonical("POST", "/webhooks/finik", headers, body),
        padding.PKCS1v15(),
        hashes.SHA256(),
    )
    headers["signature"] = base64.b64encode(stale_signature).decode()
    assert not verify_webhook(headers, body, "/webhooks/finik")
