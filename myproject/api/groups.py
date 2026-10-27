from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from myproject.database.db import get_db
from myproject.database.models import Group, User, Student, StudentGroupHistory
from myproject.database.schemas import GroupCreateSchema, GroupResponseSchema
from myproject.core.dependencies import get_current_admin, get_current_student

groups_router = APIRouter(prefix="/groups", tags=["Groups"])


@groups_router.post("/", response_model=GroupResponseSchema, status_code=201)
def create_group(data: GroupCreateSchema, db: Session = Depends(get_db), admin: User = Depends(get_current_admin)):
    if data.end_date and data.end_date < data.start_date:
        raise HTTPException(400, "Дата окончания не может быть раньше даты начала")
    group = Group(**data.model_dump())
    db.add(group)
    db.commit()
    db.refresh(group)
    return group


@groups_router.get("/", response_model=list[GroupResponseSchema])
def get_groups(db: Session = Depends(get_db), admin: User = Depends(get_current_admin)):
    return db.query(Group).all()


@groups_router.get("/my", response_model=GroupResponseSchema)
def get_my_group(student: Student = Depends(get_current_student), db: Session = Depends(get_db)):
    if not student.group_id:
        raise HTTPException(404, "Студент не привязан к группе")
    group = db.query(Group).filter(Group.id == student.group_id).first()
    if not group:
        raise HTTPException(404, "Группа не найдена")
    return group


@groups_router.get("/{group_id}", response_model=GroupResponseSchema)
def get_group(group_id: int, db: Session = Depends(get_db), admin: User = Depends(get_current_admin)):
    group = db.query(Group).filter(Group.id == group_id).first()
    if not group:
        raise HTTPException(404, "Группа не найдена")
    return group


@groups_router.put("/{group_id}", response_model=GroupResponseSchema)
def update_group(group_id: int, data: GroupCreateSchema, db: Session = Depends(get_db), admin: User = Depends(get_current_admin)):
    group = db.query(Group).filter(Group.id == group_id).first()
    if not group:
        raise HTTPException(404, "Группа не найдена")
    if data.end_date and data.end_date < data.start_date:
        raise HTTPException(400, "Дата окончания не может быть раньше даты начала")

    for key, value in data.model_dump().items():
        setattr(group, key, value)
    db.commit()
    db.refresh(group)
    return group


@groups_router.delete("/{group_id}", status_code=204)
def delete_group(group_id: int, db: Session = Depends(get_db), admin: User = Depends(get_current_admin)):
    group = db.query(Group).filter(Group.id == group_id).first()
    if not group:
        raise HTTPException(404, "Группа не найдена")
    if db.query(Student).filter(Student.group_id == group_id).first():
        raise HTTPException(409, "Нельзя удалить группу, в которой есть студенты")
    if db.query(StudentGroupHistory.id).filter(StudentGroupHistory.group_id == group_id).first():
        raise HTTPException(409, "Нельзя удалить группу: сохранена история переводов")
    try:
        db.delete(group)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Нельзя удалить группу: есть связанные данные")