"""Уведомления об оплате и расписании."""
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from myproject.database.models import Contract, ContractStatus, ContractType, Notification, Payment, PaymentStatus
from myproject.services.payment_allocation import payment_plan, confirmed_by_period


def create_notification(
    db: Session, user_id: int, type: str, title: str,
    message: str, event_key: str | None = None
) -> bool:
    statement = insert(Notification).values(
        user_id=user_id, type=type, title=title, message=message,
        event_key=event_key, is_read=False
    ).on_conflict_do_nothing(index_elements=["event_key"]).returning(Notification.id)
    return db.execute(statement).scalar_one_or_none() is not None


def notify_payment_confirmed(db: Session, payment: Payment, contract: Contract) -> None:
    create_notification(
        db, contract.student.user_id, "payment_confirmed", "Платёж подтверждён",
        f"Платёж {payment.amount} сом подтверждён.",
        event_key=f"payment:{payment.id}:confirmed"
    )


def send_payment_reminders(db: Session, today: date | None = None) -> int:
    today = today or datetime.now(ZoneInfo("Asia/Bishkek")).date()
    sent = 0

    contracts = db.query(Contract).filter(
        Contract.status == ContractStatus.ACTIVE,
        Contract.type == ContractType.ACADEMY
    ).all()
    for contract in contracts:
        pending = db.query(Payment.id).filter(
            Payment.contract_id == contract.id,
            Payment.status == PaymentStatus.PENDING
        ).first()
        if pending:
            continue
        paid = confirmed_by_period(contract, db)
        for period in payment_plan(contract):
            due_date = period["due_date"]
            if due_date > today + timedelta(days=3):
                continue
            remaining = period["amount"] - paid[period["index"]]
            if remaining <= 0:
                continue
            if due_date < today:
                kind = "payment_overdue"
                title = "Платёж просрочен"
                message = f"Платёж на {remaining} сом от {due_date:%d.%m.%Y} просрочен."
            else:
                kind = "payment_due"
                title = "Срок оплаты приближается"
                message = f"До {due_date:%d.%m.%Y} нужно оплатить {remaining} сом."
            if create_notification(
                db, contract.student.user_id, kind, title, message,
                event_key=f"{kind}:{contract.id}:{period['month']}"
            ):
                sent += 1
    db.commit()
    return sent


if __name__ == "__main__":
    from myproject.database.db import SessionLocal

    with SessionLocal() as session:
        print(send_payment_reminders(session))
