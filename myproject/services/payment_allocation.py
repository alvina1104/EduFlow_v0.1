"""Распределение платежей по периодам контракта.

Один Payment может покрывать несколько периодов. Исторические платежи без
PaymentAllocation учитываются без переписывания финансовой истории.
"""
from decimal import Decimal, ROUND_DOWN
from fastapi import HTTPException
from sqlalchemy.orm import Session

from myproject.database.models import (
    Contract, ContractType, Payment, PaymentAllocation, PaymentStatus
)
from myproject.services.schedule import contract_periods


ZERO = Decimal("0.00")
CENT = Decimal("0.01")


def payment_plan(contract: Contract) -> list[dict]:
    if contract.type == ContractType.ACADEMY:
        return [
            {"index": period.index, "month": period.month,
             "due_date": period.due_date, "amount": contract.monthly_payment}
            for period in contract_periods(contract)
        ]

    count = contract.installment_count or 2
    if count not in (2, 3):
        raise HTTPException(409, "Для колледжа доступны 2 или 3 взноса")
    regular = (contract.total_amount / count).quantize(CENT, rounding=ROUND_DOWN)
    return [
        {"index": index, "month": None, "due_date": None,
         "amount": regular if index < count - 1
         else contract.total_amount - regular * (count - 1)}
        for index in range(count)
    ]


def confirmed_by_period(
    contract: Contract, db: Session, exclude_payment_id: int | None = None
) -> dict[int, Decimal]:
    """Новые платежи учитываются из allocation, старые — из payment_month."""
    plan = payment_plan(contract)
    paid = {period["index"]: ZERO for period in plan}
    month_index = {period["month"]: period["index"] for period in plan}
    query = db.query(Payment).filter(
        Payment.contract_id == contract.id,
        Payment.status == PaymentStatus.CONFIRMED
    )
    if exclude_payment_id is not None:
        query = query.filter(Payment.id != exclude_payment_id)

    for payment in query.order_by(Payment.created_at, Payment.id).all():
        if payment.allocations:
            for allocation in payment.allocations:
                if allocation.period_index in paid:
                    paid[allocation.period_index] += allocation.amount
            continue

        # Совместимость со старыми записями (без распределения).
        if contract.type == ContractType.ACADEMY:
            index = month_index.get(payment.payment_month)
            if index is not None:
                paid[index] += payment.amount
        else:
            remainder = payment.amount
            for period in plan:
                index = period["index"]
                available = max(ZERO, period["amount"] - paid[index])
                amount = min(remainder, available)
                paid[index] += amount
                remainder -= amount
                if remainder <= ZERO:
                    break

    return paid


def distribute_payment(
    contract: Contract, db: Session, amount: Decimal,
    requested_month: str | None = None,
    exclude_payment_id: int | None = None
) -> list[dict]:
    """Строго с первого непогашенного периода, далее по порядку."""
    if amount <= ZERO:
        raise HTTPException(422, "Сумма платежа должна быть положительной")

    plan = payment_plan(contract)
    paid = confirmed_by_period(contract, db, exclude_payment_id)
    open_periods = [
        (period, max(ZERO, period["amount"] - paid[period["index"]]))
        for period in plan
        if period["amount"] - paid[period["index"]] > ZERO
    ]
    if not open_periods:
        raise HTTPException(409, "Контракт уже полностью оплачен")

    first_period = open_periods[0][0]
    if contract.type == ContractType.ACADEMY:
        if requested_month and requested_month != first_period["month"]:
            raise HTTPException(
                409, "Сначала оплатите предыдущий месяц: " + first_period["month"]
            )
    # Для колледжа месяц не задаёт номер взноса — деньги распределяются автоматически.
    available = sum((outstanding for _, outstanding in open_periods), ZERO)
    if amount > available:
        raise HTTPException(409, "Сумма превышает остаток контракта")

    allocations = []
    remainder = amount
    for period, outstanding in open_periods:
        if remainder <= ZERO:
            break
        chunk = min(remainder, outstanding)
        allocations.append({
            "period_index": period["index"],
            "payment_month": period["month"],
            "amount": chunk,
        })
        remainder -= chunk

    return allocations


def prepare_confirmation(
    payment: Payment, contract: Contract, db: Session
) -> list[dict]:
    """Повторная проверка под блокировкой контракта перед подтверждением."""
    expected = distribute_payment(
        contract, db, payment.amount,
        requested_month=payment.payment_month if contract.type == ContractType.ACADEMY else None,
        exclude_payment_id=payment.id,
    )
    if payment.allocations:
        actual = [
            (item.period_index, item.payment_month, item.amount)
            for item in payment.allocations
        ]
        planned = [
            (item["period_index"], item["payment_month"], item["amount"])
            for item in expected
        ]
        if sorted(actual) != sorted(planned):
            raise HTTPException(409, "График платежей изменился, требуется сверка")
    return expected


def save_allocations(payment: Payment, db: Session, allocations: list[dict]) -> None:
    if payment.allocations:
        return
    for allocation in allocations:
        db.add(PaymentAllocation(payment=payment, **allocation))
