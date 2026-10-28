"""add payment request id

Revision ID: af81d7836e38
Revises: 3ab9351a5f73
Create Date: 2026-10-27 16:18:22.353812

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'af81d7836e38'
down_revision: Union[str, Sequence[str], None] = '3ab9351a5f73'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None



def upgrade() -> None:
    op.add_column("payments", sa.Column("request_id", sa.String(36), nullable=True))
    op.add_column("payments", sa.Column("created_by_user_id", sa.Integer(), nullable=True))
    op.create_unique_constraint("uq_payments_request_id", "payments", ["request_id"])
    op.create_foreign_key("fk_payments_created_by_user", "payments", "users", ["created_by_user_id"], ["id"])


def downgrade() -> None:
    op.drop_constraint("fk_payments_created_by_user", "payments", type_="foreignkey")
    op.drop_constraint("uq_payments_request_id", "payments", type_="unique")
    op.drop_column("payments", "created_by_user_id")
    op.drop_column("payments", "request_id")
