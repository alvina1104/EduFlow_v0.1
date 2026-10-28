from datetime import date, datetime, time
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator
from .models import (UserRole, PaymentStatus, ContractStatus,
                     StudentGroupHistoryKind, PersonalInfoStatus)
from pydantic import UUID4


class BaseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class UserCreateSchema(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=8, max_length=128)
    role: UserRole = UserRole.STUDENT


class UserLoginSchema(BaseModel):
    username: str
    password: str


class UserUpdateSchema(BaseModel):
    username: str | None = Field(default=None, min_length=3, max_length=50)
    password: str | None = Field(default=None, min_length=8, max_length=128)
    is_active: bool | None = None


class UserResponseSchema(BaseSchema):
    id: int
    username: str
    role: UserRole
    is_active: bool


class UserMeResponseSchema(UserResponseSchema):
    student_id: int | None = None


class TokenResponseSchema(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshTokenRequestSchema(BaseModel):
    refresh_token: str


class PersonalInfoCreateSchema(BaseModel):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    middle_name: str | None = Field(default=None, max_length=100)
    phone: str = Field(min_length=5, max_length=20)
    birth_date: date
    birth_place: str | None = Field(default=None, max_length=150)
    address: str | None = Field(default=None, max_length=255)
    registration_address: str | None = Field(default=None, max_length=255)


class PersonalInfoResponseSchema(BaseSchema):
    id: int
    student_id: int
    first_name: str
    last_name: str
    middle_name: str | None
    phone: str
    birth_date: date
    birth_place: str | None
    address: str | None
    registration_address: str | None
    status: PersonalInfoStatus
    review_comment: str | None
    reviewed_by_admin_id: int | None
    reviewed_at: datetime | None


class PersonalInfoReviewSchema(BaseModel):
    status: Literal[PersonalInfoStatus.APPROVED, PersonalInfoStatus.REVISION]
    comment: str | None = Field(default=None, max_length=500)


class StudentCreateSchema(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=8, max_length=128)
    student_number: str = Field(min_length=1, max_length=30)
    group_id: int | None = None
    personal_info: PersonalInfoCreateSchema | None = None


class StudentUpdateSchema(BaseModel):
    group_id: int | None = None
    student_number: str | None = Field(default=None, min_length=1, max_length=30)


class StudentGroupHistoryResponseSchema(BaseSchema):
    id: int
    group_id: int
    kind: StudentGroupHistoryKind
    from_date: date | None
    to_date: date | None
    reason: str | None


class StudentResponseSchema(BaseSchema):
    id: int
    user_id: int
    group_id: int | None
    student_number: str
    personal_info: PersonalInfoResponseSchema | None
    group_history: list[StudentGroupHistoryResponseSchema]


class GroupCreateSchema(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    course_name: str = Field(min_length=1, max_length=150)
    start_date: date
    end_date: date | None = None


class ScheduleResponseSchema(BaseSchema):
    id: int
    group_id: int
    title: str
    weekday: str
    start_time: time
    end_time: time


class GroupResponseSchema(BaseSchema):
    id: int
    name: str
    course_name: str
    start_date: date
    end_date: date | None
    schedules: list[ScheduleResponseSchema]


class ContractCreateSchema(BaseModel):
    student_id: int = Field(gt=0)
    total_amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    monthly_payment: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    duration_months: int = Field(gt=0)
    start_date: date
    payment_day: int | None = Field(default=None, ge=1, le=28)



class AcademicLeaveCreateSchema(BaseModel):
    start_date: date
    end_date: date
    reason: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def validate_dates(self):
        if self.end_date < self.start_date:
            raise ValueError("Дата окончания раньше даты начала")
        return self


class AcademicLeaveResponseSchema(BaseSchema):
    id: int
    contract_id: int
    start_date: date
    end_date: date
    reason: str | None
    created_by_admin_id: int
    created_at: datetime
    cancelled_at: datetime | None



class ContractResponseSchema(BaseSchema):
    id: int
    student_id: int
    total_amount: Decimal
    monthly_payment: Decimal
    duration_months: int
    start_date: date
    status: ContractStatus
    created_at: datetime
    payment_day: int | None
    academic_leaves: list[AcademicLeaveResponseSchema]




class PaymentCreateSchema(BaseModel):
    request_id: UUID4
    contract_id: int = Field(gt=0)
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    payment_method: str | None = Field(default=None, max_length=50)
    payment_month: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")



class PaymentStatusUpdateSchema(BaseModel):
    status: PaymentStatus


class PaymentResponseSchema(BaseSchema):
    id: int
    contract_id: int
    request_id: str | None
    created_by_user_id: int | None
    amount: Decimal
    status: PaymentStatus
    payment_method: str | None
    created_at: datetime
    paid_at: datetime | None
    confirmed_by_admin_id: int | None
    payment_month: str


class ScheduleCreateSchema(BaseModel):
    group_id: int = Field(gt=0)
    title: str = Field(min_length=1, max_length=150)
    weekday: Literal["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    start_time: time
    end_time: time

    @model_validator(mode="after")
    def check_time(self):
        if self.start_time >= self.end_time:
            raise ValueError("Время начала должно быть раньше времени окончания")
        return self
