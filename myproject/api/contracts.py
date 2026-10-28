from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from myproject.database.db import get_db
from myproject.database.models import (Contract, Student, User, UserRole, ContractStatus, Payment,
                                       AcademicLeave)
from myproject.database.schemas import (ContractCreateSchema, ContractResponseSchema,
                                        AcademicLeaveCreateSchema, AcademicLeaveResponseSchema)
from myproject.core.dependencies import get_current_admin, get_current_student, get_current_user
from datetime import datetime, timezone

contracts_router = APIRouter(prefix="/contracts", tags=["Contracts"])


@contracts_router.post("/", response_model=ContractResponseSchema, status_code=201)
def create_contract(data: ContractCreateSchema, db: Session = Depends(get_db), admin: User = Depends(get_current_admin)):
    student = db.query(Student).filter(Student.id == data.student_id).first()
    if not student:
        raise HTTPException(404, "Студент не найден")
    if data.total_amount <= 0 or data.monthly_payment <= 0 or data.duration_months <= 0:
        raise HTTPException(400, "Суммы и срок должны быть положительными")

    contract = Contract(**data.model_dump(), status=ContractStatus.ACTIVE)
    db.add(contract)
    db.commit()
    db.refresh(contract)
    return contract


@contracts_router.get("/", response_model=list[ContractResponseSchema])
def get_contracts(db: Session = Depends(get_db), admin: User = Depends(get_current_admin)):
    return db.query(Contract).all()


@contracts_router.get("/my", response_model=list[ContractResponseSchema])
def get_my_contracts(student: Student = Depends(get_current_student), db: Session = Depends(get_db)):
    return db.query(Contract).filter(Contract.student_id == student.id).all()


@contracts_router.get("/{contract_id}", response_model=ContractResponseSchema)
def get_contract(contract_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    contract = db.query(Contract).filter(Contract.id == contract_id).first()
    if not contract:
        raise HTTPException(404, "Контракт не найден")
    if user.role == UserRole.STUDENT and contract.student.user_id != user.id:
        raise HTTPException(403, "Нет доступа к этому контракту")
    return contract



@contracts_router.put("/{contract_id}", response_model=ContractResponseSchema)
def update_contract(contract_id: int, data: ContractCreateSchema, db: Session = Depends(get_db), admin: User = Depends(get_current_admin)):
    contract = db.query(Contract).filter(Contract.id == contract_id).with_for_update().first()
    if not contract:
        raise HTTPException(404, "Контракт не найден")
    if db.query(Payment.id).filter(Payment.contract_id == contract_id).first():
        raise HTTPException(409, "Контракт с платежами нельзя изменять")
    if data.total_amount <= 0 or data.monthly_payment <= 0 or data.duration_months <= 0:
        raise HTTPException(400, "Суммы и срок должны быть положительными")


    for key, value in data.model_dump().items():
        setattr(contract, key, value)
    db.commit()
    db.refresh(contract)
    return contract



@contracts_router.delete("/{contract_id}", status_code=204)
def delete_contract(contract_id: int, db: Session = Depends(get_db), admin: User = Depends(get_current_admin)):
    contract = db.query(Contract).filter(Contract.id == contract_id).with_for_update().first()
    if not contract:
        raise HTTPException(404, "Контракт не найден")

    if db.query(Payment.id).filter(Payment.contract_id == contract_id).first():
        raise HTTPException(409, "Нельзя удалить контракт с историей платежей")

    try:
        db.delete(contract)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Не удалось удалить контракт")




@contracts_router.post("/{contract_id}/leaves", response_model=AcademicLeaveResponseSchema, status_code=201)
def create_academic_leave(contract_id: int, data: AcademicLeaveCreateSchema, db: Session = Depends(get_db), admin: User = Depends(get_current_admin)):
    contract = db.query(Contract).filter(Contract.id == contract_id).with_for_update().first()
    if not contract:
        raise HTTPException(404, "Контракт не найден")
    if contract.status != ContractStatus.ACTIVE:
        raise HTTPException(409, "Контракт не активен")

    conflict = db.query(AcademicLeave).filter(
        AcademicLeave.contract_id == contract_id,
        AcademicLeave.cancelled_at.is_(None),
        AcademicLeave.start_date <= data.end_date,
        AcademicLeave.end_date >= data.start_date
    ).first()
    if conflict:
        raise HTTPException(409, "Академический отпуск пересекается с существующим")

    leave = AcademicLeave(contract_id=contract_id, created_by_admin_id=admin.id, **data.model_dump())
    db.add(leave)
    try:
        db.commit()
        db.refresh(leave)
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Не удалось сохранить академический отпуск")
    return leave


@contracts_router.delete("/{contract_id}/leaves/{leave_id}", status_code=204)
def cancel_academic_leave(contract_id: int, leave_id: int, db: Session = Depends(get_db), admin: User = Depends(get_current_admin)):
    contract = db.query(Contract).filter(Contract.id == contract_id).with_for_update().first()
    if not contract:
        raise HTTPException(404, "Контракт не найден")

    leave = db.query(AcademicLeave).filter(
        AcademicLeave.id == leave_id, AcademicLeave.contract_id == contract_id
    ).first()
    if not leave:
        raise HTTPException(404, "Академический отпуск не найден")
    if leave.cancelled_at is not None:
        raise HTTPException(409, "Академический отпуск уже отменён")

    leave.cancelled_at = datetime.now(timezone.utc)
    db.commit()
