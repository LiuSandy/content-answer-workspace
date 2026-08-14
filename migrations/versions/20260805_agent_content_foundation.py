"""add AIOperation.output_metadata

R0：基线与跨计划契约修正。仅增加兼容字段，不删除旧字段或入口。
output_metadata 供质检/选题等结构化报告写输出字段，不占用 input_metadata。

Revision ID: 20260805_foundation
Revises: 20260804_mem
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision: str = '20260805_foundation'
down_revision: Union[str, None] = '20260804_mem'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'ai_operations',
        sa.Column('output_metadata', JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )


def downgrade() -> None:
    op.drop_column('ai_operations', 'output_metadata')
