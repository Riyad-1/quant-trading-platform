"""Explicit research capabilities for configured data-provider integrations."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Dict


class CapabilitySupport(str, Enum):
    """Tri-state capability declaration; UNKNOWN never implies support."""

    SUPPORTED = "SUPPORTED"
    UNSUPPORTED = "UNSUPPORTED"
    UNKNOWN = "UNKNOWN"

    @property
    def is_supported(self) -> bool:
        return self is CapabilitySupport.SUPPORTED


@dataclass(frozen=True)
class ProviderCapabilities:
    """Capabilities implemented and verified by one configured integration."""

    historical_prices: CapabilitySupport = CapabilitySupport.UNKNOWN
    delisted_securities: CapabilitySupport = CapabilitySupport.UNKNOWN
    historical_universe_membership: CapabilitySupport = CapabilitySupport.UNKNOWN
    symbol_history: CapabilitySupport = CapabilitySupport.UNKNOWN
    listing_history: CapabilitySupport = CapabilitySupport.UNKNOWN
    corporate_actions: CapabilitySupport = CapabilitySupport.UNKNOWN
    point_in_time_fundamentals: CapabilitySupport = CapabilitySupport.UNKNOWN
    historical_news: CapabilitySupport = CapabilitySupport.UNKNOWN
    news_available_timestamp: CapabilitySupport = CapabilitySupport.UNKNOWN

    def to_dict(self) -> Dict[str, str]:
        return {name: value.value for name, value in asdict(self).items()}

    @classmethod
    def requested_symbol_prices_only(cls) -> "ProviderCapabilities":
        """Capabilities for integrations limited to prices for supplied symbols."""
        return cls(
            historical_prices=CapabilitySupport.SUPPORTED,
            delisted_securities=CapabilitySupport.UNSUPPORTED,
            historical_universe_membership=CapabilitySupport.UNSUPPORTED,
            symbol_history=CapabilitySupport.UNSUPPORTED,
            listing_history=CapabilitySupport.UNSUPPORTED,
            corporate_actions=CapabilitySupport.UNSUPPORTED,
            point_in_time_fundamentals=CapabilitySupport.UNSUPPORTED,
            historical_news=CapabilitySupport.UNSUPPORTED,
            news_available_timestamp=CapabilitySupport.UNSUPPORTED,
        )
