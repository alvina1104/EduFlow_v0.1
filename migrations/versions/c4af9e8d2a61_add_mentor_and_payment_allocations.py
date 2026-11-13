"""add mentor name and installment allocations

Revision ID: c4af9e8d2a61
Revises: b7c2d9e4f1a3

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "c4af9e8d2a61"
down_revision: Union[str, Sequence[str], None] = "b7c2d9e4f1a3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("groups", sa.Column("mentor_name", sa.String(150), nullable=True))
    op.add_column("contracts", sa.Column("installment_count", sa.Integer(), nullable=True))
    op.execute("UPDATE contracts SET installment_count = 2 WHERE type = 'COLLEGE'")
    op.create_table(
        "payment_allocations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("payment_id", sa.Integer(), sa.ForeignKey("payments.id"), nullable=False),
        sa.Column("period_index", sa.Integer(), nullable=False),
        sa.Column("payment_month", sa.String(7), nullable=True),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.CheckConstraint("amount > 0", name="ck_payment_allocations_positive"),
    )
    op.create_index(
        "uq_payment_allocations_payment_period", "payment_allocations",
        ["payment_id", "period_index"], unique=True,
    )
    # Старые payments остаются нетронутыми; сервис учитывает их по payment_month
    # или общей сумме, если контракт относится к колледжу.


def downgrade() -> None:
    op.drop_index("uq_payment_allocations_payment_period", table_name="payment_allocations")
    op.drop_table("payment_allocations")
    op.drop_column("contracts", "installment_count")
    op.drop_column("groups", "mentor_name")
