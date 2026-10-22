from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from myproject.database.db import get_db
from myproject.database.models import Contract, Student, User, UserRole, ContractStatus
from myproject.database.schemas import ContractCreateSchema, ContractResponseSchema
from myproject.core.dependencies import get_current_admin, get_current_student, get_current_user

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
    contract = db.query(Contract).filter(Contract.id == contract_id).first()
    if not contract:
        raise HTTPException(404, "Контракт не найден")
    if data.total_amount <= 0 or data.monthly_payment <= 0 or data.duration_months <= 0:
        raise HTTPException(400, "Суммы и срок должны быть положительными")

    for key, value in data.model_dump().items():
        setattr(contract, key, value)
    db.commit()
    db.refresh(contract)
    return contract


@contracts_router.delete("/{contract_id}", status_code=204)
def delete_contract(contract_id: int, db: Session = Depends(get_db), admin: User = Depends(get_current_admin)):
    contract = db.query(Contract).filter(Contract.id == contract_id).first()
    if not contract:
        raise HTTPException(404, "Контракт не найден")
    db.delete(contract)
    db.commit()