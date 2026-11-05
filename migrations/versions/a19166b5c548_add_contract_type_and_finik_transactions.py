
"""add contract type and finik transactions

Revision ID: a19166b5c548
Revises: 343e4dee48aa
Create Date: 2026-11-05 18:20:59.116750

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a19166b5c548'
down_revision: Union[str, Sequence[str], None] = '343e4dee48aa'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    contract_type = sa.Enum("ACADEMY", "COLLEGE", name="contracttype")
    contract_type.create(op.get_bind(), checkfirst=True)

    op.create_table(
        'finik_transactions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('payment_id', sa.Integer(), nullable=False),
        sa.Column('provider_payment_id', sa.String(length=36), nullable=False),
        sa.Column('provider_transaction_id', sa.String(length=150), nullable=True),
        sa.Column('provider_operation_id', sa.String(length=150), nullable=True),
        sa.Column('status', sa.String(length=30), nullable=False),
        sa.Column('payment_url', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('confirmed_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['payment_id'], ['payments.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('payment_id'),
        sa.UniqueConstraint('provider_payment_id'),
        sa.UniqueConstraint('provider_transaction_id')
    )

    op.add_column(
        'contracts',
        sa.Column(
            'type',
            sa.Enum('ACADEMY', 'COLLEGE', name='contracttype', create_type=False),
            server_default='ACADEMY',
            nullable=False
        )
    )


def downgrade() -> None:
    op.drop_table('finik_transactions')
    op.drop_column('contracts', 'type')

    contract_type = sa.Enum("ACADEMY", "COLLEGE", name="contracttype")
    contract_type.drop(op.get_bind(), checkfirst=True)
