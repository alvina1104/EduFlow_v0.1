"""Безопасная локальная проверка причины отказа входа в EduFlow.

Запуск из корня репозитория:
    ./.venv/bin/python diagnose_local_login.py

Только SELECT: пароль не печатается, хеши не выводятся, данные не меняются.
Никогда не проверяет удалённый / production PostgreSQL.
"""
from getpass import getpass
from pathlib import Path

from dotenv import dotenv_values
from sqlalchemy import select
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError

from myproject.config import DATABASE_URL
from myproject.core.security import verify_password
from myproject.database.db import SessionLocal
from myproject.database.models import User


def _identity(value: str) -> tuple[str, int, str]:
    url = make_url(value)
    if url.get_backend_name() != "postgresql":
        raise SystemExit("Отказ: требуется локальная PostgreSQL база")
    if url.host not in ("localhost", "127.0.0.1", "::1"):
        raise SystemExit("Отказ: удалённые PostgreSQL базы не проверяем")
    return (url.host, url.port or 5432, url.database or "")


def main() -> None:
    active = _identity(DATABASE_URL)
    print("FastAPI (текущий DATABASE_URL):")
    print("  Host:", active[0], "Port:", active[1], "Database:", active[2])

    admin_env_path = Path(__file__).resolve().parent / "myproject" / ".env"
    if admin_env_path.is_file():
        admin_config = dotenv_values(admin_env_path)
        if admin_config.get("DATABASE_URL"):
            admin_db = _identity(admin_config["DATABASE_URL"])
            print("create_admin.py (myproject/.env):")
            print("  Host:", admin_db[0], "Port:", admin_db[1],
                  "Database:", admin_db[2])
            if admin_db != active:
                print("  ВНИМАНИЕ: create_admin.py и FastAPI используют разные БД!")
    else:
        print("myproject/.env отсутствует: create_admin.py без него не работает.")

    username = input("Логин для проверки [admin]: ").strip() or "admin"
    try:
        with SessionLocal() as db:
            user = db.execute(
                select(User).where(User.username == username)
            ).scalar_one_or_none()
            if user is None:
                print("Аккаунт с таким логином в текущей базе НЕ найден.")
                print("Проверьте DATABASE_URL и старую базу, пароль не сбрасывайте.")
                return
            print("Аккаунт найден. Роль:", user.role.value,
                  "Активен:", user.is_active)
            if not user.is_active:
                print("Причина: аккаунт деактивирован.")
                return
            password = getpass("Проверить старый пароль (ввод скрыт; Enter = пропустить): ")
            if not password:
                print("Проверка пароля пропущена.")
                return
            valid = verify_password(password, user.hashed_password)
            print("Старый пароль подходит:", "ДА" if valid else "НЕТ")
            if valid:
                print("Пароль в БД совпадает. Если браузер не пускает,")
                print("проверьте ответ POST /auth/login и какую БД использует")
                print("запущенный процесс Uvicorn (он мог быть запущен раньше).")
            else:
                print("Проверьте раскладку и правильность БД. Пароль не изменён.")
    except SQLAlchemyError as exc:
        print("Ошибка соединения или запроса к локальной БД:", type(exc).__name__)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
