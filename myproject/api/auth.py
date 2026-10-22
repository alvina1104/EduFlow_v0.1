from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from jose import JWTError
from sqlalchemy.orm import Session
from myproject.core.dependencies import get_current_user
from myproject.core.security import create_access_token, create_refresh_token, decode_token, hash_refresh_token, verify_password
from myproject.database.db import get_db
from myproject.database.models import RefreshToken, User
from myproject.database.schemas import UserLoginSchema, RefreshTokenRequestSchema, TokenResponseSchema

auth_router = APIRouter(prefix="/auth", tags=["Auth"])


@auth_router.post("/login", response_model=TokenResponseSchema)
def login(data: UserLoginSchema, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == data.username).first()

    if not user or not verify_password(data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Неверный логин или пароль")

    if not user.is_active:
        raise HTTPException(status_code=403, detail="Аккаунт деактивирован")

    access_token = create_access_token(user.id)
    refresh_token = create_refresh_token(user.id)
    payload = decode_token(refresh_token)
    token_hash = hash_refresh_token(refresh_token)
    expires_at = datetime.fromtimestamp(payload["exp"], tz=timezone.utc).replace(tzinfo=None)

    token_db = RefreshToken(
        user_id=user.id,
        token_hash=token_hash,
        expires_at=expires_at
    )
    db.add(token_db)
    db.commit()

    return {"access_token": access_token, "refresh_token": refresh_token, "token_type": "bearer"}


@auth_router.post("/refresh", response_model=TokenResponseSchema)
def refresh(data: RefreshTokenRequestSchema, db: Session = Depends(get_db)):
    refresh_token = data.refresh_token

    try:
        payload = decode_token(refresh_token)

        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Недействительный refresh-токен")

        user_id = int(payload["sub"])

    except (JWTError, ValueError, KeyError, TypeError):
        raise HTTPException(status_code=401, detail="Недействительный или просроченный refresh-токен")

    token_hash = hash_refresh_token(refresh_token)

    token_db = db.query(RefreshToken).filter(
        RefreshToken.user_id == user_id,
        RefreshToken.token_hash == token_hash,
        RefreshToken.revoked_at.is_(None)
    ).first()

    if not token_db or token_db.expires_at <= datetime.utcnow():
        raise HTTPException(status_code=401, detail="Refresh-токен недействителен или истёк")

    user = db.query(User).filter(User.id == user_id, User.is_active.is_(True)).first()

    if not user:
        raise HTTPException(status_code=401, detail="Пользователь не найден или аккаунт деактивирован")

    token_db.revoked_at = datetime.utcnow()

    access_token = create_access_token(user.id)
    refresh_token = create_refresh_token(user.id)
    payload = decode_token(refresh_token)
    token_hash = hash_refresh_token(refresh_token)
    expires_at = datetime.fromtimestamp(payload["exp"], tz=timezone.utc).replace(tzinfo=None)

    new_token_db = RefreshToken(
        user_id=user.id,
        token_hash=token_hash,
        expires_at=expires_at
    )
    db.add(new_token_db)
    db.commit()

    return {"access_token": access_token, "refresh_token": refresh_token, "token_type": "bearer"}


@auth_router.post("/logout")
def logout(data: RefreshTokenRequestSchema, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    refresh_token = data.refresh_token
    token_hash = hash_refresh_token(refresh_token)

    token_db = db.query(RefreshToken).filter(
        RefreshToken.user_id == current_user.id,
        RefreshToken.token_hash == token_hash,
        RefreshToken.revoked_at.is_(None)
    ).first()

    if not token_db:
        raise HTTPException(status_code=404, detail="Активный refresh-токен не найден")

    token_db.revoked_at = datetime.utcnow()
    db.commit()

    return {"message": "Вы успешно вышли из системы"}
