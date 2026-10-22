from datetime import date, datetime, time
from decimal import Decimal
from pydantic import BaseModel, ConfigDict, Field
from .models import UserRole, PaymentStatus, ContractStatus


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
    username: str | None = None
    password: str | None = None
    is_active: bool | None = None


class UserResponseSchema(BaseSchema):
    id: int
    username: str
    role: UserRole
    is_active: bool


class TokenResponseSchema(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshTokenRequestSchema(BaseModel):
    refresh_token: str


class PersonalInfoCreateSchema(BaseModel):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    phone: str = Field(min_length=5, max_length=20)
    birth_date: date
    address: str | None = Field(default=None, max_length=255)


class PersonalInfoResponseSchema(BaseSchema):
    id: int
    student_id: int
    first_name: str
    last_name: str
    phone: str
    birth_date: date
    address: str | None


class StudentCreateSchema(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=8, max_length=128)
    student_number: str = Field(min_length=1, max_length=30)
    group_id: int | None = None
    personal_info: PersonalInfoCreateSchema


class StudentResponseSchema(BaseSchema):
    id: int
    user_id: int
    group_id: int | None
    student_number: str
    personal_info: PersonalInfoResponseSchema | None


class GroupCreateSchema(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    course_name: str = Field(min_length=1, max_length=150)
    start_date: date
    end_date: date | None = None


class GroupResponseSchema(BaseSchema):
    id: int
    name: str
    course_name: str
    start_date: date
    end_date: date | None


class ContractCreateSchema(BaseModel):
    student_id: int
    total_amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    monthly_payment: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    duration_months: int = Field(gt=0)
    start_date: date


class ContractResponseSchema(BaseSchema):
    id: int
    student_id: int
    total_amount: Decimal
    monthly_payment: Decimal
    duration_months: int
    start_date: date
    status: ContractStatus
    created_at: datetime


class PaymentCreateSchema(BaseModel):
    contract_id: int
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    payment_method: str | None = Field(default=None, max_length=50)
    payment_month: str


class PaymentStatusUpdateSchema(BaseModel):
    status: PaymentStatus


class PaymentResponseSchema(BaseSchema):
    id: int
    contract_id: int
    amount: Decimal
    status: PaymentStatus
    payment_method: str | None
    created_at: datetime
    paid_at: datetime | None
    confirmed_by_admin_id: int | None
    payment_month: str


class ScheduleCreateSchema(BaseModel):
    group_id: int
    title: str = Field(min_length=1, max_length=150)
    weekday: str = Field(min_length=1, max_length=20)
    start_time: time
    end_time: time


class ScheduleResponseSchema(BaseSchema):
    id: int
    group_id: int
    title: str
    weekday: str
    start_time: time
    end_time: time
