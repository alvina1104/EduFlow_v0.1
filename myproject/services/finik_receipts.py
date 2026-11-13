"""Внутренняя квитанция EduFlow по подтверждённому платежу Finik.

Не подменяет официальный фискальный чек провайдера или налоговой системы.
"""
from fastapi import HTTPException
from sqlalchemy.orm import Session

from myproject.database.models import (
    FinikReceipt, FinikTransaction, Payment, PaymentStatus
)


def create_finik_receipt(
    payment: Payment,
    transaction: FinikTransaction,
    db: Session,
    verification_source: str,
) -> FinikReceipt:
    """Создать запись один раз, в той же транзакции, что подтверждение оплаты."""
    if payment.status != PaymentStatus.CONFIRMED or transaction.status != "confirmed":
        raise HTTPException(409, "Подтверждённый платёж Finik не найден")
    if not transaction.provider_transaction_id:
        raise HTTPException(409, "Не указан Transaction ID Finik")

    existing = db.query(FinikReceipt).filter(
        FinikReceipt.payment_id == payment.id
    ).first()
    if existing:
        return existing

    # Сохраняем согласованное распределение сумм, даже если график
    # контракта позднее будет изменён.
    db.flush()
    db.expire(payment, ["allocations"])
    allocation_snapshot = [
        {
            "period_index": part.period_index,
            "payment_month": part.payment_month,
            "amount": str(part.amount),
        }
        for part in sorted(payment.allocations, key=lambda item: item.period_index)
    ]

    receipt = FinikReceipt(
        payment_id=payment.id,
        receipt_number=f"EDU-FINIK-{payment.id:010d}",
        amount=payment.amount,
        currency="KGS",
        provider_transaction_id=transaction.provider_transaction_id,
        provider_operation_id=transaction.provider_operation_id,
        provider_paid_at=None,  # Finik не гарантирует время оплаты в callback.
        confirmed_at=transaction.confirmed_at,
        verification_source=verification_source,
        allocation_snapshot=allocation_snapshot,
    )
    db.add(receipt)
    return receipt
