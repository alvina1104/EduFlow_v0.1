"""add payment day and academic leaves

Revision ID: 343e4dee48aa
Revises: af81d7836e38
Create Date: 2026-10-27 16:34:02.774636

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '343e4dee48aa'
down_revision: Union[str, Sequence[str], None] = 'af81d7836e38'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None



def upgrade() -> None:
    op.add_column("contracts", sa.Column("payment_day", sa.Integer(), nullable=True))
    op.create_check_constraint("ck_contracts_payment_day", "contracts", "payment_day BETWEEN 1 AND 28")

    op.create_table(
        "academic_leaves",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("contract_id", sa.Integer(), sa.ForeignKey("contracts.id"), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("reason", sa.String(500), nullable=True),
        sa.Column("created_by_admin_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("end_date >= start_date", name="ck_academic_leaves_dates")
    )


def downgrade() -> None:
    op.drop_table("academic_leaves")
    op.drop_constraint("ck_contracts_payment_day", "contracts", type_="check")
    op.drop_column("contracts", "payment_day")

