from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from myproject.database.db import get_db
from myproject.database.models import Notification, User
from myproject.database.schemas import NotificationResponseSchema
from myproject.core.dependencies import get_current_user

notifications_router = APIRouter(prefix="/notifications", tags=["Notifications"])


@notifications_router.get("/", response_model=list[NotificationResponseSchema])
def get_notifications(
    unread_only: bool = False, limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    query = db.query(Notification).filter(Notification.user_id == user.id)
    if unread_only:
        query = query.filter(Notification.is_read.is_(False))
    return query.order_by(Notification.created_at.desc(), Notification.id.desc()).offset(offset).limit(limit).all()


@notifications_router.get("/unread-count")
def get_unread_count(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    return {"count": db.query(Notification).filter(
        Notification.user_id == user.id, Notification.is_read.is_(False)
    ).count()}


@notifications_router.patch("/read-all")
def read_all_notifications(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    count = db.query(Notification).filter(
        Notification.user_id == user.id, Notification.is_read.is_(False)
    ).update({Notification.is_read: True}, synchronize_session=False)
    db.commit()
    return {"updated": count}


@notifications_router.patch("/{notification_id}/read", response_model=NotificationResponseSchema)
def read_notification(
    notification_id: int, db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    notification = db.query(Notification).filter(
        Notification.id == notification_id, Notification.user_id == user.id
    ).first()
    if not notification:
        raise HTTPException(404, "Уведомление не найдено")
    if not notification.is_read:
        notification.is_read = True
        db.commit()
        db.refresh(notification)
    return notification
