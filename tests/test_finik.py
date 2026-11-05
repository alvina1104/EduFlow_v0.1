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
        return "https://pay.finik/retry"

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
    assert second.json()["payment_url"] == "https://pay.finik/retry"

    db_session.refresh(transaction)
    assert transaction.status == "ready"
    assert transaction.provider_payment_id == provider_payment_id


def test_finik_admin_can_confirm_reviewed_payment(
    client, actors, auth_headers, contract_factory, db_session, monkeypatch
):
    contract = contract_factory()
    _patch_finik(monkeypatch, lambda *args: "https://pay.finik/review")
    headers = auth_headers(actors["student_user"])
    body = _body(contract)

    created = client.post("/finik/payments", headers=headers, json=body)
    assert created.status_code == 201
    payment_id = created.json()["payment_id"]
    transaction = _transaction(db_session, payment_id)
    transaction.status = "review"
    transaction.review_reason = "amount_mismatch"
    db_session.flush()

    resolved = client.post(
        f"/finik/transactions/{transaction.id}/resolve",
        headers=auth_headers(actors["admin"]),
        json={
            "action": "confirm",
            "provider_transaction_id": "finik-tx-1",
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
    _patch_finik(monkeypatch, lambda *args: "https://pay.finik/reject")
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


def test_finik_webhook_confirms_and_is_idempotent(
    client, actors, auth_headers, contract_factory, db_session, monkeypatch
):
    contract = contract_factory()
    finik_api = _patch_finik(monkeypatch, lambda *args: "https://pay.finik/ok")
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
        "fields": {"paymentId": transaction.provider_payment_id},
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

    payment = db_session.query(Payment).filter(Payment.id == payment_id).one()
    assert payment.status == PaymentStatus.CONFIRMED


def test_finik_webhook_mismatch_goes_to_review(
    client, actors, auth_headers, contract_factory, db_session, monkeypatch
):
    contract = contract_factory()
    finik_api = _patch_finik(monkeypatch, lambda *args: "https://pay.finik/review")
    monkeypatch.setattr(finik_api, "verify_webhook", lambda *args: True)
    headers = auth_headers(actors["student_user"])

    created = client.post("/finik/payments", headers=headers, json=_body(contract))
    assert created.status_code == 201
    payment_id = created.json()["payment_id"]
    transaction = _transaction(db_session, payment_id)

    response = client.post("/webhooks/finik", json={
        "status": "success",
        "transactionId": "finik-tx-mismatch",
        "amount": 50,
        "fields": {"paymentId": transaction.provider_payment_id},
    })

    assert response.status_code == 200
    assert response.json()["status"] == "review"

    db_session.refresh(transaction)
    assert "amount_mismatch" in transaction.review_reason

    payment = db_session.query(Payment).filter(Payment.id == payment_id).one()
    assert payment.status == PaymentStatus.PENDING


def test_finik_failed_webhook_releases_month(
    client, actors, auth_headers, contract_factory, db_session, monkeypatch
):
    contract = contract_factory()
    finik_api = _patch_finik(monkeypatch, lambda *args: "https://pay.finik/fail")
    monkeypatch.setattr(finik_api, "verify_webhook", lambda *args: True)
    headers = auth_headers(actors["student_user"])

    created = client.post("/finik/payments", headers=headers, json=_body(contract))
    assert created.status_code == 201
    payment_id = created.json()["payment_id"]
    transaction = _transaction(db_session, payment_id)
    transaction.payment_url = "https://pay.finik/previous"
    db_session.flush()

    failed = client.post("/webhooks/finik", json={
        "status": "failed",
        "transactionId": "finik-tx-failed",
        "fields": {"paymentId": transaction.provider_payment_id},
    })
    assert failed.status_code == 200
    assert failed.json()["status"] == "failed"

    db_session.refresh(transaction)
    assert transaction.payment_url is None

    payment = db_session.query(Payment).filter(Payment.id == payment_id).one()
    assert payment.status == PaymentStatus.REJECTED

    retried = client.post(
        "/payments/", headers=headers,
        json=_body(contract, amount="100.00", month="2026-10")
    )
    assert retried.status_code == 201


def test_finik_late_success_can_be_confirmed_by_admin(
    client, actors, auth_headers, contract_factory, db_session, monkeypatch
):
    contract = contract_factory()
    finik_api = _patch_finik(monkeypatch, lambda *args: "https://pay.finik/late")
    monkeypatch.setattr(finik_api, "verify_webhook", lambda *args: True)
    headers = auth_headers(actors["student_user"])

    created = client.post("/finik/payments", headers=headers, json=_body(contract))
    assert created.status_code == 201
    payment_id = created.json()["payment_id"]
    transaction = _transaction(db_session, payment_id)

    failed = client.post("/webhooks/finik", json={
        "status": "failed",
        "transactionId": "finik-tx-late",
        "fields": {"paymentId": transaction.provider_payment_id},
    })
    assert failed.status_code == 200

    late = client.post("/webhooks/finik", json={
        "status": "success",
        "transactionId": "finik-tx-late",
        "amount": 100,
        "fields": {"paymentId": transaction.provider_payment_id},
    })
    assert late.status_code == 200
    assert late.json()["status"] == "review"

    db_session.refresh(transaction)
    assert transaction.review_reason == "late_success"

    payment = db_session.query(Payment).filter(Payment.id == payment_id).one()
    assert payment.status == PaymentStatus.REJECTED

    resolved = client.post(
        f"/finik/transactions/{transaction.id}/resolve",
        headers=auth_headers(actors["admin"]),
        json={"action": "confirm", "comment": "late success checked"},
    )
    assert resolved.status_code == 200
    assert resolved.json()["status"] == "confirmed"

    db_session.refresh(payment)
    assert payment.status == PaymentStatus.CONFIRMED


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
