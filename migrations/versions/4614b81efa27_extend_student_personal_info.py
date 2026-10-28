"""extend student personal info

Revision ID: 4614b81efa27
Revises: 52dc7e1f1c88
Create Date: 2026-10-27 14:12:14.584891

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4614b81efa27'
down_revision: Union[str, Sequence[str], None] = '52dc7e1f1c88'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None



def upgrade() -> None:
    status_enum = sa.Enum("NOT_SUBMITTED", "PENDING", "APPROVED", "REVISION", name="personalinfostatus")
    status_enum.create(op.get_bind(), checkfirst=True)

    op.add_column("personal_info", sa.Column("middle_name", sa.String(100), nullable=True))
    op.add_column("personal_info", sa.Column("birth_place", sa.String(150), nullable=True))
    op.add_column("personal_info", sa.Column("registration_address", sa.String(255), nullable=True))
    op.add_column("personal_info", sa.Column("status", status_enum, server_default="PENDING", nullable=False))
    op.add_column("personal_info", sa.Column("review_comment", sa.String(500), nullable=True))
    op.add_column("personal_info", sa.Column("reviewed_by_admin_id", sa.Integer(), nullable=True))
    op.add_column("personal_info", sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True))

    op.create_foreign_key("fk_personal_info_reviewer", "personal_info", "users", ["reviewed_by_admin_id"], ["id"])


def downgrade() -> None:
    op.drop_constraint("fk_personal_info_reviewer", "personal_info", type_="foreignkey")
    op.drop_column("personal_info", "reviewed_at")
    op.drop_column("personal_info", "reviewed_by_admin_id")
    op.drop_column("personal_info", "review_comment")
    op.drop_column("personal_info", "status")
    op.drop_column("personal_info", "registration_address")
    op.drop_column("personal_info", "birth_place")
    op.drop_column("personal_info", "middle_name")

    sa.Enum("NOT_SUBMITTED", "PENDING", "APPROVED", "REVISION", name="personalinfostatus").drop(op.get_bind(), checkfirst=True)
