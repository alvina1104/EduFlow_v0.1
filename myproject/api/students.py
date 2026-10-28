from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from myproject.database.db import get_db
from myproject.database.models import (User, Student, PersonalInfo, Group, StudentGroupHistoryKind,
                                       StudentGroupHistory, UserRole)
from myproject.database.schemas import StudentCreateSchema, StudentResponseSchema,StudentUpdateSchema
from myproject.core.dependencies import get_current_admin, get_current_student, get_current_user
from myproject.core.security import hash_password
from datetime import date
from io import BytesIO
from fastapi import File, UploadFile, Response
from PIL import Image, ImageOps, UnidentifiedImageError


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

        if data.personal_info is not None:
            info = PersonalInfo(student_id=student.id, **data.personal_info.model_dump())
            db.add(info)

        if data.group_id is not None:
            db.add(StudentGroupHistory(student_id=student.id, group_id=data.group_id,
                                       kind=StudentGroupHistoryKind.ENROLLMENT,
                                       from_date=date.today(), to_date=None))

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
def update_student(student_id: int, data: StudentUpdateSchema, db: Session = Depends(get_db), admin: User = Depends(get_current_admin)):
    student = db.query(Student).filter(Student.id == student_id).with_for_update().first()
    if not student:
        raise HTTPException(404, "Студент не найден")

    changes = data.model_dump(exclude_unset=True)

    if "student_number" in changes:
        if changes["student_number"] is None:
            raise HTTPException(422, "Номер студента не может быть null")
        student.student_number = changes["student_number"]

    if "group_id" in changes:
        new_group_id = changes["group_id"]
        old_group_id = student.group_id

        if new_group_id is not None and not db.query(Group).filter(Group.id == new_group_id).first():
            raise HTTPException(404, "Группа не найдена")

        if new_group_id != old_group_id:
            today = date.today()
            history = db.query(StudentGroupHistory).filter(
                StudentGroupHistory.student_id == student.id,
                StudentGroupHistory.to_date.is_(None)
            ).first()

            if history:
                history.to_date = today
            elif old_group_id is not None:
                db.add(StudentGroupHistory(student_id=student.id, group_id=old_group_id,
                                           kind=StudentGroupHistoryKind.ENROLLMENT,
                                           from_date=None, to_date=today))

            if new_group_id is not None:
                db.add(StudentGroupHistory(student_id=student.id, group_id=new_group_id,
                                           kind=StudentGroupHistoryKind.TRANSFER,
                                           from_date=today, to_date=None))

            student.group_id = new_group_id

    try:
        db.commit()
        db.refresh(student)
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Конфликт данных студента")

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

@students_router.put("/me/photo")
def upload_my_photo(file: UploadFile = File(...), student: Student = Depends(get_current_student), db: Session = Depends(get_db)):
    content = file.file.read(2 * 1024 * 1024 + 1)
    if len(content) > 2 * 1024 * 1024:
        raise HTTPException(413, "Размер фотографии не должен превышать 2 МБ")

    try:
        with Image.open(BytesIO(content)) as image:
            if image.format not in ("JPEG", "PNG"):
                raise HTTPException(422, "Разрешены только JPEG и PNG")
            if image.width * image.height > 10_000_000:
                raise HTTPException(422, "Слишком большое разрешение")

            photo = ImageOps.exif_transpose(image)
            photo.thumbnail((1024, 1024))
            output = BytesIO()
            photo.convert("RGB").save(output, format="JPEG", quality=85)
            student.profile_photo = output.getvalue()

    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        raise HTTPException(422, "Некорректный файл изображения")

    db.commit()
    return {"message": "Фотография успешно сохранена"}


@students_router.get("/{student_id}/photo")
def get_student_photo(student_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    student = db.query(Student).filter(Student.id == student_id).first()

    if current_user.role != UserRole.ADMIN:
        if not student or student.user_id != current_user.id:
            raise HTTPException(403, "Нет доступа")

    if not student:
        raise HTTPException(404, "Студент не найден")
    if not student.profile_photo:
        raise HTTPException(404, "Фотография не найдена")

    return Response(content=student.profile_photo, media_type="image/jpeg",
                    headers={"Cache-Control": "private, no-store"})
