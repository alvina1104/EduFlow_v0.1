from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from myproject.database.db import get_db
from myproject.database.models import Student, PersonalInfo, User
from myproject.database.schemas import PersonalInfoCreateSchema, PersonalInfoResponseSchema
from myproject.core.dependencies import get_current_admin, get_current_student

personal_info_router = APIRouter(prefix="/personal-info", tags=["Personal Info"])


@personal_info_router.post("/{student_id}", response_model=PersonalInfoResponseSchema, status_code=201)
def create_personal_info(student_id: int, data: PersonalInfoCreateSchema, db: Session = Depends(get_db), admin: User = Depends(get_current_admin)):
    student = db.query(Student).filter(Student.id == student_id).first()
    if not student:
        raise HTTPException(404, "Студент не найден")
    if student.personal_info:
        raise HTTPException(409, "Личные данные уже существуют")

    info = PersonalInfo(student_id=student_id, **data.model_dump())
    db.add(info)
    db.commit()
    db.refresh(info)
    return info


@personal_info_router.get("/me", response_model=PersonalInfoResponseSchema)
def get_my_personal_info(student: Student = Depends(get_current_student), db: Session = Depends(get_db)):
    info = db.query(PersonalInfo).filter(PersonalInfo.student_id == student.id).first()
    if not info:
        raise HTTPException(404, "Личные данные не найдены")
    return info


@personal_info_router.get("/{student_id}", response_model=PersonalInfoResponseSchema)
def get_personal_info(student_id: int, db: Session = Depends(get_db), admin: User = Depends(get_current_admin)):
    info = db.query(PersonalInfo).filter(PersonalInfo.student_id == student_id).first()
    if not info:
        raise HTTPException(404, "Личные данные не найдены")
    return info


@personal_info_router.put("/me", response_model=PersonalInfoResponseSchema)
def update_my_personal_info(data: PersonalInfoCreateSchema, student: Student = Depends(get_current_student), db: Session = Depends(get_db)):
    info = db.query(PersonalInfo).filter(PersonalInfo.student_id == student.id).first()
    if not info:
        raise HTTPException(404, "Личные данные не найдены")

    for key, value in data.model_dump().items():
        setattr(info, key, value)
    db.commit()
    db.refresh(info)
    return info


@personal_info_router.put("/{student_id}", response_model=PersonalInfoResponseSchema)
def update_personal_info(student_id: int, data: PersonalInfoCreateSchema, db: Session = Depends(get_db), admin: User = Depends(get_current_admin)):
    info = db.query(PersonalInfo).filter(PersonalInfo.student_id == student_id).first()
    if not info:
        raise HTTPException(404, "Личные данные не найдены")

    for key, value in data.model_dump().items():
        setattr(info, key, value)
    db.commit()
    db.refresh(info)
    return info


@personal_info_router.delete("/{student_id}", status_code=204)
def delete_personal_info(student_id: int, db: Session = Depends(get_db), admin: User = Depends(get_current_admin)):
    info = db.query(PersonalInfo).filter(PersonalInfo.student_id == student_id).first()
    if not info:
        raise HTTPException(404, "Личные данные не найдены")
    db.delete(info)
    db.commit()