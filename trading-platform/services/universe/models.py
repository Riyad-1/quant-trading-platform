"""Domain models for point-in-time security and universe queries."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Optional


class SecurityLifecycleStatus(str, Enum):
    ACTIVE = "ACTIVE"
    DELISTED = "DELISTED"
    SUSPENDED = "SUSPENDED"
    ACQUIRED = "ACQUIRED"
    BANKRUPT = "BANKRUPT"
    UNKNOWN = "UNKNOWN"


TRADABLE_STATUSES = frozenset({SecurityLifecycleStatus.ACTIVE.value})


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
