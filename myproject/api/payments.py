from datetime import date, datetime
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from myproject.database.db import get_db
from myproject.database.models import (
    Payment, Contract, Student, User, UserRole,
    PaymentStatus, ContractStatus, ContractType
)
from myproject.database.schemas import PaymentCreateSchema, PaymentStatusUpdateSchema, PaymentResponseSchema
from myproject.core.dependencies import get_current_admin, get_current_student, get_current_user
from myproject.services.schedule import (
    contract_periods, current_month, find_contract_period
)
from myproject.services.payment_allocation import (
    payment_plan, confirmed_by_period, distribute_payment,
    prepare_confirmation, save_allocations
)

payments_router = APIRouter(prefix="/payments", tags=["Payments"])


def get_reserved_amount(
    contract_id: int,
    db: Session,
    exclude_payment_id: int | None = None
):
    query = db.query(func.coalesce(func.sum(Payment.amount), 0)).filter(
        Payment.contract_id == contract_id,
        Payment.status.in_([
            PaymentStatus.PENDING,
            PaymentStatus.CONFIRMED
        ])
    )

    if exclude_payment_id is not None:
        query = query.filter(Payment.id != exclude_payment_id)

    return query.scalar()


def calculate_balance(contract_id: int, db: Session):
    contract = db.query(Contract).filter(Contract.id == contract_id).first()

    if not contract:
        raise HTTPException(404, "Контракт не найден")

    paid = db.query(func.coalesce(func.sum(Payment.amount), 0)).filter(
        Payment.contract_id == contract_id,
        Payment.status == PaymentStatus.CONFIRMED
    ).scalar()

    remaining = contract.total_amount - paid

    paid_months = None
    overdue_months = None
    overdue_amount = Decimal("0")
    next_due_date = None
    next_due_amount = None
    installment_count = None
    paid_installments = None
    next_installment_amount = None

    plan = payment_plan(contract)
    paid_by_period = confirmed_by_period(contract, db)

    if contract.type == ContractType.ACADEMY:
        paid_months = 0
        overdue_months = 0
        today = date.today()

        for period in plan:
            outstanding = max(
                Decimal("0"), period["amount"] - paid_by_period[period["index"]]
            )
            if outstanding <= 0:
                paid_months += 1
                continue

            if next_due_date is None:
                next_due_date = period["due_date"]
                next_due_amount = outstanding

            if period["due_date"] < today:
                overdue_months += 1
                overdue_amount += outstanding

        overdue_amount = min(overdue_amount, max(remaining, Decimal("0")))
    else:
        installment_count = len(plan)
        paid_installments = sum(
            paid_by_period[p["index"]] >= p["amount"] for p in plan
        )
        next_installment_amount = next(
            (p["amount"] - paid_by_period[p["index"]]
             for p in plan if paid_by_period[p["index"]] < p["amount"]),
            Decimal("0"),
        )

    return {
        "contract_id": contract.id,
        "total_amount": contract.total_amount,
        "paid_amount": paid,
        "remaining_amount": remaining,
        "paid_months": paid_months,
        "duration_months": contract.duration_months,
        "overdue_months": overdue_months,
        "overdue_amount": overdue_amount,
        "next_due_date": next_due_date,
        "next_due_amount": next_due_amount,
        "installment_count": installment_count,
        "paid_installments": paid_installments,
        "next_installment_amount": next_installment_amount
    }


def get_month_paid(contract_id: int, payment_month: str, db: Session):
    """Учитывает multi-month allocations и старые записи."""
    contract = db.query(Contract).filter(Contract.id == contract_id).first()
    if not contract:
        raise HTTPException(404, "Контракт не найден")
    period = find_contract_period(contract, payment_month)
    if period is None:
        return Decimal("0")
    return confirmed_by_period(contract, db).get(period.index, Decimal("0"))


def _create_payment(
    data: PaymentCreateSchema,
    db: Session,
    user: User,
    allow_finik: bool = False
):
    if allow_finik:
        if data.payment_method != "finik" or user.role != UserRole.STUDENT:
            raise HTTPException(403, "Нет доступа")
    elif user.role != UserRole.ADMIN:
        raise HTTPException(403, "Наличные платежи регистрирует только администратор")
    elif data.payment_method != "cash":
        raise HTTPException(422, "Администратор может зарегистрировать только наличный платёж")

    contract = db.query(Contract).filter(
        Contract.id == data.contract_id
    ).with_for_update().first()

    if not contract:
        raise HTTPException(404, "Контракт не найден")

    if user.role == UserRole.STUDENT:
        student = db.query(Student).filter(Student.user_id == user.id).first()

        if not student or contract.student_id != student.id:
            raise HTTPException(403, "Нет доступа к контракту")

    elif user.role != UserRole.ADMIN:
        raise HTTPException(403, "Нет доступа")

    # Проверка номера месяца выполняется после идемпотентного поиска запроса:
    # повторный request_id обязан возвращать исходный платёж.
    payment_month = data.payment_month or current_month()

    request_id = str(data.request_id)

    payment = db.query(Payment).filter(
        Payment.request_id == request_id
    ).first()

    if payment:
        if (
            payment.created_by_user_id != user.id
            or payment.contract_id != data.contract_id
            or payment.amount != data.amount
            or payment.payment_method != data.payment_method
            or (data.payment_month is not None and payment.payment_month != data.payment_month
                and contract.type == ContractType.ACADEMY)
            or (contract.type == ContractType.COLLEGE
                and payment.payment_month != payment_month)
        ):
            raise HTTPException(409, "Этот request_id уже используется")

        return payment

    if contract.status != ContractStatus.ACTIVE:
        raise HTTPException(409, "Контракт не активен")

    # Пока Finik ожидает webhook, новый платёж по этому контракту
    # не создаём: иначе можно зарезервировать одни и те же периоды.
    pending = db.query(Payment.id).filter(
        Payment.contract_id == contract.id,
        Payment.status == PaymentStatus.PENDING
    ).first()
    if pending:
        raise HTTPException(409, "Сначала завершите ожидающий платёж")

    reserved = get_reserved_amount(contract.id, db)
    if data.amount > contract.total_amount - reserved:
        raise HTTPException(409, "Сумма превышает доступный остаток")

    allocation_rows = distribute_payment(
        contract, db, data.amount,
        requested_month=data.payment_month if contract.type == ContractType.ACADEMY else None
    )
    if contract.type == ContractType.ACADEMY:
        payment_month = allocation_rows[0]["payment_month"]

    if user.role == UserRole.ADMIN:
        if not data.payment_method or not data.payment_method.strip():
            raise HTTPException(422, "Укажите способ оплаты")

    payment = Payment(
        contract_id=contract.id,
        request_id=request_id,
        created_by_user_id=user.id,
        amount=data.amount,
        payment_method=data.payment_method,
        payment_month=payment_month,
        status=(
            PaymentStatus.CONFIRMED
            if user.role == UserRole.ADMIN
            else PaymentStatus.PENDING
        ),
        confirmed_by_admin_id=(
            user.id if user.role == UserRole.ADMIN else None
        ),
        paid_at=(
            datetime.utcnow()
            if user.role == UserRole.ADMIN else None
        )
    )

    db.add(payment)
    save_allocations(payment, db, allocation_rows)

    try:
        db.commit()
        db.refresh(payment)
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Платёж с таким request_id уже существует")

    return payment


@payments_router.post("/", response_model=PaymentResponseSchema, status_code=201)
def create_payment(
    data: PaymentCreateSchema,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    return _create_payment(data, db, user)


@payments_router.get("/", response_model=list[PaymentResponseSchema])
def get_payments(db: Session = Depends(get_db), admin: User = Depends(get_current_admin)):
    return db.query(Payment).all()


@payments_router.get("/my", response_model=list[PaymentResponseSchema])
def get_my_payments(student: Student = Depends(get_current_student), db: Session = Depends(get_db)):
    return db.query(Payment).join(Contract).filter(Contract.student_id == student.id).all()


@payments_router.get("/my/balance")
def get_my_balance(student: Student = Depends(get_current_student), db: Session = Depends(get_db)):
    contracts = db.query(Contract).filter(Contract.student_id == student.id).all()
    return [calculate_balance(contract.id, db) for contract in contracts]


@payments_router.get("/{payment_id}", response_model=PaymentResponseSchema)
def get_payment(
    payment_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    payment = db.query(Payment).filter(Payment.id == payment_id).first()

    if not payment:
        raise HTTPException(404, "Платёж не найден")

    if user.role == UserRole.STUDENT:
        student = db.query(Student).filter(Student.user_id == user.id).first()

        if not student or payment.contract.student_id != student.id:
            raise HTTPException(403, "Нет доступа к этому платежу")

    return payment


@payments_router.patch("/{payment_id}/status", response_model=PaymentResponseSchema)
def update_payment_status(
    payment_id: int,
    data: PaymentStatusUpdateSchema,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin)
):
    payment = db.query(Payment).filter(Payment.id == payment_id).first()

    if not payment:
        raise HTTPException(404, "Платёж не найден")

    contract = db.query(Contract).filter(
        Contract.id == payment.contract_id
    ).with_for_update().first()

    payment = db.query(Payment).filter(
        Payment.id == payment_id
    ).with_for_update().populate_existing().first()

    if payment.status != PaymentStatus.PENDING:
        raise HTTPException(409, "Платёж уже обработан")

    if payment.payment_method == "finik":
        raise HTTPException(409, "Платёж Finik подтверждается автоматически")

    if data.status not in (PaymentStatus.CONFIRMED, PaymentStatus.REJECTED):
        raise HTTPException(400, "Можно только подтвердить или отклонить платёж")

    if data.status == PaymentStatus.CONFIRMED:
        if contract.status != ContractStatus.ACTIVE:
            raise HTTPException(409, "Контракт не активен")

        allocations = prepare_confirmation(payment, contract, db)

        balance = calculate_balance(contract.id, db)
        if payment.amount > balance["remaining_amount"]:
            raise HTTPException(409, "Сумма превышает остаток контракта")
        save_allocations(payment, db, allocations)

    payment.status = data.status
    payment.confirmed_by_admin_id = admin.id
    payment.paid_at = (
        datetime.utcnow()
        if data.status == PaymentStatus.CONFIRMED else None
    )

    db.commit()
    db.refresh(payment)

    return payment


@payments_router.delete("/{payment_id}", status_code=204)
def delete_payment(
    payment_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin)
):
    payment = db.query(Payment).filter(
        Payment.id == payment_id
    ).with_for_update().first()

    if not payment:
        raise HTTPException(404, "Платёж не найден")

    raise HTTPException(409, "Платежи нельзя удалять из финансовой истории")
