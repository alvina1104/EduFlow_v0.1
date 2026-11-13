import json
import logging
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from myproject.api.payments import (
    _create_payment, calculate_balance, get_reserved_amount
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
    ensure_config, create_finik_payment, validate_payment_url, verify_webhook
)
from myproject.services.payment_allocation import prepare_confirmation, save_allocations


finik_router = APIRouter(tags=["Finik"])
logger = logging.getLogger(__name__)

SUCCESS_STATUSES = {"success", "succeeded"}


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
    if contract.status != ContractStatus.ACTIVE:
        raise HTTPException(409, "Контракт не активен")

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
            url = validate_payment_url(create_finik_payment(
                transaction.provider_payment_id,
                payment.amount,
                contract.id
            ))
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
        url = validate_payment_url(create_finik_payment(
            transaction.provider_payment_id,
            payment.amount,
            contract.id
        ))
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

    payment = db.query(Payment).filter(
        Payment.id == transaction.payment_id
    ).first()

    if not payment:
        raise HTTPException(404, "Платёж не найден")

    contract = db.query(Contract).filter(Contract.id == payment.contract_id).first()
    if not contract or contract.status != ContractStatus.ACTIVE:
        raise HTTPException(409, "Контракт не активен")

    if transaction.payment_url:
        return transaction

    try:
        url = validate_payment_url(create_finik_payment(
            transaction.provider_payment_id,
            payment.amount,
            payment.contract_id
        ))
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
    transaction_ref = db.query(FinikTransaction).filter(
        FinikTransaction.id == transaction_id
    ).first()

    if not transaction_ref:
        raise HTTPException(404, "Операция Finik не найдена")

    # Lock rows in one global order (contract -> payment -> transaction).
    # The webhook uses the same order to avoid a payment/transaction deadlock.
    payment_ref = db.query(Payment).filter(
        Payment.id == transaction_ref.payment_id
    ).first()

    if not payment_ref:
        raise HTTPException(404, "Платёж не найден")

    contract = db.query(Contract).filter(
        Contract.id == payment_ref.contract_id
    ).populate_existing().with_for_update().first()

    if not contract:
        raise HTTPException(404, "Контракт не найден")

    payment = db.query(Payment).filter(
        Payment.id == payment_ref.id
    ).populate_existing().with_for_update().first()
    transaction = db.query(FinikTransaction).filter(
        FinikTransaction.id == transaction_ref.id
    ).populate_existing().with_for_update().first()

    if not payment or not transaction:
        raise HTTPException(404, "Операция оплаты не найдена")

    now = datetime.utcnow()

    if data.action == "confirm":
        if transaction.status == "confirmed":
            return transaction

        if transaction.status not in {
            "review", "unknown", "sending", "ready", "failed"
        }:
            raise HTTPException(409, "Операцию нельзя подтвердить")

        if not data.evidence_reference or not data.evidence_reference.strip():
            raise HTTPException(422, "Укажите ссылку на доказательство сверки в Finik")

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

        # Сверяем весь график взносов, включая несколько месяцев.
        allocations = prepare_confirmation(payment, contract, db)

        reserved = get_reserved_amount(
            contract.id, db, exclude_payment_id=payment.id
        )

        if payment.amount > contract.total_amount - reserved:
            raise HTTPException(409, "Сумма превышает остаток контракта")

        save_allocations(payment, db, allocations)
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
    evidence = (
        f"evidence={data.evidence_reference.strip()}; "
        if data.evidence_reference else ""
    )
    transaction.admin_comment = f"{evidence}{data.comment.strip()}"

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Transaction ID уже связан с другой операцией Finik")
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

    status_value = str(body.get("status", "")).strip().lower()

    # Current Finik Web SDK documents callbacks only for successful payments.
    # An undocumented failure value must never reject a payment or release funds.
    if status_value not in SUCCESS_STATUSES:
        return {"status": "ignored"}

    fields = body.get("fields")
    provider_payment_id = fields.get("paymentId") if isinstance(fields, dict) else None
    transaction_id = body.get("transactionId")

    if not isinstance(provider_payment_id, str) or not provider_payment_id:
        raise HTTPException(422, "Нет Payment ID Finik")

    transaction_ref = db.query(FinikTransaction).filter(
        FinikTransaction.provider_payment_id == provider_payment_id
    ).first()

    if not transaction_ref:
        raise HTTPException(404, "Операция не найдена")

    payment_ref = db.query(Payment).filter(
        Payment.id == transaction_ref.payment_id
    ).first()

    if not payment_ref:
        raise HTTPException(404, "Платёж не найден")

    contract = db.query(Contract).filter(
        Contract.id == payment_ref.contract_id
    ).populate_existing().with_for_update().first()

    if not contract:
        raise HTTPException(404, "Контракт не найден")

    payment = db.query(Payment).filter(
        Payment.id == payment_ref.id
    ).populate_existing().with_for_update().first()

    transaction = db.query(FinikTransaction).filter(
        FinikTransaction.id == transaction_ref.id
    ).populate_existing().with_for_update().first()

    if not payment or not transaction:
        raise HTTPException(404, "Операция оплаты не найдена")

    if not transaction_id:
        raise HTTPException(422, "Нет Transaction ID Finik")
    if not isinstance(transaction_id, str) or len(transaction_id) > 150:
        raise HTTPException(422, "Неверный Transaction ID Finik")

    if (
        transaction.provider_transaction_id
        and transaction.provider_transaction_id != transaction_id
    ):
        raise HTTPException(409, "Конфликт транзакций")

    fields_amount = fields.get("amount")
    try:
        amount = Decimal(str(body["amount"]))
        if fields_amount is None:
            raise InvalidOperation
        form_amount = Decimal(str(fields_amount))
    except (KeyError, InvalidOperation, TypeError):
        raise HTTPException(422, "Неверная сумма")

    if (
        not amount.is_finite() or amount <= 0
        or not form_amount.is_finite() or form_amount <= 0
    ):
        raise HTTPException(422, "Неверная сумма")

    if transaction.status == "confirmed":
        if payment.status != PaymentStatus.CONFIRMED or payment.amount != amount or payment.amount != form_amount:
            raise HTTPException(409, "Конфликт данных подтверждённой транзакции")
        return {"status": "duplicate"}

    transaction.provider_transaction_id = transaction_id
    transaction.provider_operation_id = str(body.get("id", "")) or None

    if transaction.status == "review":
        if payment.amount != amount or payment.amount != form_amount:
            transaction.review_reason = "amount_mismatch"
        db.commit()
        return {"status": "review"}

    if transaction.status in {"failed", "rejected"} or payment.status == PaymentStatus.REJECTED:
        transaction.status = "review"
        transaction.review_reason = (
            "late_success_amount_mismatch"
            if payment.amount != amount or payment.amount != form_amount
            else "late_success"
        )
        db.commit()
        return {"status": "review"}

    reasons = []

    if payment.status != PaymentStatus.PENDING:
        reasons.append("payment_not_pending")

    if payment.amount != amount:
        reasons.append("amount_mismatch")

    if payment.amount != form_amount or form_amount != amount:
        reasons.append("form_amount_mismatch")

    if contract.status != ContractStatus.ACTIVE:
        reasons.append("contract_inactive")

    if payment.amount > calculate_balance(
        contract.id, db
    )["remaining_amount"]:
        reasons.append("balance_exceeded")

    allocations = None
    if not reasons:
        try:
            allocations = prepare_confirmation(payment, contract, db)
        except HTTPException:
            reasons.append("period_allocation_conflict")

    if reasons:
        transaction.status = "review"
        transaction.review_reason = ",".join(reasons)
        logger.warning(
            "Finik webhook sent payment %s to review: %s",
            payment.id, transaction.review_reason
        )
    else:
        now = datetime.utcnow()
        save_allocations(payment, db, allocations)
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
