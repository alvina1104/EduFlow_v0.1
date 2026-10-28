from decimal import Decimal

import pytest
from pydantic import ValidationError

from myproject.database.schemas import AcademicLeaveCreateSchema, PaymentCreateSchema
from myproject.services.study import PortalStudyData, calculate_study_progress


def test_payment_requires_uuid4_request_id():
    with pytest.raises(ValidationError):
        PaymentCreateSchema(contract_id=1, amount="10", payment_month="2026-10")
    payment = PaymentCreateSchema(request_id="c2f69915-64f5-45e8-a31b-2e78f5a2815b",
                                  contract_id=1, amount="10", payment_month="2026-10")
    assert str(payment.request_id) == "c2f69915-64f5-45e8-a31b-2e78f5a2815b"


def test_academic_leave_date_validation():
    with pytest.raises(ValidationError):
        AcademicLeaveCreateSchema(start_date="2026-10-02", end_date="2026-10-01")


def test_study_progress_calculation_without_portal():
    data = PortalStudyData(held_lessons=8, attended_lessons=6,
                           total_topics=5, completed_topics=3, grades=[4, 5])
    progress = calculate_study_progress(17, data)
    assert progress.student_id == 17
    assert progress.attendance_percent == Decimal("75.00")
    assert progress.progress_percent == Decimal("60.00")
    assert progress.average_grade == Decimal("4.50")


@pytest.mark.parametrize("payload", [
    {"held_lessons": 2, "attended_lessons": 3},
    {"held_lessons": 1, "attended_lessons": 0, "total_topics": 1},
    {"held_lessons": 1, "attended_lessons": 0, "grades": [6]},
])
def test_invalid_portal_data_is_rejected(payload):
    with pytest.raises(ValidationError):
        PortalStudyData(**payload)
