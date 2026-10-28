from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from myproject.database.db import get_db
from myproject.database.models import Schedule, Group, User
from myproject.database.schemas import ScheduleCreateSchema, ScheduleResponseSchema
from myproject.core.dependencies import get_current_admin

schedules_router = APIRouter(prefix="/schedules", tags=["Schedules"])


def check_schedule_conflict(db: Session, data: ScheduleCreateSchema, exclude_id: int | None = None):
    query = db.query(Schedule).filter(
        Schedule.group_id == data.group_id,
        Schedule.weekday == data.weekday,
        Schedule.start_time < data.end_time,
        Schedule.end_time > data.start_time
    )
    if exclude_id is not None:
        query = query.filter(Schedule.id != exclude_id)
    return query.first() is not None


@schedules_router.post("/", response_model=ScheduleResponseSchema, status_code=201)
def create_schedule(data: ScheduleCreateSchema, db: Session = Depends(get_db), admin: User = Depends(get_current_admin)):
    group = db.query(Group).filter(Group.id == data.group_id).with_for_update().first()
    if not group:
        raise HTTPException(404, "Группа не найдена")
    if check_schedule_conflict(db, data):
        raise HTTPException(409, "У группы уже есть занятие в это время")

    schedule = Schedule(**data.model_dump())
    db.add(schedule)
    try:
        db.commit()
        db.refresh(schedule)
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Не удалось создать расписание")
    return schedule


@schedules_router.put("/{schedule_id}", response_model=ScheduleResponseSchema)
def update_schedule(schedule_id: int, data: ScheduleCreateSchema, db: Session = Depends(get_db), admin: User = Depends(get_current_admin)):
    schedule = db.query(Schedule).filter(Schedule.id == schedule_id).with_for_update().first()
    if not schedule:
        raise HTTPException(404, "Расписание не найдено")

    group = db.query(Group).filter(Group.id == data.group_id).with_for_update().first()
    if not group:
        raise HTTPException(404, "Группа не найдена")
    if check_schedule_conflict(db, data, exclude_id=schedule_id):
        raise HTTPException(409, "У группы уже есть занятие в это время")

    for key, value in data.model_dump().items():
        setattr(schedule, key, value)

    try:
        db.commit()
        db.refresh(schedule)
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Не удалось обновить расписание")
    return schedule


@schedules_router.delete("/{schedule_id}", status_code=204)
def delete_schedule(schedule_id: int, db: Session = Depends(get_db), admin: User = Depends(get_current_admin)):
    schedule = db.query(Schedule).filter(Schedule.id == schedule_id).first()
    if not schedule:
        raise HTTPException(404, "Расписание не найдено")

    db.delete(schedule)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Не удалось удалить расписание")
