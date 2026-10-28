from decimal import Decimal, ROUND_HALF_UP
from pydantic import BaseModel, Field, model_validator


class PortalStudyData(BaseModel):
    held_lessons: int = Field(ge=0)
    attended_lessons: int = Field(ge=0)
    total_topics: int | None = Field(default=None, ge=0)
    completed_topics: int | None = Field(default=None, ge=0)
    grades: list[int] = Field(default_factory=list)

    @model_validator(mode="after")
    def check_values(self):
        if self.attended_lessons > self.held_lessons:
            raise ValueError("Посещений не может быть больше проведённых занятий")
        if (self.total_topics is None) != (self.completed_topics is None):
            raise ValueError("Для прогресса нужны оба значения")
        if self.total_topics is not None and self.completed_topics > self.total_topics:
            raise ValueError("Завершённых тем не может быть больше общего количества")
        if any(grade < 1 or grade > 5 for grade in self.grades):
            raise ValueError("Оценки должны быть от 1 до 5")
        return self


class StudyProgressResponseSchema(BaseModel):
    student_id: int
    held_lessons: int
    attended_lessons: int
    attendance_percent: Decimal | None
    total_topics: int | None
    completed_topics: int | None
    progress_percent: Decimal | None
    grades: list[int]
    average_grade: Decimal | None


def percent(part: int, total: int) -> Decimal | None:
    if total == 0:
        return None
    return (Decimal(part) * Decimal(100) / Decimal(total)).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )


def calculate_study_progress(student_id: int, data: PortalStudyData) -> StudyProgressResponseSchema:
    average = None

    if data.grades:
        average = (Decimal(sum(data.grades)) / Decimal(len(data.grades))).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

    return StudyProgressResponseSchema(
        student_id=student_id,
        held_lessons=data.held_lessons,
        attended_lessons=data.attended_lessons,
        attendance_percent=percent(data.attended_lessons, data.held_lessons),
        total_topics=data.total_topics,
        completed_topics=data.completed_topics,
        progress_percent=percent(data.completed_topics, data.total_topics) if data.total_topics is not None else None,
        grades=data.grades,
        average_grade=average
    )
