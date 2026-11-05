
"""add finik resolution fields

Revision ID: b7c2d9e4f1a3
Revises: a19166b5c548
Create Date: 2026-11-05 19:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7c2d9e4f1a3'
down_revision: Union[str, Sequence[str], None] = 'a19166b5c548'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'finik_transactions',
        sa.Column('review_reason', sa.String(length=255), nullable=True)
    )
    op.add_column(
        'finik_transactions',
        sa.Column('resolved_by_admin_id', sa.Integer(), nullable=True)
    )
    op.add_column(
        'finik_transactions',
        sa.Column('resolved_at', sa.DateTime(), nullable=True)
    )
    op.add_column(
        'finik_transactions',
        sa.Column('admin_comment', sa.String(length=500), nullable=True)
    )
    op.alter_column(
        'finik_transactions',
        'created_at',
        existing_type=sa.DateTime(),
        existing_nullable=False,
        server_default=sa.text('now()')
    )
    op.create_foreign_key(
        'fk_finik_transactions_resolved_by_admin_id_users',
        'finik_transactions', 'users',
        ['resolved_by_admin_id'], ['id']
    )
    op.create_index(
        'ix_finik_transactions_status',
        'finik_transactions',
        ['status']
    )


def downgrade() -> None:
    op.drop_index('ix_finik_transactions_status', table_name='finik_transactions')
    op.drop_constraint(
        'fk_finik_transactions_resolved_by_admin_id_users',
        'finik_transactions',
        type_='foreignkey'
    )
    op.alter_column(
        'finik_transactions',
        'created_at',
        existing_type=sa.DateTime(),
        existing_nullable=False,
        server_default=None
    )
    op.drop_column('finik_transactions', 'admin_comment')
    op.drop_column('finik_transactions', 'resolved_at')
    op.drop_column('finik_transactions', 'resolved_by_admin_id')
    op.drop_column('finik_transactions', 'review_reason')
