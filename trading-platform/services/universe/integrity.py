"""Fail-closed survivorship and point-in-time integrity classification."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional

from services.data.capabilities import CapabilitySupport, ProviderCapabilities


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
            "warnings": list(self.warnings),
            "can_qualify_strategy": self.can_qualify_strategy,
        }


def evaluate_research_integrity(
    capabilities: ProviderCapabilities,
    provider_name: str,
    universe_code: Optional[str],
    *,
    uses_current_constituents: bool = False,
) -> ResearchDataIntegrity:
    """Classify configured capability facts without assuming unknown support."""

    historical_membership = capabilities.historical_universe_membership.is_supported
    delisted_coverage = capabilities.delisted_securities.is_supported
    symbol_history = capabilities.symbol_history.is_supported
    listing_history = capabilities.listing_history.is_supported

    required = (
        capabilities.historical_universe_membership,
        capabilities.delisted_securities,
        capabilities.symbol_history,
        capabilities.listing_history,
    )

    if uses_current_constituents:
        status = SurvivorshipIntegrity.CURRENT_CONSTITUENTS_ONLY
    elif all(value is CapabilitySupport.SUPPORTED for value in required):
        status = SurvivorshipIntegrity.POINT_IN_TIME
    elif historical_membership:
        status = SurvivorshipIntegrity.PARTIAL_HISTORY
    else:
        status = SurvivorshipIntegrity.UNKNOWN

    warnings: List[str] = []
    if uses_current_constituents:
        warnings.append("Research universe uses current constituents or configured current symbols.")
    if not historical_membership:
        warnings.append("Historical universe membership unavailable.")
    if not delisted_coverage:
        warnings.append("Delisted-security completeness is not established.")
    if not symbol_history:
        warnings.append("Historical symbol mapping is unavailable.")
    if not listing_history:
        warnings.append("Historical listing/tradability coverage is unavailable.")
    if status is not SurvivorshipIntegrity.POINT_IN_TIME:
        warnings.extend(
            [
                "Results may contain survivorship bias.",
                "RESEARCH ONLY.",
            ]
        )

    point_in_time = status is SurvivorshipIntegrity.POINT_IN_TIME
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
    )
