from myproject.database.db import SessionLocal
from myproject.database.models import User, UserRole
from myproject.core.security import hash_password

db = SessionLocal()

try:
    admin = db.query(User).filter(User.username == "admin").first()

    if admin:
        print("Админ уже существует")
    else:
        admin = User(
            username="admin",
            hashed_password=hash_password("Admin12345"),
            role=UserRole.ADMIN,
            is_active=True
        )

        db.add(admin)
        db.commit()

        print("Админ успешно создан")
finally:
    db.close()