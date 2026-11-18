from decimal import Decimal
from uuid import uuid4

from myproject.database.models import FinikReceipt, FinikTransaction, Payment, PaymentStatus


def _finik_body(contract, amount="30000.00"):
    return {
        "request_id": str(uuid4()),
        "contract_id": contract.id,
        "amount": amount,
        "payment_month": None,
    }


def _finik_setup(monkeypatch):
    import myproject.api.finik as finik
    monkeypatch.setattr(finik, "ensure_config", lambda: None)
    monkeypatch.setattr(
        finik, "create_finik_payment",
        lambda *args: "https://qr.finik/receipt-test"
    )
    monkeypatch.setattr(finik, "verify_webhook", lambda *args: True)


def test_signed_webhook_stores_receipt_once(
    client, actors, auth_headers, contract_factory, db_session, monkeypatch
):
    _finik_setup(monkeypatch)
    contract = contract_factory(
        total="45000.00", monthly="15000.00", months=3
    )
    student_headers = auth_headers(actors["student_user"])
    created = client.post(
        "/finik/payments",
        headers=student_headers,
        json=_finik_body(contract),
    )
    assert created.status_code == 201, created.text
    payment_id = created.json()["payment_id"]

    pending_receipt = client.get(
        f"/finik/receipts/{payment_id}", headers=student_headers
    )
    assert pending_receipt.status_code == 409

    tx = db_session.query(FinikTransaction).filter_by(payment_id=payment_id).one()
    webhook = {
        "status": "success",
        "transactionId": "finik-receipt-test-1",
        "id": "provider-operation-test-1",
        "amount": 30000,
        "fields": {
            "paymentId": tx.provider_payment_id,
            "amount": 30000,
        },
    }
    first = client.post("/webhooks/finik", json=webhook)
    assert first.status_code == 200, first.text
    assert first.json()["status"] == "confirmed"
    duplicate = client.post("/webhooks/finik", json=webhook)
    assert duplicate.status_code == 200
    assert duplicate.json()["status"] == "duplicate"

    receipt = client.get(
        f"/finik/receipts/{payment_id}", headers=student_headers
    )
    assert receipt.status_code == 200, receipt.text
    info = receipt.json()
    assert info["receipt_number"] == f"EDU-FINIK-{payment_id:010d}"
    assert Decimal(str(info["amount"])) == Decimal("30000.00")
    assert info["currency"] == "KGS"
    assert info["provider_transaction_id"] == "finik-receipt-test-1"
    assert info["provider_operation_id"] == "provider-operation-test-1"
    assert info["verification_source"] == "signed_webhook"
    assert len(info["allocation_snapshot"]) == 2
    assert [a["payment_month"] for a in info["allocation_snapshot"]] == [
        "2026-01", "2026-02"
    ]
    assert [a["amount"] for a in info["allocation_snapshot"]] == [
        "15000.00", "15000.00"
    ]
    assert info["confirmed_at"] is not None
    assert db_session.query(FinikReceipt).filter_by(payment_id=payment_id).count() == 1

    admin = client.get(
        f"/finik/receipts/{payment_id}",
        headers=auth_headers(actors["admin"]),
    )
    assert admin.status_code == 200
    assert client.get(f"/finik/receipts/{payment_id}").status_code == 401


def test_receipt_is_private_and_cash_has_no_finik_receipt(
    client, actors, auth_headers, contract_factory, db_session
):
    from myproject.core.security import hash_password
    from myproject.database.models import Student, User, UserRole

    contract = contract_factory()
    second_user = User(
        username=f"receipt-other-{uuid4().hex[:18]}",
        hashed_password=hash_password("Some-secure-password"),
        role=UserRole.STUDENT,
    )
    db_session.add(second_user)
    db_session.flush()
    second_student = Student(
        user_id=second_user.id,
        student_number=f"X{uuid4().hex[:20]}",
        group_id=actors["group_b"].id,
    )
    db_session.add(second_student)
    db_session.flush()

    payment = Payment(
        contract_id=contract.id,
        request_id=str(uuid4()),
        amount=Decimal("100.00"),
        payment_method="finik",
        payment_month="2026-01",
        status=PaymentStatus.CONFIRMED,
        created_by_user_id=actors["student_user"].id,
    )
    db_session.add(payment)
    db_session.flush()

    other_headers = auth_headers(second_user)
    assert client.get(
        f"/finik/receipts/{payment.id}", headers=other_headers
    ).status_code == 403

    owner_headers = auth_headers(actors["student_user"])
    assert client.get(
        f"/finik/receipts/{payment.id}", headers=owner_headers
    ).status_code == 404

    cash = Payment(
        contract_id=contract.id,
        request_id=str(uuid4()),
        amount=Decimal("50.00"),
        payment_method="cash",
        payment_month="2026-01",
        status=PaymentStatus.CONFIRMED,
        created_by_user_id=actors["admin"].id,
    )
    db_session.add(cash)
    db_session.flush()
    assert client.get(
        f"/finik/receipts/{cash.id}", headers=owner_headers
    ).status_code == 404


def test_manual_finik_reconciliation_creates_receipt(
    client, actors, auth_headers, contract_factory, db_session, monkeypatch
):
    _finik_setup(monkeypatch)
    contract = contract_factory()
    headers = auth_headers(actors["student_user"])
    response = client.post(
        "/finik/payments", headers=headers,
        json=_finik_body(contract, "100.00")
    )
    assert response.status_code == 201, response.text
    payment_id = response.json()["payment_id"]
    transaction = db_session.query(FinikTransaction).filter_by(
        payment_id=payment_id
    ).one()
    transaction.status = "review"
    db_session.flush()

    result = client.post(
        f"/finik/transactions/{transaction.id}/resolve",
        headers=auth_headers(actors["admin"]),
        json={
            "action": "confirm",
            "provider_transaction_id": "manual-reviewed-tx",
            "evidence_reference": "reviewed in merchant dashboard",
            "comment": "Successful payment verified",
        },
    )
    assert result.status_code == 200, result.text
    receipt = client.get(f"/finik/receipts/{payment_id}", headers=headers)
    assert receipt.status_code == 200, receipt.text
    assert receipt.json()["verification_source"] == "admin_reconciliation"
    assert receipt.json()["provider_transaction_id"] == "manual-reviewed-tx"
