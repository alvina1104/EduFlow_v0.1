"""Track student enrollments and group transfers.

Old assignments are backfilled with unknown start dates (NULL).
No student, contract or payment is deleted or rewritten.

Revision ID: 9a4c2e109dbf
Revises: 2e4a86919abd
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "9a4c2e109dbf"
down_revision: Union[str, Sequence[str], None] = "2e4a86919abd"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "student_group_history",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("student_id", sa.Integer(), sa.ForeignKey("students.id", ondelete="CASCADE"), nullable=False),
        sa.Column("group_id", sa.Integer(), sa.ForeignKey("groups.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("kind", sa.Enum("ENROLLMENT", "TRANSFER", name="studentgrouphistorykind"), nullable=False),
        sa.Column("from_date", sa.Date(), nullable=True),
        sa.Column("to_date", sa.Date(), nullable=True),
        sa.Column("reason", sa.String(length=500), nullable=True),
    )
    op.create_index("ix_student_group_history_student_id", "student_group_history", ["student_id"])
    op.create_index(
        "uq_student_group_history_open",
        "student_group_history",
        ["student_id"],
        unique=True,
        postgresql_where=sa.text("to_date IS NULL"),
        sqlite_where=sa.text("to_date IS NULL"),
    )
    # No reliable initial enrollment date exists in the old schema.
    # The backfill preserves only the current group, with an unknown start date.
    op.execute(
        sa.text(
            """INSERT INTO student_group_history (student_id, group_id, kind, from_date, to_date)
            SELECT id, group_id, 'ENROLLMENT', NULL, NULL
            FROM students WHERE group_id IS NOT NULL"""
        )
    )


def downgrade() -> None:
    op.drop_index("uq_student_group_history_open", table_name="student_group_history")
    op.drop_index("ix_student_group_history_student_id", table_name="student_group_history")
    op.drop_table("student_group_history")
    sa.Enum("ENROLLMENT", "TRANSFER", name="studentgrouphistorykind").drop(op.get_bind(), checkfirst=True)
