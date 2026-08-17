"""widen localizacao to Text

Revision ID: 002
Revises: 001
Create Date: 2026-06-23

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("vagas", "localizacao", type_=sa.Text(), existing_nullable=True)


def downgrade() -> None:
    op.alter_column("vagas", "localizacao", type_=sa.String(200), existing_nullable=True)
