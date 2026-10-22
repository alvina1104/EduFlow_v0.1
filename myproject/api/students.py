from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from myproject.database.db import get_db
from myproject.database.models import User, Student, PersonalInfo, Group
from myproject.database.schemas import StudentCreateSchema, StudentResponseSchema
from myproject.core.dependencies import get_current_admin, get_current_student
from myproject.core.security import hash_password

students_router = APIRouter(prefix="/students", tags=["Students"])


@students_router.post("/", response_model=StudentResponseSchema, status_code=201)
def create_student(data: StudentCreateSchema, db: Session = Depends(get_db), admin: User = Depends(get_current_admin)):
    if db.query(User).filter(User.username == data.username).first():
        raise HTTPException(409, "Такой username уже существует")
    if db.query(Student).filter(Student.student_number == data.student_number).first():
        raise HTTPException(409, "Такой номер студента уже существует")
    if data.group_id and not db.query(Group).filter(Group.id == data.group_id).first():
        raise HTTPException(404, "Группа не найдена")

    try:
        user = User(username=data.username, hashed_password=hash_password(data.password), role="student", is_active=True)
        db.add(user)
        db.flush()

        student = Student(user_id=user.id, student_number=data.student_number, group_id=data.group_id)
        db.add(student)
        db.flush()

        info = PersonalInfo(student_id=student.id, **data.personal_info.model_dump())
        db.add(info)
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