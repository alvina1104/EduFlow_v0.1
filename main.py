import os
from fastapi import FastAPI
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from sqlalchemy import text
import uvicorn
from myproject.api import (auth, contracts, groups, payments, personal_info, students,
                           users, schedules, study, finik)
from myproject.database.db import engine


production = os.getenv("ENVIRONMENT", "development").lower() == "production"
edu_app = FastAPI(
    title="EduFlow for Motion",
    docs_url=None if production else "/docs",
    redoc_url=None if production else "/redoc",
    openapi_url=None if production else "/openapi.json",
)
edu_app.include_router(auth.auth_router)
edu_app.include_router(students.students_router)
edu_app.include_router(personal_info.personal_info_router)
edu_app.include_router(groups.groups_router)
edu_app.include_router(contracts.contracts_router)
edu_app.include_router(payments.payments_router)
edu_app.include_router(users.user_router)
edu_app.include_router(schedules.schedules_router)
edu_app.include_router(study.study_router)
edu_app.include_router(finik.finik_router)

# Self-contained frontend; existing API routes remain unchanged.
FRONTEND_DIR = Path(__file__).resolve().parent / "myproject" / "frontend"
edu_app.mount("/app", StaticFiles(directory=FRONTEND_DIR), name="frontend")


@edu_app.get("/", include_in_schema=False)
def index():
    return FileResponse(FRONTEND_DIR / "index.html")



@edu_app.get("/health", tags=["Health"], summary="Проверка состояния приложения и базы данных")
def health():
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception:
        return JSONResponse(status_code=503, content={"status": "unavailable", "database": "down"})
    return {"status": "ok", "database": "up"}


if __name__ == "__main__":
    uvicorn.run(edu_app, host="127.0.0.1", port=8000)
