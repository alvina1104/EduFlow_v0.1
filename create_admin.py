import os
from getpass import getpass
from pathlib import Path
from dotenv import dotenv_values
from sqlalchemy.engine import make_url

config = dotenv_values(Path(__file__).parent / "myproject" / ".env")
database_url = config.get("DATABASE_URL")
secret_key = config.get("SECRET_KEY")

if not database_url or not secret_key:
    raise SystemExit("Ошибка: DATABASE_URL или SECRET_KEY не найдены")

url = make_url(database_url)

if (url.get_backend_name() != "postgresql"
        or url.host not in ("localhost", "127.0.0.1")
        or url.database != "eduflow"):
    raise SystemExit("Ошибка: разрешена только локальная база eduflow")

os.environ["DATABASE_URL"] = database_url
os.environ["SECRET_KEY"] = secret_key

from myproject.database.db import SessionLocal
from myproject.database.models import User, UserRole
from myproject.core.security import hash_password

username = input("Введите логин администратора [admin]: ").strip() or "admin"

if not 3 <= len(username) <= 50:
    raise SystemExit("Ошибка: логин должен содержать от 3 до 50 символов")

with SessionLocal() as db:
    admin = db.query(User).filter(User.username == username).first()

    if admin and admin.role != UserRole.ADMIN:
        raise SystemExit("Ошибка: этот логин уже принадлежит другому пользователю")

    if admin:
        print("Администратор с таким логином уже существует")
        answer = input("Изменить пароль администратора? (да/нет): ").strip().lower()

        if answer != "да":
            raise SystemExit("Изменения отменены")

        if not admin.is_active:
            raise SystemExit("Ошибка: аккаунт администратора отключён")

    password = getpass("Введите пароль администратора: ")
    confirm_password = getpass("Повторите пароль: ")

    if len(password) < 6:
        raise SystemExit("Пароль должен содержать минимум 6 символов")

    if password != confirm_password:
        raise SystemExit("Пароли не совпадают")

    if admin:
        admin.hashed_password = hash_password(password)
    else:
        admin = User(
            username=username,
            hashed_password=hash_password(password),
            role=UserRole.ADMIN,
            is_active=True
        )
        db.add(admin)

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise

    print("\nАдминистратор успешно создан или обновлён!")
    print("Логин:", username)
    print("\nСохраните пароль в безопасном месте.")
