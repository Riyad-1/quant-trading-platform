"""Domain models for point-in-time security and universe queries."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from typing import Any, Dict, Optional


class SecurityLifecycleStatus(str, Enum):
    ACTIVE = "ACTIVE"
    DELISTED = "DELISTED"
    SUSPENDED = "SUSPENDED"
    ACQUIRED = "ACQUIRED"
    BANKRUPT = "BANKRUPT"
    UNKNOWN = "UNKNOWN"


TRADABLE_STATUSES = frozenset({SecurityLifecycleStatus.ACTIVE.value})


@dataclass(frozen=True)
class HistoricalUniverseCoverage:
    """Explicit evidence for one historical universe/provider dataset.

    Coverage dates are inclusive evidence bounds. They do not come from row
    counts, and every evidence flag must be set by a trusted ingestion or
    validation process.
    """

    universe_code: str
    provider_name: str
    coverage_start: Optional[date] = None
    coverage_end: Optional[date] = None
    historical_population_verified: bool = False
    historical_membership_established: bool = False
    membership_availability_established: bool = False
    symbol_history_established: bool = False
    listing_history_established: bool = False
    delisted_coverage_established: bool = False
    provenance_known: bool = False
    source: Optional[str] = None
    warnings: tuple[str, ...] = ()

    def covers_requested_period(
        self,
        requested_start: Optional[date],
        requested_end: Optional[date],
    ) -> bool:
        if (
            requested_start is None
            or requested_end is None
            or requested_end < requested_start
            or self.coverage_start is None
            or self.coverage_end is None
        ):
            return False
        return (
            self.coverage_start <= requested_start
            and self.coverage_end >= requested_end
        )

    def complete_for_requested_period(
        self,
        requested_start: Optional[date],
        requested_end: Optional[date],
    ) -> bool:
        return (
            self.covers_requested_period(requested_start, requested_end)
            and self.historical_population_verified
            and self.historical_membership_established
            and self.membership_availability_established
            and self.symbol_history_established
            and self.listing_history_established
            and self.delisted_coverage_established
            and self.provenance_known
        )

    @property
    def has_meaningful_history(self) -> bool:
        return any(
            (
                self.historical_population_verified,
                self.historical_membership_established,
                self.membership_availability_established,
                self.symbol_history_established,
                self.listing_history_established,
                self.delisted_coverage_established,
                self.provenance_known,
            )
        )

    def to_dict(
        self,
        requested_start: Optional[date] = None,
        requested_end: Optional[date] = None,
    ) -> Dict[str, Any]:
        return {
            "universe_code": self.universe_code,
            "provider_name": self.provider_name,
            "coverage_start": (
                self.coverage_start.isoformat() if self.coverage_start else None
            ),
            "coverage_end": self.coverage_end.isoformat() if self.coverage_end else None,
            "historical_population_verified": self.historical_population_verified,
            "historical_membership_established": self.historical_membership_established,
            "membership_availability_established": self.membership_availability_established,
            "symbol_history_established": self.symbol_history_established,
            "listing_history_established": self.listing_history_established,
            "delisted_coverage_established": self.delisted_coverage_established,
            "provenance_known": self.provenance_known,
            "source": self.source,
            "warnings": list(self.warnings),
            "complete_for_requested_period": self.complete_for_requested_period(
                requested_start,
                requested_end,
            ),
        }


@dataclass(frozen=True)
class HistoricalUniverseMember:
    """A security that was a tradable member on the requested date."""

    security_id: int
    ticker: str
    exchange: Optional[str]
    display_name: Optional[str]
    membership_valid_from: date
    membership_valid_to: Optional[date]
    membership_source: str
    membership_available_at: Optional[datetime]
