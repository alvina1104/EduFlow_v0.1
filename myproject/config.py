import os
from pathlib import Path

from dotenv import load_dotenv

PACKAGE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_DIR.parent

load_dotenv(PROJECT_ROOT / ".env")
load_dotenv(PACKAGE_DIR / ".env")

SECRET_KEY = os.getenv("SECRET_KEY")

if not SECRET_KEY:
    raise ValueError("SECRET_KEY is not set in .env")

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError("DATABASE_URL is not set in .env")

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
REFRESH_TOKEN_EXPIRE_DAYS = 7


FINIK_ENV = os.getenv("FINIK_ENV", "beta")
FINIK_API_KEY = os.getenv("FINIK_API_KEY", "")
FINIK_ACCOUNT_ID = os.getenv("FINIK_ACCOUNT_ID", "")
FINIK_PRIVATE_KEY_PATH = os.getenv("FINIK_PRIVATE_KEY_PATH", "")
FINIK_PUBLIC_KEY_PATH = os.getenv("FINIK_PUBLIC_KEY_PATH", "")
FINIK_WEBHOOK_URL = os.getenv("FINIK_WEBHOOK_URL", "")
FINIK_REDIRECT_URL = os.getenv("FINIK_REDIRECT_URL", "")
