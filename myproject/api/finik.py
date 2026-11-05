import json
import logging
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from myproject.api.payments import (
    _create_payment, calculate_balance, get_month_paid, get_reserved_amount
)
from myproject.core.dependencies import get_current_admin, get_current_student
from myproject.database.db import get_db
from myproject.database.models import (
    Contract, ContractStatus, ContractType,
    FinikTransaction, Payment, PaymentStatus, Student, User
)
from myproject.database.schemas import (
    FinikPaymentCreateSchema, FinikResolveSchema,
    FinikTransactionResponseSchema, PaymentCreateSchema
)
from myproject.services.finik import (
    ensure_config, create_finik_payment, verify_webhook
)
from myproject.services.schedule import find_contract_period


finik_router = APIRouter(tags=["Finik"])
logger = logging.getLogger(__name__)

SUCCESS_STATUSES = {"success", "succeeded"}
FAILED_STATUSES = {"error", "failed", "cancelled", "canceled", "declined", "rejected"}


@finik_router.post("/finik/payments", status_code=201)
def create_online_payment(
    data: FinikPaymentCreateSchema,
    student: Student = Depends(get_current_student),
    db: Session = Depends(get_db)
):
    try:
        ensure_config()
    except ValueError as exc:
        raise HTTPException(503, str(exc))

    contract = db.query(Contract).filter(
        Contract.id == data.contract_id,
        Contract.student_id == student.id
    ).first()

    if not contract:
        raise HTTPException(404, "Контракт не найден")

    payment_data = PaymentCreateSchema(
        request_id=data.request_id,
        contract_id=contract.id,
        amount=data.amount,
        payment_month=data.payment_month,
        payment_method="finik"
    )

    payment = _create_payment(
        payment_data, db, student.user, allow_finik=True
    )

    if payment.status != PaymentStatus.PENDING:
        raise HTTPException(409, "Платёж уже обработан")

    transaction = db.query(FinikTransaction).filter(
        FinikTransaction.payment_id == payment.id
    ).with_for_update().first()

    if transaction:
        if transaction.status in {"review", "failed", "rejected", "confirmed"}:
            raise HTTPException(409, "Операция ожидает проверки администратором")

        if transaction.payment_url:
            return {
                "payment_id": payment.id,
                "status": payment.status,
                "payment_url": transaction.payment_url
            }

        try:
            url = create_finik_payment(
                transaction.provider_payment_id,
                payment.amount,
                contract.id
            )
        except Exception:
            logger.exception(
                "Finik payment retry failed for payment %s", payment.id
            )
            transaction = db.query(FinikTransaction).filter(
                FinikTransaction.id == transaction.id
            ).with_for_update().populate_existing().one()

            if transaction.status != "confirmed":
                transaction.status = "unknown"

            db.commit()
            raise HTTPException(502, "Ошибка Finik, требуется сверка")

        transaction = db.query(FinikTransaction).filter(
            FinikTransaction.id == transaction.id
        ).with_for_update().populate_existing().one()

        if transaction.status != "confirmed":
            transaction.status = "ready"

        transaction.payment_url = url
        db.commit()

        return {
            "payment_id": payment.id,
            "status": payment.status,
            "payment_url": url
        }

    transaction = FinikTransaction(
        payment_id=payment.id,
        provider_payment_id=str(uuid4()),
        status="sending"
    )
    db.add(transaction)

    try:
        db.commit()
        db.refresh(transaction)
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Операция уже существует")

    try:
        url = create_finik_payment(
            transaction.provider_payment_id,
            payment.amount,
            contract.id
        )
    except Exception:
        logger.exception(
            "Finik payment creation failed for payment %s", payment.id
        )
        transaction = db.query(FinikTransaction).filter(
            FinikTransaction.id == transaction.id
        ).with_for_update().populate_existing().one()

        if transaction.status != "confirmed":
            transaction.status = "unknown"

        db.commit()
        raise HTTPException(502, "Ошибка Finik, требуется сверка")

    transaction = db.query(FinikTransaction).filter(
        FinikTransaction.id == transaction.id
    ).with_for_update().populate_existing().one()

    if transaction.status != "confirmed":
        transaction.status = "ready"

    transaction.payment_url = url
    db.commit()

    return {
        "payment_id": payment.id,
        "status": payment.status,
        "payment_url": url
    }


@finik_router.get("/finik/payments/{payment_id}")
def get_online_payment(
    payment_id: int,
    student: Student = Depends(get_current_student),
    db: Session = Depends(get_db)
):
    payment = db.query(Payment).join(Contract).filter(
        Payment.id == payment_id,
        Contract.student_id == student.id,
        Payment.payment_method == "finik"
    ).first()

    if not payment:
        raise HTTPException(404, "Платёж не найден")

    transaction = db.query(FinikTransaction).filter(
        FinikTransaction.payment_id == payment.id
    ).first()

    return {
        "payment_id": payment.id,
        "status": payment.status,
        "payment_url": transaction.payment_url if transaction else None,
        "provider_status": transaction.status if transaction else "not_created"
    }


@finik_router.get(
    "/finik/transactions",
    response_model=list[FinikTransactionResponseSchema]
)
def list_finik_transactions(
    status: str | None = None,
    stale_minutes: int | None = None,
    limit: int = 100,
    offset: int = 0,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    query = db.query(FinikTransaction)

    if status:
        query = query.filter(FinikTransaction.status == status)

    if stale_minutes is not None:
        cutoff = datetime.utcnow() - timedelta(minutes=max(stale_minutes, 0))
        query = query.filter(FinikTransaction.created_at <= cutoff)

    limit = min(max(limit, 1), 200)
    offset = max(offset, 0)

    return query.order_by(
        FinikTransaction.created_at.asc()
    ).offset(offset).limit(limit).all()


@finik_router.post(
    "/finik/transactions/{transaction_id}/retry",
    response_model=FinikTransactionResponseSchema
)
def retry_finik_transaction(
    transaction_id: int,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    transaction = db.query(FinikTransaction).filter(
        FinikTransaction.id == transaction_id
    ).with_for_update().first()

    if not transaction:
        raise HTTPException(404, "Операция Finik не найдена")

    if transaction.status == "confirmed":
        raise HTTPException(409, "Платёж уже подтверждён")

    if transaction.status in {"review", "failed", "rejected"}:
        raise HTTPException(409, "Операция требует ручного разрешения")

    if transaction.payment_url:
        return transaction

    payment = db.query(Payment).filter(
        Payment.id == transaction.payment_id
    ).first()

    if not payment:
        raise HTTPException(404, "Платёж не найден")

    try:
        url = create_finik_payment(
            transaction.provider_payment_id,
            payment.amount,
            payment.contract_id
        )
    except Exception:
        logger.exception(
            "Finik payment retry failed for transaction %s", transaction.id
        )
        transaction.status = "unknown"
        db.commit()
        raise HTTPException(502, "Ошибка Finik, требуется сверка")

    transaction.status = "ready"
    transaction.payment_url = url
    db.commit()
    db.refresh(transaction)

    return transaction


@finik_router.post(
    "/finik/transactions/{transaction_id}/resolve",
    response_model=FinikTransactionResponseSchema
)
def resolve_finik_transaction(
    transaction_id: int,
    data: FinikResolveSchema,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    transaction = db.query(FinikTransaction).filter(
        FinikTransaction.id == transaction_id
    ).with_for_update().first()

    if not transaction:
        raise HTTPException(404, "Операция Finik не найдена")

    payment = db.query(Payment).filter(
        Payment.id == transaction.payment_id
    ).with_for_update().populate_existing().first()

    if not payment:
        raise HTTPException(404, "Платёж не найден")

    contract = db.query(Contract).filter(
        Contract.id == payment.contract_id
    ).with_for_update().first()

    if not contract:
        raise HTTPException(404, "Контракт не найден")

    now = datetime.utcnow()

    if data.action == "confirm":
        if transaction.status == "confirmed":
            return transaction

        if transaction.status not in {
            "review", "unknown", "sending", "ready", "failed"
        }:
            raise HTTPException(409, "Операцию нельзя подтвердить")

        if payment.status not in (PaymentStatus.PENDING, PaymentStatus.REJECTED):
            raise HTTPException(409, "Платёж уже обработан")

        if contract.status != ContractStatus.ACTIVE:
            raise HTTPException(409, "Контракт не активен")

        if data.provider_transaction_id:
            if (
                transaction.provider_transaction_id
                and transaction.provider_transaction_id != data.provider_transaction_id
            ):
                raise HTTPException(409, "Другой Transaction ID")
            transaction.provider_transaction_id = data.provider_transaction_id
        elif not transaction.provider_transaction_id:
            raise HTTPException(422, "Укажите Transaction ID Finik")

        if contract.type == ContractType.ACADEMY:
            period = find_contract_period(contract, payment.payment_month)

            if period is None:
                raise HTTPException(409, "Месяц не входит в график оплаты контракта")

            month_paid = get_month_paid(
                contract.id, payment.payment_month, db
            )

            if payment.amount > contract.monthly_payment - month_paid:
                raise HTTPException(409, "Превышена сумма оплаты за месяц")

        reserved = get_reserved_amount(
            contract.id, db, exclude_payment_id=payment.id
        )

        if payment.amount > contract.total_amount - reserved:
            raise HTTPException(409, "Сумма превышает остаток контракта")

        payment.status = PaymentStatus.CONFIRMED
        payment.paid_at = now
        payment.confirmed_by_admin_id = admin.id
        transaction.status = "confirmed"
        transaction.confirmed_at = now
        transaction.review_reason = None
    else:
        if transaction.status == "confirmed":
            raise HTTPException(409, "Подтверждённый платёж нельзя отклонить")

        payment.status = PaymentStatus.REJECTED
        payment.paid_at = None
        payment.confirmed_by_admin_id = admin.id
        transaction.status = "rejected"
        transaction.confirmed_at = None
        transaction.payment_url = None

    transaction.resolved_by_admin_id = admin.id
    transaction.resolved_at = now
    transaction.admin_comment = data.comment

    db.commit()
    db.refresh(transaction)

    return transaction


@finik_router.post("/webhooks/finik")
async def finik_webhook(
    request: Request,
    db: Session = Depends(get_db)
):
    if request.url.query:
        raise HTTPException(400, "Query не поддерживается")

    try:
        body = json.loads(await request.body())
        if not isinstance(body, dict):
            raise ValueError()
    except (ValueError, TypeError):
        raise HTTPException(400, "Неверный JSON")

    if not verify_webhook(dict(request.headers), body, request.url.path):
        raise HTTPException(401, "Неверная подпись Finik")

    status_value = str(body.get("status", "")).lower()

    if status_value not in SUCCESS_STATUSES | FAILED_STATUSES:
        return {"status": "ignored"}

    fields = body.get("fields")
    provider_payment_id = fields.get("paymentId") if isinstance(fields, dict) else None
    transaction_id = body.get("transactionId")

    if not provider_payment_id:
        raise HTTPException(422, "Нет Payment ID Finik")

    transaction = db.query(FinikTransaction).filter(
        FinikTransaction.provider_payment_id == provider_payment_id
    ).first()

    if not transaction:
        raise HTTPException(404, "Операция не найдена")

    payment = db.query(Payment).filter(
        Payment.id == transaction.payment_id
    ).first()

    if not payment:
        raise HTTPException(404, "Платёж не найден")

    contract = db.query(Contract).filter(
        Contract.id == payment.contract_id
    ).with_for_update().first()

    if not contract:
        raise HTTPException(404, "Контракт не найден")

    payment = db.query(Payment).filter(
        Payment.id == payment.id
    ).with_for_update().populate_existing().first()

    transaction = db.query(FinikTransaction).filter(
        FinikTransaction.id == transaction.id
    ).with_for_update().populate_existing().first()

    if transaction.status == "confirmed":
        if (
            transaction_id
            and transaction.provider_transaction_id
            and transaction.provider_transaction_id != str(transaction_id)
        ):
            raise HTTPException(409, "Другой Transaction ID")
        return {"status": "duplicate"}

    if transaction.status == "review" and status_value in FAILED_STATUSES:
        return {"status": "review"}

    if status_value in FAILED_STATUSES:
        if (
            transaction_id
            and transaction.provider_transaction_id
            and transaction.provider_transaction_id != str(transaction_id)
        ):
            raise HTTPException(409, "Конфликт транзакций")

        if transaction.status in {"failed", "rejected"}:
            return {"status": transaction.status}

        if transaction_id and not transaction.provider_transaction_id:
            transaction.provider_transaction_id = str(transaction_id)

        transaction.provider_operation_id = str(body.get("id", "")) or None
        transaction.status = "failed"
        transaction.payment_url = None
        transaction.review_reason = f"provider_{status_value}"

        if payment.status == PaymentStatus.PENDING:
            payment.status = PaymentStatus.REJECTED
            payment.paid_at = None

        db.commit()
        logger.warning(
            "Finik webhook reported %s for payment %s",
            status_value, payment.id
        )
        return {"status": "failed"}

    if not transaction_id:
        raise HTTPException(422, "Нет Transaction ID Finik")

    if (
        transaction.provider_transaction_id
        and transaction.provider_transaction_id != str(transaction_id)
    ):
        raise HTTPException(409, "Конфликт транзакций")

    if transaction.status == "review":
        return {"status": "review"}

    if transaction.status in {"failed", "rejected"}:
        transaction.status = "review"
        transaction.review_reason = "late_success"
        db.commit()
        return {"status": "review"}

    try:
        amount = Decimal(str(body["amount"]))
    except (KeyError, InvalidOperation, TypeError):
        raise HTTPException(422, "Неверная сумма")

    if not amount.is_finite() or amount <= 0:
        raise HTTPException(422, "Неверная сумма")

    transaction.provider_transaction_id = str(transaction_id)
    transaction.provider_operation_id = str(body.get("id", "")) or None

    reasons = []

    if payment.status != PaymentStatus.PENDING:
        reasons.append("payment_not_pending")

    if payment.amount != amount:
        reasons.append("amount_mismatch")

    if contract.status != ContractStatus.ACTIVE:
        reasons.append("contract_inactive")

    if payment.amount > calculate_balance(
        contract.id, db
    )["remaining_amount"]:
        reasons.append("balance_exceeded")

    if contract.type == ContractType.ACADEMY:
        period = find_contract_period(contract, payment.payment_month)

        if period is None:
            reasons.append("month_out_of_schedule")
        elif payment.amount > (
            contract.monthly_payment
            - get_month_paid(contract.id, payment.payment_month, db)
        ):
            reasons.append("month_exceeded")

    if reasons:
        transaction.status = "review"
        transaction.review_reason = ",".join(reasons)
        logger.warning(
            "Finik webhook sent payment %s to review: %s",
            payment.id, transaction.review_reason
        )
    else:
        now = datetime.utcnow()
        payment.status = PaymentStatus.CONFIRMED
        payment.paid_at = now
        payment.confirmed_by_admin_id = None
        transaction.status = "confirmed"
        transaction.confirmed_at = now
        transaction.review_reason = None

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Дубликат транзакции Finik")

    return {"status": transaction.status}