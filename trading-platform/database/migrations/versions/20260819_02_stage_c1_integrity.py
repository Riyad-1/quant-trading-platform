"""Add explicit historical universe coverage evidence.

Revision ID: 20260819_02
Revises: 20260819_01
Create Date: 2026-08-19
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260819_02"
down_revision: Union[str, None] = "20260819_01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "historical_universe_coverage" in tables:
        return

    op.create_table(
        "historical_universe_coverage",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "universe_id",
            sa.Integer(),
            sa.ForeignKey("universe_definitions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("provider_name", sa.String(100), nullable=False),
        sa.Column("coverage_start", sa.Date()),
        sa.Column("coverage_end", sa.Date()),
        sa.Column(
            "historical_population_verified",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "historical_membership_established",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "membership_availability_established",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "symbol_history_established",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "listing_history_established",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "delisted_coverage_established",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "provenance_known",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("source", sa.String(100), nullable=False),
        sa.Column("evidence_metadata", sa.JSON()),
        sa.Column("warnings", sa.JSON()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "coverage_end IS NULL OR coverage_start IS NULL "
            "OR coverage_end >= coverage_start",
            name="ck_historical_universe_coverage_range",
        ),
        sa.UniqueConstraint(
            "universe_id",
            "provider_name",
            "source",
            "coverage_start",
            "coverage_end",
            name="uq_historical_universe_coverage_evidence",
        ),
    )
    op.create_index(
        "ix_historical_universe_coverage_universe_id",
        "historical_universe_coverage",
        ["universe_id"],
    )
    op.create_index(
        "ix_historical_universe_coverage_provider_name",
        "historical_universe_coverage",
        ["provider_name"],
    )
    op.create_index(
        "ix_historical_universe_coverage_lookup",
        "historical_universe_coverage",
        ["universe_id", "provider_name"],
    )


def downgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "historical_universe_coverage" in tables:
        op.drop_table("historical_universe_coverage")
