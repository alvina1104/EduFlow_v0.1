import os
from urllib.parse import quote, urlsplit
import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import ValidationError
from myproject.core.dependencies import get_current_student
from myproject.database.models import Student
from myproject.services.study import PortalStudyData, StudyProgressResponseSchema, calculate_study_progress

study_router = APIRouter(prefix="/study", tags=["Study"])


@study_router.get("/me", response_model=StudyProgressResponseSchema)
def get_my_study_progress(student: Student = Depends(get_current_student)):
    template = os.getenv("PORTAL_STUDY_URL_TEMPLATE", "")
    token = os.getenv("PORTAL_STUDY_API_TOKEN", "")

    if not template or "{student_number}" not in template or not token:
        raise HTTPException(503, "Интеграция с учебным порталом пока не настроена")

    url = template.replace("{student_number}", quote(student.student_number, safe=""))
    parsed = urlsplit(url)

    if parsed.scheme != "https" and not (parsed.scheme == "http" and parsed.hostname in ("localhost", "127.0.0.1")):
        raise HTTPException(503, "Укажите безопасный адрес API учебного портала")

    try:
        response = httpx.get(
            url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
            follow_redirects=False
        )
    except httpx.RequestError:
        raise HTTPException(502, "Учебный портал временно недоступен")

    if response.status_code == 404:
        raise HTTPException(404, "Учебные данные студента пока не найдены")
    if response.status_code != 200:
        raise HTTPException(502, "Не удалось получить данные учебного портала")

    try:
        portal_data = PortalStudyData.model_validate(response.json())
    except (ValueError, ValidationError):
        raise HTTPException(502, "Формат ответа учебного портала не поддерживается")

    return calculate_study_progress(student.id, portal_data)
