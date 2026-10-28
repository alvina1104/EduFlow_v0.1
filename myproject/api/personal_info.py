from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from myproject.database.db import get_db
from myproject.database.models import Student, PersonalInfo, User, PersonalInfoStatus
from myproject.database.schemas import PersonalInfoCreateSchema, PersonalInfoResponseSchema, PersonalInfoReviewSchema
from myproject.core.dependencies import get_current_admin, get_current_student

personal_info_router = APIRouter(prefix="/personal-info", tags=["Personal Info"])


@personal_info_router.post("/{student_id}", response_model=PersonalInfoResponseSchema, status_code=201)
def create_personal_info(student_id: int, data: PersonalInfoCreateSchema, db: Session = Depends(get_db), admin: User = Depends(get_current_admin)):
    student = db.query(Student).filter(Student.id == student_id).first()
    if not student:
        raise HTTPException(404, "Студент не найден")
    if student.personal_info:
        raise HTTPException(409, "Личные данные уже существуют")

    info = PersonalInfo(student_id=student_id, **data.model_dump(), status=PersonalInfoStatus.PENDING)
    db.add(info)
    try:
        db.commit()
        db.refresh(info)
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Не удалось создать анкету")
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
    info = db.query(PersonalInfo).filter(PersonalInfo.student_id == student.id).with_for_update().first()
    values = data.model_dump()

    if not info:
        info = PersonalInfo(student_id=student.id, **values, status=PersonalInfoStatus.PENDING)
        db.add(info)
    elif info.status == PersonalInfoStatus.REVISION or any(getattr(info, key) != value for key, value in values.items()):
        for key, value in values.items():
            setattr(info, key, value)
        info.status = PersonalInfoStatus.PENDING
        info.review_comment = None
        info.reviewed_by_admin_id = None
        info.reviewed_at = None

    try:
        db.commit()
        db.refresh(info)
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Не удалось сохранить анкету")
    return info


@personal_info_router.put("/{student_id}", response_model=PersonalInfoResponseSchema)
def update_personal_info(student_id: int, data: PersonalInfoCreateSchema, db: Session = Depends(get_db), admin: User = Depends(get_current_admin)):
    info = db.query(PersonalInfo).filter(PersonalInfo.student_id == student_id).with_for_update().first()
    if not info:
        raise HTTPException(404, "Личные данные не найдены")

    values = data.model_dump()
    if any(getattr(info, key) != value for key, value in values.items()):
        for key, value in values.items():
            setattr(info, key, value)
        info.status = PersonalInfoStatus.PENDING
        info.review_comment = None
        info.reviewed_by_admin_id = None
        info.reviewed_at = None

    db.commit()
    db.refresh(info)
    return info


@personal_info_router.patch("/{student_id}/review", response_model=PersonalInfoResponseSchema)
def review_personal_info(student_id: int, data: PersonalInfoReviewSchema, db: Session = Depends(get_db), admin: User = Depends(get_current_admin)):
    info = db.query(PersonalInfo).filter(PersonalInfo.student_id == student_id).with_for_update().first()
    if not info:
        raise HTTPException(404, "Анкета не найдена")
    if info.status != PersonalInfoStatus.PENDING:
        raise HTTPException(409, "Анкета не ожидает проверки")
    if data.status == PersonalInfoStatus.REVISION and not (data.comment and data.comment.strip()):
        raise HTTPException(422, "Укажите причину возврата на исправление")

    info.status = data.status
    info.review_comment = data.comment.strip() if data.status == PersonalInfoStatus.REVISION else None
    info.reviewed_by_admin_id = admin.id
    info.reviewed_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(info)
    return info


@personal_info_router.delete("/{student_id}", status_code=204)
def delete_personal_info(student_id: int, db: Session = Depends(get_db), admin: User = Depends(get_current_admin)):
    info = db.query(PersonalInfo).filter(PersonalInfo.student_id == student_id).first()
    if not info:
        raise HTTPException(404, "Личные данные не найдены")

    db.delete(info)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Не удалось удалить анкету")
