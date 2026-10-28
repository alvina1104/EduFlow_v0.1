from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from myproject.database.models import User, RefreshToken
from myproject.database.db import get_db
from myproject.database.schemas import UserCreateSchema, UserUpdateSchema, UserResponseSchema
from myproject.core.dependencies import get_current_admin
from myproject.core.security import hash_password

user_router = APIRouter(prefix="/users", tags=["Users"])


@user_router.post("/", response_model=UserResponseSchema, status_code=status.HTTP_201_CREATED)
def create_user(user: UserCreateSchema, db: Session = Depends(get_db), current_admin: User = Depends(get_current_admin)):
    if db.query(User).filter(User.username == user.username).first():
        raise HTTPException(400, "Такой пользователь уже существует")

    user_data = User(username=user.username, hashed_password=hash_password(user.password),
                     role=user.role, is_active=True)
    db.add(user_data)
    try:
        db.commit()
        db.refresh(user_data)
    except IntegrityError:
        db.rollback()
        raise HTTPException(400, "Не удалось создать пользователя")
    return user_data


@user_router.get("/", response_model=list[UserResponseSchema])
def get_users(db: Session = Depends(get_db), current_admin: User = Depends(get_current_admin)):
    return db.query(User).all()


@user_router.get("/{user_id}", response_model=UserResponseSchema)
def get_user(user_id: int, db: Session = Depends(get_db), current_admin: User = Depends(get_current_admin)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(404, "Пользователь не найден")
    return user


@user_router.put("/{user_id}", response_model=UserResponseSchema)
def update_user(user_id: int, user: UserUpdateSchema, db: Session = Depends(get_db), current_admin: User = Depends(get_current_admin)):
    user_db = db.query(User).filter(User.id == user_id).with_for_update().first()
    if not user_db:
        raise HTTPException(404, "Пользователь не найден")

    if user.username is not None:
        if db.query(User).filter(User.username == user.username, User.id != user_id).first():
            raise HTTPException(400, "Такой логин уже занят")
        user_db.username = user.username

    revoke_tokens = False

    if user.password is not None:
        user_db.hashed_password = hash_password(user.password)
        revoke_tokens = True

    if user.is_active is not None:
        user_db.is_active = user.is_active
        if not user.is_active:
            revoke_tokens = True

    if revoke_tokens:
        db.query(RefreshToken).filter(
            RefreshToken.user_id == user_db.id,
            RefreshToken.revoked_at.is_(None)
        ).update({RefreshToken.revoked_at: datetime.utcnow()}, synchronize_session=False)

    try:
        db.commit()
        db.refresh(user_db)
    except IntegrityError:
        db.rollback()
        raise HTTPException(400, "Не удалось обновить пользователя")

    return user_db


@user_router.delete("/{user_id}")
def delete_user(user_id: int, db: Session = Depends(get_db), current_admin: User = Depends(get_current_admin)):
    user_db = db.query(User).filter(User.id == user_id).first()
    if not user_db:
        raise HTTPException(404, "Пользователь не найден")
    if user_db.id == current_admin.id:
        raise HTTPException(400, "Нельзя удалить свой аккаунт")

    db.delete(user_db)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Нельзя удалить пользователя: с ним связаны другие данные")
    return {"message": "Пользователь успешно удалён"}
