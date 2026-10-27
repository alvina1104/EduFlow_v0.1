from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.exc import IntegrityError
from myproject.database.db import get_db
from myproject.database.models import (
    User, UserRole, Student, PersonalInfo, Group,
    StudentGroupHistory, StudentGroupHistoryKind,
)
from myproject.database.schemas import (
    StudentCreateSchema, StudentResponseSchema, StudentUpdateSchema,
    StudentGroupHistoryResponseSchema,
)
from myproject.core.dependencies import get_current_admin, get_current_student
from myproject.core.security import hash_password

students_router = APIRouter(prefix="/students", tags=["Students"])


@students_router.post("/", response_model=StudentResponseSchema, status_code=201)
def create_student(data: StudentCreateSchema, db: Session = Depends(get_db), admin: User = Depends(get_current_admin)):
    if db.query(User).filter(User.username == data.username).first():
        raise HTTPException(409, "Такой username уже существует")
    if db.query(Student).filter(Student.student_number == data.student_number).first():
        raise HTTPException(409, "Такой номер студента уже существует")
    if data.group_id is not None and not db.query(Group).filter(Group.id == data.group_id).first():
        raise HTTPException(404, "Группа не найдена")

    try:
        user = User(username=data.username, hashed_password=hash_password(data.password), role=UserRole.STUDENT, is_active=True)
        db.add(user)
        db.flush()

        student = Student(user_id=user.id, student_number=data.student_number, group_id=data.group_id)
        db.add(student)
        db.flush()

        info = PersonalInfo(student_id=student.id, **data.personal_info.model_dump())
        db.add(info)
        if data.group_id is not None:
            db.add(StudentGroupHistory(
                student_id=student.id,
                group_id=data.group_id,
                kind=StudentGroupHistoryKind.ENROLLMENT,
                from_date=datetime.now(timezone.utc).date(),
            ))
        db.commit()
        db.refresh(student)
        return student
    except IntegrityError:
        db.rollback()
        raise HTTPException(400, "Не удалось создать студента")


@students_router.get("/", response_model=list[StudentResponseSchema])
def get_students(db: Session = Depends(get_db), admin: User = Depends(get_current_admin)):
    return db.query(Student).all()


@students_router.get("/me", response_model=StudentResponseSchema)
def get_my_student(student: Student = Depends(get_current_student)):
    return student


@students_router.get("/{student_id}", response_model=StudentResponseSchema)
def get_student(student_id: int, db: Session = Depends(get_db), admin: User = Depends(get_current_admin)):
    student = db.query(Student).filter(Student.id == student_id).first()
    if not student:
        raise HTTPException(404, "Студент не найден")
    return student


@students_router.patch("/{student_id}", response_model=StudentResponseSchema)
def update_student(
    student_id: int,
    data: StudentUpdateSchema,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    # Lock the student row so two concurrent transfers cannot create overlapping history.
    student = db.query(Student).filter(Student.id == student_id).with_for_update().first()
    if student is None:
        raise HTTPException(404, "Студент не найден")

    if "student_number" in data.model_fields_set:
        if data.student_number is None:
            raise HTTPException(422, "student_number не может быть null")
        if data.student_number != student.student_number:
            duplicate = db.query(Student).filter(
                Student.student_number == data.student_number,
                Student.id != student_id,
            ).first()
            if duplicate:
                raise HTTPException(409, "Такой номер студента уже существует")
            student.student_number = data.student_number

    if "group_id" in data.model_fields_set and data.group_id != student.group_id:
        if data.group_id is not None and db.get(Group, data.group_id) is None:
            raise HTTPException(404, "Группа не найдена")

        today = datetime.now(timezone.utc).date()
        active = db.query(StudentGroupHistory).filter(
            StudentGroupHistory.student_id == student.id,
            StudentGroupHistory.to_date.is_(None),
        ).with_for_update().first()
        has_history = db.query(StudentGroupHistory.id).filter(
            StudentGroupHistory.student_id == student.id
        ).first() is not None

        if active is not None:
            if active.group_id != student.group_id:
                raise HTTPException(409, "История групп не совпадает с текущей группой")
            active.to_date = today
        elif student.group_id is not None:
            # Existing students may lack a history record; never invent an enrollment date.
            db.add(StudentGroupHistory(
                student_id=student.id,
                group_id=student.group_id,
                kind=StudentGroupHistoryKind.TRANSFER if has_history else StudentGroupHistoryKind.ENROLLMENT,
                from_date=None,
                to_date=today,
            ))

        if data.group_id is not None:
            db.add(StudentGroupHistory(
                student_id=student.id,
                group_id=data.group_id,
                kind=StudentGroupHistoryKind.TRANSFER if (has_history or student.group_id is not None) else StudentGroupHistoryKind.ENROLLMENT,
                from_date=today,
            ))
        student.group_id = data.group_id

    try:
        db.commit()
        db.refresh(student)
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Не удалось обновить студента: конфликт данных")
    return student


def _get_group_history(student_id: int, db: Session):
    return (
        db.query(StudentGroupHistory)
        .options(joinedload(StudentGroupHistory.group))
        .filter(StudentGroupHistory.student_id == student_id)
        .order_by(StudentGroupHistory.id.asc())
        .all()
    )


@students_router.get("/me/groups", response_model=list[StudentGroupHistoryResponseSchema])
def get_my_group_history(student: Student = Depends(get_current_student), db: Session = Depends(get_db)):
    return _get_group_history(student.id, db)


@students_router.get("/{student_id}/groups", response_model=list[StudentGroupHistoryResponseSchema])
def get_student_group_history(
    student_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    if db.get(Student, student_id) is None:
        raise HTTPException(404, "Студент не найден")
    return _get_group_history(student_id, db)


@students_router.delete("/{student_id}", status_code=204)
def delete_student(student_id: int, db: Session = Depends(get_db), admin: User = Depends(get_current_admin)):
    student = db.query(Student).filter(Student.id == student_id).first()
    if not student:
        raise HTTPException(404, "Студент не найден")

    user = db.query(User).filter(User.id == student.user_id).first()
    try:
        db.delete(student)
        if user:
            db.delete(user)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Студента нельзя удалить: есть связанные данные")