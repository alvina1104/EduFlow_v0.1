
from datetime import date, datetime, time
from decimal import Decimal
from enum import Enum
from sqlalchemy import (Boolean, Date, DateTime, Enum as SQLEnum, ForeignKey,
                        Integer, Numeric, String, Time, Index, text,
                        CheckConstraint, func, LargeBinary)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .db import Base


class UserRole(str, Enum):
    ADMIN = "admin"
    STUDENT = "student"


class PaymentStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"


class ContractStatus(str, Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class StudentGroupHistoryKind(str, Enum):
    ENROLLMENT = "enrollment"
    TRANSFER = "transfer"


class PersonalInfoStatus(str, Enum):
    NOT_SUBMITTED = "not_submitted"
    PENDING = "pending"
    APPROVED = "approved"
    REVISION = "revision"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(SQLEnum(UserRole), default=UserRole.STUDENT, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[date | None] = mapped_column(Date, default=date.today, nullable=True)

    student: Mapped["Student | None"] = relationship(back_populates="user", uselist=False)
    refresh_tokens: Mapped[list["RefreshToken"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    confirmed_payments: Mapped[list["Payment"]] = relationship(
        back_populates="confirmed_by_admin", foreign_keys="Payment.confirmed_by_admin_id"
    )


class Group(Base):
    __tablename__ = "groups"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    course_name: Mapped[str] = mapped_column(String(150), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    students: Mapped[list["Student"]] = relationship(back_populates="group")
    schedules: Mapped[list["Schedule"]] = relationship(back_populates="group")
    history_entries: Mapped[list["StudentGroupHistory"]] = relationship(back_populates="group")


class Student(Base):
    __tablename__ = "students"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True, nullable=False)
    group_id: Mapped[int | None] = mapped_column(ForeignKey("groups.id"), nullable=True)
    student_number: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    profile_photo: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)

    user: Mapped["User"] = relationship(back_populates="student")
    group: Mapped["Group | None"] = relationship(back_populates="students")
    personal_info: Mapped["PersonalInfo | None"] = relationship(
        back_populates="student", uselist=False, cascade="all, delete-orphan"
    )
    contracts: Mapped[list["Contract"]] = relationship(back_populates="student", cascade="all, delete-orphan")
    group_history: Mapped[list["StudentGroupHistory"]] = relationship(
        back_populates="student", cascade="all, delete-orphan"
    )


class StudentGroupHistory(Base):
    __tablename__ = "student_group_history"

    __table_args__ = (
        Index("uq_student_group_history_open", "student_id", unique=True,
              postgresql_where=text("to_date IS NULL"),
              sqlite_where=text("to_date IS NULL")),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"), nullable=False)
    group_id: Mapped[int] = mapped_column(ForeignKey("groups.id"), nullable=False)
    kind: Mapped[StudentGroupHistoryKind] = mapped_column(SQLEnum(StudentGroupHistoryKind), nullable=False)
    from_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    to_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)

    student: Mapped["Student"] = relationship(back_populates="group_history")
    group: Mapped["Group"] = relationship(back_populates="history_entries")


class PersonalInfo(Base):
    __tablename__ = "personal_info"

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"), unique=True, nullable=False)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    middle_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    phone: Mapped[str] = mapped_column(String(20), nullable=False)
    birth_date: Mapped[date] = mapped_column(Date, nullable=False)
    birth_place: Mapped[str | None] = mapped_column(String(150), nullable=True)
    address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    registration_address: Mapped[str | None] = mapped_column(String(255), nullable=True)

    status: Mapped[PersonalInfoStatus] = mapped_column(
        SQLEnum(PersonalInfoStatus), default=PersonalInfoStatus.PENDING,
        server_default="PENDING", nullable=False
    )
    review_comment: Mapped[str | None] = mapped_column(String(500), nullable=True)
    reviewed_by_admin_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    student: Mapped["Student"] = relationship(back_populates="personal_info")


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    user: Mapped["User"] = relationship(back_populates="refresh_tokens")


class Schedule(Base):
    __tablename__ = "schedules"

    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("groups.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(150), nullable=False)
    weekday: Mapped[str] = mapped_column(String(20), nullable=False)
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)

    group: Mapped["Group"] = relationship(back_populates="schedules")


class Contract(Base):
    __tablename__ = "contracts"

    __table_args__ = (
        CheckConstraint("payment_day BETWEEN 1 AND 28", name="ck_contracts_payment_day"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"), nullable=False)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    monthly_payment: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    duration_months: Mapped[int] = mapped_column(Integer, nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[ContractStatus] = mapped_column(SQLEnum(ContractStatus), default=ContractStatus.ACTIVE, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    payment_day: Mapped[int | None] = mapped_column(Integer, nullable=True)

    student: Mapped["Student"] = relationship(back_populates="contracts")
    payments: Mapped[list["Payment"]] = relationship(back_populates="contract", cascade="all, delete-orphan")
    academic_leaves: Mapped[list["AcademicLeave"]] = relationship(back_populates="contract")


class AcademicLeave(Base):
    __tablename__ = "academic_leaves"

    __table_args__ = (
        CheckConstraint("end_date >= start_date", name="ck_academic_leaves_dates"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    contract_id: Mapped[int] = mapped_column(ForeignKey("contracts.id"), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_by_admin_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    contract: Mapped["Contract"] = relationship(back_populates="academic_leaves")


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    contract_id: Mapped[int] = mapped_column(ForeignKey("contracts.id"), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    status: Mapped[PaymentStatus] = mapped_column(SQLEnum(PaymentStatus), default=PaymentStatus.PENDING, nullable=False)
    payment_method: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    confirmed_by_admin_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    payment_month: Mapped[str] = mapped_column(String(7), nullable=False)
    request_id: Mapped[str | None] = mapped_column(String(36), unique=True, nullable=True)
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    contract: Mapped["Contract"] = relationship(back_populates="payments")
    confirmed_by_admin: Mapped["User | None"] = relationship(
        back_populates="confirmed_payments", foreign_keys=[confirmed_by_admin_id]
    )
