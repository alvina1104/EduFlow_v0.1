from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from myproject.database.db import get_db
from myproject.database.models import Payment, Contract, Student, User, UserRole, PaymentStatus, ContractStatus
from myproject.database.schemas import PaymentCreateSchema, PaymentStatusUpdateSchema, PaymentResponseSchema
from myproject.core.dependencies import get_current_admin, get_current_student, get_current_user

payments_router = APIRouter(prefix="/payments", tags=["Payments"])


def calculate_balance(contract_id: int, db: Session):
    contract = db.query(Contract).filter(Contract.id == contract_id).first()
    if not contract:
        raise HTTPException(404, "Контракт не найден")
    paid = db.query(func.coalesce(func.sum(Payment.amount), 0)).filter(
        Payment.contract_id == contract_id, Payment.status == PaymentStatus.CONFIRMED).scalar()
    return {"contract_id": contract.id, "total_amount": contract.total_amount,
            "paid_amount": paid, "remaining_amount": max(contract.total_amount - paid, 0),
            "paid_months": int(paid // contract.monthly_payment) if contract.monthly_payment > 0 else 0,
            "duration_months": contract.duration_months}



@payments_router.post("/", response_model=PaymentResponseSchema, status_code=201)
def create_payment(data: PaymentCreateSchema, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    contract = db.query(Contract).filter(Contract.id == data.contract_id).with_for_update().first()
    if not contract:
        raise HTTPException(404, "Контракт не найден")

    if user.role == UserRole.STUDENT:
        student = db.query(Student).filter(Student.user_id == user.id).first()
        if not student or contract.student_id != student.id:
            raise HTTPException(403, "Нет доступа к контракту")
    elif user.role != UserRole.ADMIN:
        raise HTTPException(403, "Нет доступа")

    request_id = str(data.request_id)
    payment = db.query(Payment).filter(Payment.request_id == request_id).first()

    if payment:
        if (payment.created_by_user_id != user.id or payment.contract_id != data.contract_id
                or payment.amount != data.amount or payment.payment_method != data.payment_method
                or payment.payment_month != data.payment_month):
            raise HTTPException(409, "Этот request_id уже используется")
        return payment

    if contract.status != ContractStatus.ACTIVE:
        raise HTTPException(409, "Контракт не активен")

    if user.role == UserRole.ADMIN:
        if not data.payment_method or not data.payment_method.strip():
            raise HTTPException(422, "Укажите способ оплаты")
        if data.amount > calculate_balance(contract.id, db)["remaining_amount"]:
            raise HTTPException(409, "Сумма превышает остаток контракта")

    payment = Payment(
        contract_id=contract.id,
        request_id=request_id,
        created_by_user_id=user.id,
        amount=data.amount,
        payment_method=data.payment_method,
        payment_month=data.payment_month,
        status=PaymentStatus.CONFIRMED if user.role == UserRole.ADMIN else PaymentStatus.PENDING,
        confirmed_by_admin_id=user.id if user.role == UserRole.ADMIN else None,
        paid_at=datetime.utcnow() if user.role == UserRole.ADMIN else None
    )

    db.add(payment)
    try:
        db.commit()
        db.refresh(payment)
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Платёж с таким request_id уже существует")

    return payment



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
def get_payment(payment_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    payment = db.query(Payment).filter(Payment.id == payment_id).first()
    if not payment:
        raise HTTPException(404, "Платёж не найден")
    if user.role == UserRole.STUDENT:
        student = db.query(Student).filter(Student.user_id == user.id).first()
        if not student or payment.contract.student_id != student.id:
            raise HTTPException(403, "Нет доступа к этому платежу")
    return payment



@payments_router.patch("/{payment_id}/status", response_model=PaymentResponseSchema)
def update_payment_status(payment_id: int, data: PaymentStatusUpdateSchema, db: Session = Depends(get_db), admin: User = Depends(get_current_admin)):
    payment = db.query(Payment).filter(Payment.id == payment_id).first()
    if not payment:
        raise HTTPException(404, "Платёж не найден")

    contract = db.query(Contract).filter(Contract.id == payment.contract_id).with_for_update().first()
    payment = db.query(Payment).filter(Payment.id == payment_id).with_for_update().first()

    if payment.status != PaymentStatus.PENDING:
        raise HTTPException(409, "Платёж уже обработан")
    if data.status not in (PaymentStatus.CONFIRMED, PaymentStatus.REJECTED):
        raise HTTPException(400, "Можно только подтвердить или отклонить платёж")
    if contract.status != ContractStatus.ACTIVE:
        raise HTTPException(409, "Контракт не активен")

    if data.status == PaymentStatus.CONFIRMED:
        balance = calculate_balance(contract.id, db)
        if payment.amount > balance["remaining_amount"]:
            raise HTTPException(409, "Сумма платежа превышает остаток контракта")

    payment.status = data.status
    payment.confirmed_by_admin_id = admin.id
    payment.paid_at = datetime.utcnow() if data.status == PaymentStatus.CONFIRMED else None

    db.commit()
    db.refresh(payment)
    return payment



@payments_router.delete("/{payment_id}", status_code=204)
def delete_payment(payment_id: int, db: Session = Depends(get_db), admin: User = Depends(get_current_admin)):
    payment = db.query(Payment).filter(Payment.id == payment_id).first()
    if not payment:
        raise HTTPException(404, "Платёж не найден")
    if payment.status == PaymentStatus.CONFIRMED:
        raise HTTPException(400, "Подтверждённый платёж нельзя удалить")
    db.delete(payment)
    db.commit()
