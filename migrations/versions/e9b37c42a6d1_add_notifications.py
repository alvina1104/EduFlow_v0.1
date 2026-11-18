"""add notifications

Revision ID: e9b37c42a6d1
Revises: d6b309e67142
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e9b37c42a6d1"
down_revision: Union[str, Sequence[str], None] = "d6b309e67142"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "notifications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("type", sa.String(50), nullable=False),
        sa.Column("title", sa.String(150), nullable=False),
        sa.Column("message", sa.String(500), nullable=False),
        sa.Column("event_key", sa.String(150), unique=True, nullable=True),
        sa.Column("is_read", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()"))
    )
    op.create_index("ix_notifications_user_id", "notifications", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_notifications_user_id", table_name="notifications")
    op.drop_table("notifications")
