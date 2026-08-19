"""Reusable point-in-time timing metadata for daily research data."""

from datetime import datetime, timezone
from typing import Optional

import polars as pl


DEFAULT_DAILY_AVAILABILITY_RULE = "US_EQUITY_SESSION_CLOSE_CONSERVATIVE_21_UTC"


def add_daily_point_in_time_columns(
    frame: pl.DataFrame,
    time_col: str,
    computed_at: Optional[datetime] = None,
) -> pl.DataFrame:
    """Attach conservative availability metadata to daily market-derived rows.

    Timestamps are stored as timezone-naive UTC values because the project's
    existing Polars frames are timezone-naive. Daily OHLCV is conservatively
    considered available at 21:00 UTC on its event date, covering both US
    daylight-saving and standard-time closes without making it available early.
    """
    if time_col not in frame.columns:
        raise ValueError(f"Missing time column: {time_col}")

    calculation_time = computed_at or datetime.now(timezone.utc).replace(tzinfo=None)
    if calculation_time.tzinfo is not None:
        calculation_time = calculation_time.astimezone(timezone.utc).replace(tzinfo=None)

    event_time = pl.col(time_col).cast(pl.Datetime(time_unit="us"))
    return frame.with_columns(
        event_time.alias("event_time"),
        (
            event_time.cast(pl.Date).cast(pl.Datetime(time_unit="us"))
            + pl.duration(hours=21)
        ).alias("available_at"),
        pl.lit(calculation_time).cast(pl.Datetime(time_unit="us")).alias("computed_at"),
        pl.lit(DEFAULT_DAILY_AVAILABILITY_RULE).alias("availability_rule"),
    )
