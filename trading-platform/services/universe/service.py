"""Point-in-time security master and historical-universe queries.

Every effective-dated range uses half-open semantics:
``valid_from <= as_of_date < valid_to``. A NULL ``valid_to`` is open-ended.
Missing history fails closed; current constituents are never substituted.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Optional, Type

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from apps.api.src.db.models import (
    Security,
    SecurityStatusHistory,
    SecuritySymbol,
    UniverseDefinition,
    UniverseMembership,
)
from services.data.capabilities import ProviderCapabilities

from .integrity import ResearchDataIntegrity, evaluate_research_integrity
from .models import HistoricalUniverseMember, TRADABLE_STATUSES


class HistoricalDataConflictError(ValueError):
    """Raised when overlapping records make a point-in-time answer ambiguous."""


class HistoricalUniverseService:
    """Focused SQLAlchemy service for security identity and universe history."""

    def __init__(self, session: Session):
        self.session = session

    @staticmethod
    def _contains(model: Type[Any], as_of_date: date):
        return and_(
            model.valid_from <= as_of_date,
            or_(model.valid_to.is_(None), as_of_date < model.valid_to),
        )

    @staticmethod
    def _validate_range(valid_from: date, valid_to: Optional[date]) -> None:
        if valid_to is not None and valid_to <= valid_from:
            raise ValueError("valid_to must be later than valid_from for a half-open range")

    def _ensure_no_overlap(
        self,
        model: Type[Any],
        filters: list[Any],
        valid_from: date,
        valid_to: Optional[date],
    ) -> None:
        self._validate_range(valid_from, valid_to)
        starts_before_new_end = (
            model.valid_from < valid_to if valid_to is not None else True
        )
        existing_ends_after_new_start = or_(
            model.valid_to.is_(None),
            model.valid_to > valid_from,
        )
        if self.session.query(model).filter(
            *filters,
            starts_before_new_end,
            existing_ends_after_new_start,
        ).first() is not None:
            raise HistoricalDataConflictError("effective-dated ranges must not overlap")

    def add_symbol(
        self,
        security_id: int,
        ticker: str,
        valid_from: date,
        valid_to: Optional[date],
        source: str,
        exchange: Optional[str] = None,
    ) -> SecuritySymbol:
        normalized_ticker = ticker.upper()
        self._ensure_no_overlap(
            SecuritySymbol,
            [SecuritySymbol.security_id == security_id],
            valid_from,
            valid_to,
        )
        self._ensure_no_overlap(
            SecuritySymbol,
            [SecuritySymbol.ticker == normalized_ticker],
            valid_from,
            valid_to,
        )
        symbol = SecuritySymbol(
            security_id=security_id,
            ticker=normalized_ticker,
            exchange=exchange,
            valid_from=valid_from,
            valid_to=valid_to,
            source=source,
        )
        self.session.add(symbol)
        self.session.flush()
        return symbol

    def add_status(
        self,
        security_id: int,
        status: str,
        valid_from: date,
        valid_to: Optional[date],
        source: str,
    ) -> SecurityStatusHistory:
        self._ensure_no_overlap(
            SecurityStatusHistory,
            [SecurityStatusHistory.security_id == security_id],
            valid_from,
            valid_to,
        )
        history = SecurityStatusHistory(
            security_id=security_id,
            status=status.upper(),
            valid_from=valid_from,
            valid_to=valid_to,
            source=source,
        )
        self.session.add(history)
        self.session.flush()
        return history

    def add_membership(
        self,
        universe_id: int,
        security_id: int,
        valid_from: date,
        valid_to: Optional[date],
        source: str,
        available_at: Any = None,
    ) -> UniverseMembership:
        self._ensure_no_overlap(
            UniverseMembership,
            [
                UniverseMembership.universe_id == universe_id,
                UniverseMembership.security_id == security_id,
            ],
            valid_from,
            valid_to,
        )
        membership = UniverseMembership(
            universe_id=universe_id,
            security_id=security_id,
            valid_from=valid_from,
            valid_to=valid_to,
            source=source,
            available_at=available_at,
        )
        self.session.add(membership)
        self.session.flush()
        return membership

    def get_symbol_as_of(
        self,
        security_id: int,
        as_of_date: date,
    ) -> Optional[SecuritySymbol]:
        rows = self.session.query(SecuritySymbol).filter(
            SecuritySymbol.security_id == security_id,
            self._contains(SecuritySymbol, as_of_date),
        ).all()
        if len(rows) > 1:
            raise HistoricalDataConflictError(
                f"multiple symbols are valid for security {security_id} on {as_of_date}"
            )
        return rows[0] if rows else None

    def resolve_security_as_of(
        self,
        ticker: str,
        as_of_date: date,
    ) -> Optional[Security]:
        rows = (
            self.session.query(Security)
            .join(SecuritySymbol, SecuritySymbol.security_id == Security.id)
            .filter(
                SecuritySymbol.ticker == ticker.upper(),
                self._contains(SecuritySymbol, as_of_date),
            )
            .all()
        )
        if len(rows) > 1:
            raise HistoricalDataConflictError(
                f"ticker {ticker.upper()} resolves to multiple securities on {as_of_date}"
            )
        return rows[0] if rows else None

    def is_security_tradable_as_of(
        self,
        security_id: int,
        as_of_date: date,
    ) -> bool:
        rows = self.session.query(SecurityStatusHistory).filter(
            SecurityStatusHistory.security_id == security_id,
            self._contains(SecurityStatusHistory, as_of_date),
        ).all()
        if len(rows) > 1:
            raise HistoricalDataConflictError(
                f"multiple statuses are valid for security {security_id} on {as_of_date}"
            )
        return bool(rows and rows[0].status.upper() in TRADABLE_STATUSES)

    def get_universe_as_of(
        self,
        universe_code: str,
        as_of_date: date,
    ) -> list[HistoricalUniverseMember]:
        universe = self.session.query(UniverseDefinition).filter(
            UniverseDefinition.code == universe_code
        ).one_or_none()
        if universe is None:
            return []

        memberships = self.session.query(UniverseMembership).filter(
            UniverseMembership.universe_id == universe.id,
            self._contains(UniverseMembership, as_of_date),
        ).all()

        result: list[HistoricalUniverseMember] = []
        seen_security_ids: set[int] = set()
        for membership in memberships:
            if membership.security_id in seen_security_ids:
                raise HistoricalDataConflictError(
                    f"multiple memberships are valid for security "
                    f"{membership.security_id} in {universe_code} on {as_of_date}"
                )
            seen_security_ids.add(membership.security_id)
            if not self.is_security_tradable_as_of(membership.security_id, as_of_date):
                continue
            symbol = self.get_symbol_as_of(membership.security_id, as_of_date)
            if symbol is None:
                continue
            security = self.session.get(Security, membership.security_id)
            if security is None:
                continue
            result.append(
                HistoricalUniverseMember(
                    security_id=security.id,
                    ticker=symbol.ticker,
                    exchange=symbol.exchange,
                    display_name=security.display_name,
                    membership_valid_from=membership.valid_from,
                    membership_valid_to=membership.valid_to,
                    membership_source=membership.source,
                )
            )
        return sorted(result, key=lambda member: (member.ticker, member.security_id))

    @staticmethod
    def get_integrity_status(
        provider: Any,
        universe_code: Optional[str],
        *,
        uses_current_constituents: bool = False,
    ) -> ResearchDataIntegrity:
        capabilities = getattr(provider, "capabilities", ProviderCapabilities())
        if not isinstance(capabilities, ProviderCapabilities):
            capabilities = ProviderCapabilities()
        provider_name = getattr(
            provider,
            "source_name",
            provider.__class__.__name__,
        )
        return evaluate_research_integrity(
            capabilities,
            str(provider_name),
            universe_code,
            uses_current_constituents=uses_current_constituents,
        )
