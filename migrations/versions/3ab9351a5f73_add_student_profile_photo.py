"""add student profile photo

Revision ID: 3ab9351a5f73
Revises: 4614b81efa27
Create Date: 2026-10-27 15:56:44.818214

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3ab9351a5f73'
down_revision: Union[str, Sequence[str], None] = '4614b81efa27'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("students", sa.Column("profile_photo", sa.LargeBinary(), nullable=True))


def downgrade() -> None:
    op.drop_column("students", "profile_photo")
