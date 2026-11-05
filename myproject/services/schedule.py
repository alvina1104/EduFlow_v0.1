from calendar import monthrange
from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class PaymentPeriod:
    index: int
    month: str
    start_date: date
    end_date: date
    due_date: date


def add_months(value: date, months: int) -> date:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, monthrange(year, month)[1])
    return date(year, month, day)


def month_label(value: date) -> str:
    return f"{value.year:04d}-{value.month:02d}"


def _month_bounds(value: date) -> tuple[date, date]:
    first = value.replace(day=1)
    last = value.replace(day=monthrange(value.year, value.month)[1])
    return first, last


def _is_leave_month(contract, month_start: date, month_end: date) -> bool:
    for leave in contract.academic_leaves:
        if leave.cancelled_at is not None:
            continue
        if leave.start_date <= month_start and leave.end_date >= month_end:
            return True
    return False


def contract_periods(contract) -> list[PaymentPeriod]:
    periods: list[PaymentPeriod] = []
    cursor = date(contract.start_date.year, contract.start_date.month, 1)
    last_year = contract.start_date.year + 100

    while len(periods) < contract.duration_months and cursor.year <= last_year:
        month_start, month_end = _month_bounds(cursor)

        if _is_leave_month(contract, month_start, month_end):
            cursor = add_months(cursor, 1)
            continue

        day = contract.payment_day or contract.start_date.day
        due_date = date(
            cursor.year,
            cursor.month,
            min(day, monthrange(cursor.year, cursor.month)[1]),
        )
        periods.append(
            PaymentPeriod(
                index=len(periods),
                month=month_label(cursor),
                start_date=month_start,
                end_date=month_end,
                due_date=due_date,
            )
        )
        cursor = add_months(cursor, 1)

    return periods


def find_contract_period(contract, payment_month: str) -> PaymentPeriod | None:
    for period in contract_periods(contract):
        if period.month == payment_month:
            return period
    return None


def current_month() -> str:
    return month_label(date.today())
