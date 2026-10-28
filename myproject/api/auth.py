from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from jose import JWTError
from sqlalchemy.orm import Session
from myproject.core.dependencies import get_current_user
from myproject.core.security import create_access_token, create_refresh_token, decode_token, hash_refresh_token, verify_password
from myproject.database.db import get_db
from myproject.database.models import RefreshToken, User, Student
from myproject.database.schemas import UserLoginSchema, RefreshTokenRequestSchema, TokenResponseSchema, UserMeResponseSchema

auth_router = APIRouter(prefix="/auth", tags=["Auth"])


@auth_router.post("/login", response_model=TokenResponseSchema)
def login(data: UserLoginSchema, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == data.username).first()
    if not user or not verify_password(data.password, user.hashed_password):
        raise HTTPException(401, "Неверный логин или пароль")
    if not user.is_active:
        raise HTTPException(403, "Аккаунт деактивирован")

    access_token = create_access_token(user.id)
    refresh_token = create_refresh_token(user.id)
    payload = decode_token(refresh_token)
    token_hash = hash_refresh_token(refresh_token)
    expires_at = datetime.fromtimestamp(payload["exp"], tz=timezone.utc).replace(tzinfo=None)

    token_db = RefreshToken(user_id=user.id, token_hash=token_hash, expires_at=expires_at)
    db.add(token_db)
    db.commit()
    return {"access_token": access_token, "refresh_token": refresh_token, "token_type": "bearer"}


@auth_router.post("/refresh", response_model=TokenResponseSchema)
def refresh(data: RefreshTokenRequestSchema, db: Session = Depends(get_db)):
    try:
        payload = decode_token(data.refresh_token)
        if payload.get("type") != "refresh":
            raise HTTPException(401, "Недействительный refresh-токен")
        user_id = int(payload["sub"])
    except (JWTError, ValueError, KeyError, TypeError):
        raise HTTPException(401, "Недействительный или просроченный refresh-токен")

    token_hash = hash_refresh_token(data.refresh_token)
    token_db = db.query(RefreshToken).filter(
        RefreshToken.user_id == user_id,
        RefreshToken.token_hash == token_hash,
        RefreshToken.revoked_at.is_(None)
    ).first()

    if not token_db or token_db.expires_at <= datetime.utcnow():
        raise HTTPException(401, "Refresh-токен недействителен или истёк")

    user = db.query(User).filter(User.id == user_id, User.is_active.is_(True)).first()
    if not user:
        raise HTTPException(401, "Пользователь не найден или аккаунт деактивирован")

    token_db.revoked_at = datetime.utcnow()

    access_token = create_access_token(user.id)
    refresh_token = create_refresh_token(user.id)
    payload = decode_token(refresh_token)
    token_hash = hash_refresh_token(refresh_token)
    expires_at = datetime.fromtimestamp(payload["exp"], tz=timezone.utc).replace(tzinfo=None)

    db.add(RefreshToken(user_id=user.id, token_hash=token_hash, expires_at=expires_at))
    db.commit()
    return {"access_token": access_token, "refresh_token": refresh_token, "token_type": "bearer"}


@auth_router.post("/logout")
def logout(data: RefreshTokenRequestSchema, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    token_hash = hash_refresh_token(data.refresh_token)
    token_db = db.query(RefreshToken).filter(
        RefreshToken.user_id == current_user.id,
        RefreshToken.token_hash == token_hash,
        RefreshToken.revoked_at.is_(None)
    ).first()

    if not token_db:
        raise HTTPException(404, "Активный refresh-токен не найден")

    token_db.revoked_at = datetime.utcnow()
    db.commit()
    return {"message": "Вы успешно вышли из системы"}


@auth_router.get("/me", response_model=UserMeResponseSchema)
def get_me(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    student_id = db.query(Student.id).filter(Student.user_id == current_user.id).scalar()
    return {
        "id": current_user.id,
        "username": current_user.username,
        "role": current_user.role,
        "is_active": current_user.is_active,
        "student_id": student_id
    }
