"""Add point-in-time securities and historical universes.

Revision ID: 20260819_01
Revises: None
Create Date: 2026-08-19
"""

from __future__ import annotations

from datetime import date
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260819_01"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

BACKFILL_SOURCE = "stage_c_asset_backfill_current_state"


def _table_names() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _column_names(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {column["name"] for column in inspector.get_columns(table_name)}


def upgrade() -> None:
    tables = _table_names()

    if "securities" not in tables:
        op.create_table(
            "securities",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("security_type", sa.String(50), nullable=False, server_default="COMMON_STOCK"),
            sa.Column("display_name", sa.String(255)),
            sa.Column("primary_exchange", sa.String(50)),
            sa.Column("currency", sa.String(10)),
            sa.Column("country", sa.String(10)),
            sa.Column("current_status", sa.String(30), nullable=False, server_default="UNKNOWN"),
            sa.Column("figi", sa.String(20), unique=True),
            sa.Column("composite_figi", sa.String(20), unique=True),
            sa.Column("isin", sa.String(20), unique=True),
            sa.Column("cusip", sa.String(20), unique=True),
            sa.Column("provider_identifiers", sa.JSON()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
        op.create_index("ix_securities_current_status", "securities", ["current_status"])

    tables = _table_names()
    if "security_symbols" not in tables:
        op.create_table(
            "security_symbols",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("security_id", sa.Integer(), sa.ForeignKey("securities.id", ondelete="CASCADE"), nullable=False),
            sa.Column("ticker", sa.String(20), nullable=False),
            sa.Column("exchange", sa.String(50)),
            sa.Column("valid_from", sa.Date(), nullable=False),
            sa.Column("valid_to", sa.Date()),
            sa.Column("source", sa.String(100), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.CheckConstraint("valid_to IS NULL OR valid_to > valid_from", name="ck_security_symbol_valid_range"),
            sa.UniqueConstraint("security_id", "ticker", "exchange", "valid_from", name="uq_security_symbol_start"),
        )
        op.create_index("ix_security_symbols_security_id", "security_symbols", ["security_id"])
        op.create_index("ix_security_symbols_ticker", "security_symbols", ["ticker"])
        op.create_index("ix_security_symbols_lookup", "security_symbols", ["ticker", "valid_from", "valid_to"])

    tables = _table_names()
    if "security_status_history" not in tables:
        op.create_table(
            "security_status_history",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("security_id", sa.Integer(), sa.ForeignKey("securities.id", ondelete="CASCADE"), nullable=False),
            sa.Column("status", sa.String(30), nullable=False),
            sa.Column("valid_from", sa.Date(), nullable=False),
            sa.Column("valid_to", sa.Date()),
            sa.Column("source", sa.String(100), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.CheckConstraint("valid_to IS NULL OR valid_to > valid_from", name="ck_security_status_valid_range"),
            sa.UniqueConstraint("security_id", "valid_from", name="uq_security_status_start"),
        )
        op.create_index("ix_security_status_security_id", "security_status_history", ["security_id"])
        op.create_index("ix_security_status_status", "security_status_history", ["status"])
        op.create_index("ix_security_status_lookup", "security_status_history", ["security_id", "valid_from", "valid_to"])

    tables = _table_names()
    if "universe_definitions" not in tables:
        op.create_table(
            "universe_definitions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("code", sa.String(100), nullable=False, unique=True),
            sa.Column("name", sa.String(255), nullable=False),
            sa.Column("description", sa.Text()),
            sa.Column("source", sa.String(100), nullable=False),
            sa.Column("methodology", sa.JSON()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
        op.create_index("ix_universe_definitions_code", "universe_definitions", ["code"])

    tables = _table_names()
    if "universe_memberships" not in tables:
        op.create_table(
            "universe_memberships",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("universe_id", sa.Integer(), sa.ForeignKey("universe_definitions.id", ondelete="CASCADE"), nullable=False),
            sa.Column("security_id", sa.Integer(), sa.ForeignKey("securities.id", ondelete="CASCADE"), nullable=False),
            sa.Column("valid_from", sa.Date(), nullable=False),
            sa.Column("valid_to", sa.Date()),
            sa.Column("source", sa.String(100), nullable=False),
            sa.Column("available_at", sa.DateTime(timezone=True)),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.CheckConstraint("valid_to IS NULL OR valid_to > valid_from", name="ck_universe_membership_valid_range"),
            sa.UniqueConstraint("universe_id", "security_id", "valid_from", name="uq_universe_membership_start"),
        )
        op.create_index("ix_universe_membership_universe_id", "universe_memberships", ["universe_id"])
        op.create_index("ix_universe_membership_security_id", "universe_memberships", ["security_id"])
        op.create_index("ix_universe_membership_lookup", "universe_memberships", ["universe_id", "valid_from", "valid_to"])

    tables = _table_names()
    if "corporate_actions" not in tables:
        op.create_table(
            "corporate_actions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("security_id", sa.Integer(), sa.ForeignKey("securities.id", ondelete="CASCADE"), nullable=False),
            sa.Column("action_type", sa.String(30), nullable=False),
            sa.Column("event_date", sa.Date()),
            sa.Column("effective_date", sa.Date(), nullable=False),
            sa.Column("available_at", sa.DateTime(timezone=True)),
            sa.Column("source", sa.String(100), nullable=False),
            sa.Column("source_event_id", sa.String(200)),
            sa.Column("action_metadata", sa.JSON()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("source", "source_event_id", name="uq_corporate_action_source_event"),
        )
        op.create_index("ix_corporate_actions_security_id", "corporate_actions", ["security_id"])
        op.create_index("ix_corporate_actions_action_type", "corporate_actions", ["action_type"])
        op.create_index("ix_corporate_actions_effective_date", "corporate_actions", ["effective_date"])
        op.create_index("ix_corporate_actions_security_date", "corporate_actions", ["security_id", "effective_date"])

    tables = _table_names()
    if "assets" in tables and "security_id" not in _column_names("assets"):
        with op.batch_alter_table("assets") as batch_op:
            batch_op.add_column(sa.Column("security_id", sa.Integer(), nullable=True))
            batch_op.create_foreign_key(
                "fk_assets_security_id_securities",
                "securities",
                ["security_id"],
                ["id"],
                ondelete="SET NULL",
            )
            batch_op.create_index("ix_assets_security_id", ["security_id"])

    tables = _table_names()
    if "news_articles" in tables:
        article_columns = _column_names("news_articles")
        with op.batch_alter_table("news_articles") as batch_op:
            if "first_seen_at" not in article_columns:
                batch_op.add_column(sa.Column("first_seen_at", sa.DateTime(timezone=True)))
            if "received_at" not in article_columns:
                batch_op.add_column(sa.Column("received_at", sa.DateTime(timezone=True)))
            if "available_at" not in article_columns:
                batch_op.add_column(sa.Column("available_at", sa.DateTime(timezone=True)))
                batch_op.create_index("ix_news_articles_available_at", ["available_at"])
            if "revision" not in article_columns:
                batch_op.add_column(sa.Column("revision", sa.Integer()))

    if "assets" in _table_names():
        _backfill_current_assets()


def _backfill_current_assets() -> None:
    connection = op.get_bind()
    # The migration execution date is the earliest observed validity; no earlier
    # symbol or listing history is inferred from a current-state asset row.
    backfill_effective_date = date.today()
    metadata = sa.MetaData()
    assets = sa.Table("assets", metadata, autoload_with=connection)
    securities = sa.Table("securities", metadata, autoload_with=connection)
    symbols = sa.Table("security_symbols", metadata, autoload_with=connection)
    statuses = sa.Table("security_status_history", metadata, autoload_with=connection)

    current_assets = connection.execute(
        sa.select(
            assets.c.id,
            assets.c.ticker,
            assets.c.name,
            assets.c.exchange,
            assets.c.status,
            assets.c.security_id,
        )
    ).mappings()

    for asset in current_assets:
        if asset["security_id"] is not None:
            continue
        raw_status = asset["status"]
        status_value = getattr(raw_status, "value", raw_status) or "UNKNOWN"
        result = connection.execute(
            securities.insert().values(
                security_type="UNKNOWN",
                display_name=asset["name"],
                primary_exchange=asset["exchange"],
                current_status=str(status_value).upper(),
            )
        )
        security_id = result.inserted_primary_key[0]
        connection.execute(
            symbols.insert().values(
                security_id=security_id,
                ticker=asset["ticker"],
                exchange=asset["exchange"],
                valid_from=backfill_effective_date,
                valid_to=None,
                source=BACKFILL_SOURCE,
            )
        )
        connection.execute(
            statuses.insert().values(
                security_id=security_id,
                status=str(status_value).upper(),
                valid_from=backfill_effective_date,
                valid_to=None,
                source=BACKFILL_SOURCE,
            )
        )
        connection.execute(
            assets.update()
            .where(assets.c.id == asset["id"])
            .values(security_id=security_id)
        )


def downgrade() -> None:
    tables = _table_names()
    if "news_articles" in tables:
        article_columns = _column_names("news_articles")
        with op.batch_alter_table("news_articles") as batch_op:
            if "revision" in article_columns:
                batch_op.drop_column("revision")
            if "available_at" in article_columns:
                batch_op.drop_index("ix_news_articles_available_at")
                batch_op.drop_column("available_at")
            if "received_at" in article_columns:
                batch_op.drop_column("received_at")
            if "first_seen_at" in article_columns:
                batch_op.drop_column("first_seen_at")

    if "assets" in tables and "security_id" in _column_names("assets"):
        with op.batch_alter_table("assets") as batch_op:
            batch_op.drop_index("ix_assets_security_id")
            batch_op.drop_constraint("fk_assets_security_id_securities", type_="foreignkey")
            batch_op.drop_column("security_id")

    for table_name in (
        "corporate_actions",
        "universe_memberships",
        "universe_definitions",
        "security_status_history",
        "security_symbols",
        "securities",
    ):
        if table_name in _table_names():
            op.drop_table(table_name)
