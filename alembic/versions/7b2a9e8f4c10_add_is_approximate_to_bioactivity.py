"""Add is_approximate column to bioactivities

Revision ID: 7b2a9e8f4c10
Revises: 6a1721321edd
Create Date: 2026-09-04 17:20:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "7b2a9e8f4c10"
down_revision: Union[str, None] = "6a1721321edd"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("bioactivities", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("is_approximate", sa.Boolean(), nullable=False, server_default=sa.text("0"))
        )
        batch_op.create_index(
            batch_op.f("ix_bioactivities_is_approximate"), ["is_approximate"], unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table("bioactivities", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_bioactivities_is_approximate"))
        batch_op.drop_column("is_approximate")
