"""Point-in-time security master and historical-universe queries.

Every effective-dated range uses half-open semantics:
``valid_from <= as_of_date < valid_to``. A NULL ``valid_to`` is open-ended.
Missing history fails closed; current constituents are never substituted.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional, Type

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from apps.api.src.db.models import (
    HistoricalUniverseCoverageRecord,
    Security,
    SecurityStatusHistory,
    SecuritySymbol,
    UniverseDefinition,
    UniverseMembership,
)
from services.data.capabilities import ProviderCapabilities

from .integrity import ResearchDataIntegrity, evaluate_research_integrity
from .models import (
    HistoricalUniverseCoverage,
    HistoricalUniverseMember,
    TRADABLE_STATUSES,
)


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

    def add_coverage(
        self,
        coverage: HistoricalUniverseCoverage,
        *,
        evidence_metadata: Any = None,
    ) -> HistoricalUniverseCoverageRecord:
        """Persist explicit coverage evidence without deriving it from row counts."""
        universe = self.session.query(UniverseDefinition).filter(
            UniverseDefinition.code == coverage.universe_code
        ).one_or_none()
        if universe is None:
            raise ValueError(f"unknown universe code: {coverage.universe_code}")
        if not coverage.provider_name:
            raise ValueError("coverage provider_name is required")
        if not coverage.source:
            raise ValueError("coverage source is required")
        if (
            coverage.coverage_start is not None
            and coverage.coverage_end is not None
            and coverage.coverage_end < coverage.coverage_start
        ):
            raise ValueError("coverage_end must be on or after coverage_start")

        record = HistoricalUniverseCoverageRecord(
            universe_id=universe.id,
            provider_name=coverage.provider_name,
            coverage_start=coverage.coverage_start,
            coverage_end=coverage.coverage_end,
            historical_population_verified=coverage.historical_population_verified,
            historical_membership_established=coverage.historical_membership_established,
            membership_availability_established=(
                coverage.membership_availability_established
            ),
            symbol_history_established=coverage.symbol_history_established,
            listing_history_established=coverage.listing_history_established,
            delisted_coverage_established=coverage.delisted_coverage_established,
            provenance_known=coverage.provenance_known,
            source=coverage.source,
            evidence_metadata=evidence_metadata,
            warnings=list(coverage.warnings),
        )
        self.session.add(record)
        self.session.flush()
        return record

    def get_coverage(
        self,
        universe_code: str,
        provider_name: str,
    ) -> Optional[HistoricalUniverseCoverage]:
        records = (
            self.session.query(HistoricalUniverseCoverageRecord)
            .join(
                UniverseDefinition,
                HistoricalUniverseCoverageRecord.universe_id == UniverseDefinition.id,
            )
            .filter(
                UniverseDefinition.code == universe_code,
                HistoricalUniverseCoverageRecord.provider_name == provider_name,
            )
            .all()
        )
        if len(records) > 1:
            raise HistoricalDataConflictError(
                f"multiple coverage records exist for {provider_name}/{universe_code}"
            )
        if not records:
            return None
        record = records[0]
        return HistoricalUniverseCoverage(
            universe_code=universe_code,
            provider_name=record.provider_name,
            coverage_start=record.coverage_start,
            coverage_end=record.coverage_end,
            historical_population_verified=record.historical_population_verified,
            historical_membership_established=record.historical_membership_established,
            membership_availability_established=(
                record.membership_availability_established
            ),
            symbol_history_established=record.symbol_history_established,
            listing_history_established=record.listing_history_established,
            delisted_coverage_established=record.delisted_coverage_established,
            provenance_known=record.provenance_known,
            source=record.source,
            warnings=tuple(record.warnings or ()),
        )

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
        *,
        known_at: Optional[datetime] = None,
    ) -> list[HistoricalUniverseMember]:
        universe = self.session.query(UniverseDefinition).filter(
            UniverseDefinition.code == universe_code
        ).one_or_none()
        if universe is None:
            return []

        membership_query = self.session.query(UniverseMembership).filter(
            UniverseMembership.universe_id == universe.id,
            self._contains(UniverseMembership, as_of_date),
        )
        if known_at is not None:
            membership_query = membership_query.filter(
                UniverseMembership.available_at.is_not(None),
                UniverseMembership.available_at <= known_at,
            )
        memberships = membership_query.all()

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
                    membership_available_at=membership.available_at,
                )
            )
        return sorted(result, key=lambda member: (member.ticker, member.security_id))

    def get_point_in_time_universe(
        self,
        universe_code: str,
        as_of_date: date,
        known_at: datetime,
    ) -> list[HistoricalUniverseMember]:
        """Return effective members whose membership fact was known by known_at."""
        return self.get_universe_as_of(
            universe_code,
            as_of_date,
            known_at=known_at,
        )

    def get_integrity_status(
        self,
        provider: Any,
        universe_code: Optional[str],
        *,
        coverage: Optional[HistoricalUniverseCoverage] = None,
        requested_start: Optional[date] = None,
        requested_end: Optional[date] = None,
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
        provider_name = str(provider_name)
        if coverage is None and universe_code is not None:
            coverage = self.get_coverage(universe_code, provider_name)
        return evaluate_research_integrity(
            capabilities,
            provider_name,
            universe_code,
            coverage=coverage,
            requested_start=requested_start,
            requested_end=requested_end,
            uses_current_constituents=uses_current_constituents,
        )
