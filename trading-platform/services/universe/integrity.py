"""Fail-closed survivorship and point-in-time integrity classification."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Any, Dict, Iterable, List, Optional

from services.data.capabilities import CapabilitySupport, ProviderCapabilities

from .models import HistoricalUniverseCoverage


class SurvivorshipIntegrity(str, Enum):
    POINT_IN_TIME = "POINT_IN_TIME"
    PARTIAL_HISTORY = "PARTIAL_HISTORY"
    CURRENT_CONSTITUENTS_ONLY = "CURRENT_CONSTITUENTS_ONLY"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class ResearchDataIntegrity:
    """Serializable explanation of whether research can control survivorship bias."""

    survivorship_status: SurvivorshipIntegrity
    historical_universe_available: bool
    delisted_security_coverage: bool
    symbol_history_available: bool
    listing_history_available: bool
    point_in_time_data: bool
    provider_name: str
    universe_code: Optional[str]
    warnings: List[str]
    can_qualify_strategy: bool
    dataset_coverage: Optional[HistoricalUniverseCoverage] = None
    requested_start: Optional[date] = None
    requested_end: Optional[date] = None

    @classmethod
    def unknown(
        cls,
        provider_name: str = "UNSPECIFIED",
        universe_code: Optional[str] = None,
        *,
        warnings: Optional[Iterable[str]] = None,
    ) -> "ResearchDataIntegrity":
        messages = [
            "Research data integrity was not supplied.",
            "Survivorship control cannot be established.",
            "RESEARCH ONLY.",
        ]
        if warnings:
            messages.extend(warnings)
        return cls(
            survivorship_status=SurvivorshipIntegrity.UNKNOWN,
            historical_universe_available=False,
            delisted_security_coverage=False,
            symbol_history_available=False,
            listing_history_available=False,
            point_in_time_data=False,
            provider_name=provider_name,
            universe_code=universe_code,
            warnings=messages,
            can_qualify_strategy=False,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "survivorship_status": self.survivorship_status.value,
            "historical_universe_available": self.historical_universe_available,
            "delisted_security_coverage": self.delisted_security_coverage,
            "symbol_history_available": self.symbol_history_available,
            "listing_history_available": self.listing_history_available,
            "point_in_time_data": self.point_in_time_data,
            "provider_name": self.provider_name,
            "universe_code": self.universe_code,
            "requested_start": (
                self.requested_start.isoformat() if self.requested_start else None
            ),
            "requested_end": self.requested_end.isoformat() if self.requested_end else None,
            "dataset_coverage": (
                self.dataset_coverage.to_dict(
                    self.requested_start,
                    self.requested_end,
                )
                if self.dataset_coverage
                else None
            ),
            "warnings": list(self.warnings),
            "can_qualify_strategy": self.can_qualify_strategy,
        }


def evaluate_research_integrity(
    capabilities: ProviderCapabilities,
    provider_name: str,
    universe_code: Optional[str],
    *,
    coverage: Optional[HistoricalUniverseCoverage] = None,
    requested_start: Optional[date] = None,
    requested_end: Optional[date] = None,
    uses_current_constituents: bool = False,
) -> ResearchDataIntegrity:
    """Require provider support and explicit dataset evidence for qualification."""

    if (
        requested_start is not None
        and requested_end is not None
        and requested_end < requested_start
    ):
        raise ValueError("requested_end must be on or after requested_start")

    provider_membership = capabilities.historical_universe_membership.is_supported
    provider_delisted = capabilities.delisted_securities.is_supported
    provider_symbols = capabilities.symbol_history.is_supported
    provider_listings = capabilities.listing_history.is_supported
    provider_complete = all(
        value is CapabilitySupport.SUPPORTED
        for value in (
            capabilities.historical_universe_membership,
            capabilities.delisted_securities,
            capabilities.symbol_history,
            capabilities.listing_history,
        )
    )

    coverage_matches = bool(
        coverage is not None
        and coverage.universe_code == universe_code
        and coverage.provider_name == provider_name
    )
    period_covered = bool(
        coverage_matches
        and coverage is not None
        and coverage.covers_requested_period(requested_start, requested_end)
    )
    evidence_foundation = bool(
        period_covered
        and coverage is not None
        and coverage.historical_population_verified
        and coverage.provenance_known
    )
    historical_membership = bool(
        provider_membership
        and evidence_foundation
        and coverage is not None
        and coverage.historical_membership_established
        and coverage.membership_availability_established
    )
    delisted_coverage = bool(
        provider_delisted
        and evidence_foundation
        and coverage is not None
        and coverage.delisted_coverage_established
    )
    symbol_history = bool(
        provider_symbols
        and evidence_foundation
        and coverage is not None
        and coverage.symbol_history_established
    )
    listing_history = bool(
        provider_listings
        and evidence_foundation
        and coverage is not None
        and coverage.listing_history_established
    )
    dataset_complete = bool(
        coverage_matches
        and coverage is not None
        and coverage.complete_for_requested_period(requested_start, requested_end)
    )

    if uses_current_constituents:
        status = SurvivorshipIntegrity.CURRENT_CONSTITUENTS_ONLY
    elif provider_complete and dataset_complete:
        status = SurvivorshipIntegrity.POINT_IN_TIME
    elif coverage_matches and coverage is not None and coverage.has_meaningful_history:
        status = SurvivorshipIntegrity.PARTIAL_HISTORY
    else:
        status = SurvivorshipIntegrity.UNKNOWN

    warnings: List[str] = []
    if uses_current_constituents:
        warnings.append(
            "Research universe uses current constituents or configured current symbols."
        )

    if not provider_membership:
        warnings.append("Provider does not establish historical universe membership support.")
    if not provider_delisted:
        warnings.append("Provider does not establish delisted-security coverage.")
    if not provider_symbols:
        warnings.append("Provider does not establish historical symbol support.")
    if not provider_listings:
        warnings.append("Provider does not establish listing/tradability history support.")

    if not uses_current_constituents:
        if coverage is None:
            warnings.append("Historical universe coverage evidence was not supplied.")
        elif not coverage_matches:
            warnings.append(
                "Coverage evidence does not match the requested provider and universe."
            )
        else:
            if requested_start is None or requested_end is None:
                warnings.append("The requested research period was not supplied.")
            elif not period_covered:
                warnings.append("Dataset coverage does not span the requested research period.")
            if not coverage.historical_population_verified:
                warnings.append("Historical universe population completeness is not verified.")
            if not coverage.historical_membership_established:
                warnings.append("Historical membership completeness is not established.")
            if not coverage.membership_availability_established:
                warnings.append("Membership availability provenance is not established.")
            if not coverage.symbol_history_established:
                warnings.append("Historical symbol coverage is not established.")
            if not coverage.listing_history_established:
                warnings.append("Historical listing/tradability coverage is not established.")
            if not coverage.delisted_coverage_established:
                warnings.append("Delisted-security completeness is not established.")
            if not coverage.provenance_known:
                warnings.append("Dataset provenance is not established.")
            warnings.extend(coverage.warnings)

    point_in_time = status is SurvivorshipIntegrity.POINT_IN_TIME
    if not point_in_time:
        warnings.extend(
            [
                "Results may contain survivorship bias.",
                "RESEARCH ONLY.",
            ]
        )

    return ResearchDataIntegrity(
        survivorship_status=status,
        historical_universe_available=historical_membership,
        delisted_security_coverage=delisted_coverage,
        symbol_history_available=symbol_history,
        listing_history_available=listing_history,
        point_in_time_data=point_in_time,
        provider_name=provider_name,
        universe_code=universe_code,
        warnings=warnings,
        can_qualify_strategy=point_in_time,
        dataset_coverage=coverage if coverage_matches else None,
        requested_start=requested_start,
        requested_end=requested_end,
    )
