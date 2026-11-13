from datetime import datetime
from decimal import Decimal
from uuid import uuid4

from myproject.database.models import ContractType, Payment, PaymentStatus
from myproject.services.payment_allocation import payment_plan


def _cash(contract, amount, month=None):
    return {
        "request_id": str(uuid4()),
        "contract_id": contract.id,
        "amount": str(amount),
        "payment_method": "cash",
        "payment_month": month,
    }


def test_academy_auto_distributes_30000_across_two_months(
    client, actors, auth_headers, contract_factory
):
    contract = contract_factory(total="150000.00", monthly="15000.00", months=10)
    payload = _cash(contract, "30000.00")
    response = client.post(
        "/payments/", headers=auth_headers(actors["admin"]), json=payload
    )
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["status"] == "confirmed"
    assert [(r["period_index"], r["payment_month"], Decimal(str(r["amount"])))
            for r in data["allocations"]] == [
        (0, "2026-01", Decimal("15000.00")),
        (1, "2026-02", Decimal("15000.00")),
    ]
    assert datetime.fromisoformat(data["created_at"])
    assert datetime.fromisoformat(data["paid_at"])
    repeat = client.post("/payments/", headers=auth_headers(actors["admin"]), json=payload)
    assert repeat.status_code == 201
    assert repeat.json()["id"] == data["id"]
    assert len(repeat.json()["allocations"]) == 2

    balance = client.get(
        "/payments/my/balance", headers=auth_headers(actors["student_user"])
    )
    assert balance.status_code == 200
    assert balance.json()[0]["paid_months"] == 2
    assert Decimal(str(balance.json()[0]["remaining_amount"])) == Decimal("120000.00")


def test_cannot_select_future_month_before_paying_first(
    client, actors, auth_headers, contract_factory
):
    contract = contract_factory(total="45000.00", monthly="15000.00", months=3)
    headers = auth_headers(actors["admin"])
    skipped = client.post(
        "/payments/", headers=headers,
        json=_cash(contract, "15000.00", "2026-02"),
    )
    assert skipped.status_code == 409

    partial = client.post("/payments/", headers=headers, json=_cash(contract, "5000.00"))
    assert partial.status_code == 201
    wrong = client.post(
        "/payments/", headers=headers,
        json=_cash(contract, "15000.00", "2026-02"),
    )
    assert wrong.status_code == 409
    catch_up = client.post(
        "/payments/", headers=headers, json=_cash(contract, "25000.00")
    )
    assert catch_up.status_code == 201
    assert [a["payment_month"] for a in catch_up.json()["allocations"]] == [
        "2026-01", "2026-02"
    ]
    assert [Decimal(str(a["amount"])) for a in catch_up.json()["allocations"]] == [
        Decimal("10000.00"), Decimal("15000.00")
    ]


def test_college_three_installments_with_remainder(
    client, actors, auth_headers, contract_factory, db_session
):
    contract = contract_factory(
        total="100000.00", monthly="10000.00", months=10,
        contract_type=ContractType.COLLEGE
    )
    contract.installment_count = 3
    db_session.flush()

    amounts = [p["amount"] for p in payment_plan(contract)]
    assert amounts == [
        Decimal("33333.33"), Decimal("33333.33"), Decimal("33333.34")
    ]

    headers = auth_headers(actors["admin"])
    first = client.post(
        "/payments/", headers=headers, json=_cash(contract, "66666.66")
    )
    assert first.status_code == 201
    assert [a["period_index"] for a in first.json()["allocations"]] == [0, 1]
    last = client.post(
        "/payments/", headers=headers, json=_cash(contract, "33333.34")
    )
    assert last.status_code == 201
    assert [a["period_index"] for a in last.json()["allocations"]] == [2]
    balance = client.get(
        "/payments/my/balance", headers=auth_headers(actors["student_user"])
    ).json()[0]
    assert balance["installment_count"] == 3
    assert balance["paid_installments"] == 3
    assert Decimal(str(balance["remaining_amount"])) == 0


def test_mentor_name_is_visible_in_group_and_student_api(
    client, actors, auth_headers, db_session
):
    group = actors["group_a"]
    group.mentor_name = "Айбек Тестов"
    db_session.flush()
    headers = auth_headers(actors["admin"])

    group_response = client.get(f"/groups/{group.id}", headers=headers)
    assert group_response.status_code == 200
    assert group_response.json()["mentor_name"] == "Айбек Тестов"

    student = actors["student"]
    student_response = client.get(f"/students/{student.id}", headers=headers)
    assert student_response.status_code == 200
    assert student_response.json()["mentor_name"] == "Айбек Тестов"


def test_pending_payment_prevents_double_reservation(
    client, actors, auth_headers, contract_factory, db_session
):
    contract = contract_factory(total="45000.00", monthly="15000.00", months=3)
    existing = Payment(
        contract_id=contract.id, amount=Decimal("15000.00"),
        status=PaymentStatus.PENDING, payment_method="finik",
        payment_month="2026-01", request_id=str(uuid4()),
        created_by_user_id=actors["student_user"].id
    )
    db_session.add(existing)
    db_session.flush()

    second = client.post(
        "/payments/", headers=auth_headers(actors["admin"]),
        json=_cash(contract, "30000.00")
    )
    assert second.status_code == 409


def test_college_contract_creation_accepts_two_or_three_parts(
    client, actors, auth_headers
):
    payload = {
        "student_id": actors["student"].id,
        "total_amount": "90000.00",
        "monthly_payment": "15000.00",
        "duration_months": 6,
        "start_date": "2026-01-01",
        "type": "college",
    }
    headers = auth_headers(actors["admin"])
    two = client.post("/contracts/", headers=headers, json=payload)
    assert two.status_code == 201, two.text
    assert two.json()["installment_count"] == 2

    three = client.post(
        "/contracts/", headers=headers,
        json={**payload, "installment_count": 3}
    )
    assert three.status_code == 201, three.text
    assert three.json()["installment_count"] == 3

    invalid = client.post(
        "/contracts/", headers=headers,
        json={**payload, "installment_count": 4}
    )
    assert invalid.status_code == 422


def test_finik_multi_month_single_transaction_and_repeated_webhook(
    client, actors, auth_headers, contract_factory, db_session, monkeypatch
):
    import myproject.api.finik as finik_api
    from myproject.database.models import FinikTransaction

    monkeypatch.setattr(finik_api, "ensure_config", lambda: None)
    monkeypatch.setattr(
        finik_api, "create_finik_payment", lambda *args: "https://qr.finik/multi"
    )
    monkeypatch.setattr(finik_api, "verify_webhook", lambda *args: True)

    contract = contract_factory(total="45000.00", monthly="15000.00", months=3)
    body = {
        "request_id": str(uuid4()),
        "contract_id": contract.id,
        "amount": "30000.00",
        "payment_month": None,
    }
    headers = auth_headers(actors["student_user"])
    created = client.post("/finik/payments", headers=headers, json=body)
    assert created.status_code == 201, created.text
    payment_id = created.json()["payment_id"]

    transaction = db_session.query(FinikTransaction).filter_by(
        payment_id=payment_id
    ).one()
    webhook = {
        "status": "success",
        "transactionId": "finik-multi-tx",
        "id": "finik-multi-op",
        "amount": 30000,
        "fields": {
            "paymentId": transaction.provider_payment_id,
            "amount": 30000,
        },
    }
    confirmed = client.post("/webhooks/finik", json=webhook)
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["status"] == "confirmed"
    duplicate = client.post("/webhooks/finik", json=webhook)
    assert duplicate.status_code == 200
    assert duplicate.json()["status"] == "duplicate"

    payment_response = client.get(
        f"/payments/{payment_id}", headers=headers
    )
    assert payment_response.status_code == 200
    assert len(payment_response.json()["allocations"]) == 2
    assert [a["payment_month"] for a in payment_response.json()["allocations"]] == [
        "2026-01", "2026-02"
    ]

    balance = client.get("/payments/my/balance", headers=headers).json()[0]
    assert balance["paid_months"] == 2
    assert Decimal(str(balance["remaining_amount"])) == Decimal("15000.00")


def test_create_group_with_mentor_name(client, actors, auth_headers):
    payload = {
        "name": "Python 2026",
        "course_name": "Python",
        "mentor_name": "Ментор Айбек",
        "start_date": "2026-01-01",
    }
    response = client.post(
        "/groups/", headers=auth_headers(actors["admin"]), json=payload
    )
    assert response.status_code == 201, response.text
    assert response.json()["mentor_name"] == "Ментор Айбек"
