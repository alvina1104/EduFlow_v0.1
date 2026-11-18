"""store immutable EduFlow confirmations for verified Finik payments

Revision ID: d6b309e67142
Revises: c4af9e8d2a61

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d6b309e67142"
down_revision: Union[str, Sequence[str], None] = "c4af9e8d2a61"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "finik_receipts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("payment_id", sa.Integer(), sa.ForeignKey("payments.id"),
                  unique=True, nullable=False),
        sa.Column("receipt_number", sa.String(40), unique=True, nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("provider_transaction_id", sa.String(150), nullable=False),
        sa.Column("provider_operation_id", sa.String(150), nullable=True),
        sa.Column("provider_paid_at", sa.DateTime(), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(), nullable=False),
        sa.Column("verification_source", sa.String(30), nullable=False),
        sa.Column("allocation_snapshot", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("finik_receipts")
