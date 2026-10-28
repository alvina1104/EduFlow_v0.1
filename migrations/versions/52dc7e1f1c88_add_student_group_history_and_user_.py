"""add student group history and user created at

Revision ID: 52dc7e1f1c88
Revises: 2e4a86919abd
Create Date: 2026-10-27 12:46:55.555396

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '52dc7e1f1c88'
down_revision: Union[str, Sequence[str], None] = '2e4a86919abd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None



def upgrade() -> None:
    # 1. Добавляем дату создания аккаунта
    op.add_column(
        "users",
        sa.Column("created_at", sa.Date(), nullable=True)
    )

    # 2. Создаём таблицу истории групп
    op.create_table(
        "student_group_history",
        sa.Column("id", sa.Integer(), primary_key=True),

        sa.Column(
            "student_id",
            sa.Integer(),
            sa.ForeignKey("students.id"),
            nullable=False
        ),

        sa.Column(
            "group_id",
            sa.Integer(),
            sa.ForeignKey("groups.id"),
            nullable=False
        ),

        sa.Column(
            "kind",
            sa.Enum(
                "ENROLLMENT",
                "TRANSFER",
                name="studentgrouphistorykind"
            ),
            nullable=False
        ),

        sa.Column("from_date", sa.Date(), nullable=True),
        sa.Column("to_date", sa.Date(), nullable=True),
        sa.Column("reason", sa.String(500), nullable=True),
    )

    # 3. Запрещаем две активные группы
    op.create_index(
        "uq_student_group_history_open",
        "student_group_history",
        ["student_id"],
        unique=True,
        postgresql_where=sa.text("to_date IS NULL"),
        sqlite_where=sa.text("to_date IS NULL"),
    )

    # 4. Сохраняем текущие группы старых студентов
    op.execute(
        """
        INSERT INTO student_group_history
            (student_id, group_id, kind, from_date, to_date)
        SELECT id, group_id, 'ENROLLMENT', NULL, NULL
        FROM students
        WHERE group_id IS NOT NULL
        """
    )


def downgrade() -> None:
    op.drop_index(
        "uq_student_group_history_open",
        table_name="student_group_history"
    )

    op.drop_table("student_group_history")

    sa.Enum(
        "ENROLLMENT",
        "TRANSFER",
        name="studentgrouphistorykind"
    ).drop(op.get_bind(), checkfirst=True)

    op.drop_column("users", "created_at")
