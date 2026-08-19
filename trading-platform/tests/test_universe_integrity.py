"""Stage C point-in-time universe and survivorship-control invariants."""

from datetime import date, datetime

import polars as pl
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from apps.api.src.db.models import (
    CorporateAction,
    HistoricalUniverseCoverageRecord,
    Security,
    SecurityStatusHistory,
    SecuritySymbol,
    UniverseDefinition,
    UniverseMembership,
)
from services.backtesting.engine import BacktestEngine
from services.backtesting.strategy import Strategy, StrategyConfig
from services.data.capabilities import CapabilitySupport, ProviderCapabilities
from services.data.providers.mock_provider import MockMarketDataProvider
from services.data.providers.openbb_provider import OpenBBMarketDataProvider
from services.data.providers.yfinance_provider import YFinanceMarketDataProvider
from services.universe.integrity import (
    SurvivorshipIntegrity,
    evaluate_research_integrity,
)
from services.universe.models import HistoricalUniverseCoverage
from services.universe.service import (
    HistoricalDataConflictError,
    HistoricalUniverseService,
)


STAGE_C_TABLES = [
    Security.__table__,
    SecuritySymbol.__table__,
    SecurityStatusHistory.__table__,
    UniverseDefinition.__table__,
    HistoricalUniverseCoverageRecord.__table__,
    UniverseMembership.__table__,
    CorporateAction.__table__,
]


@pytest.fixture()
def session():
    engine = create_engine("sqlite:///:memory:")
    for table in STAGE_C_TABLES:
        table.create(engine)
    factory = sessionmaker(bind=engine)
    db = factory()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture()
def universe_fixture(session):
    service = HistoricalUniverseService(session)
    universe = UniverseDefinition(
        code="SYNTHETIC_US",
        name="Synthetic test universe",
        source="synthetic_test_fixture",
    )
    aaa = Security(display_name="Synthetic AAA", current_status="DELISTED")
    bbb = Security(display_name="Synthetic BBB", current_status="ACTIVE")
    session.add_all([universe, aaa, bbb])
    session.flush()

    service.add_symbol(aaa.id, "AAA", date(2010, 1, 1), date(2020, 1, 1), "synthetic")
    service.add_status(aaa.id, "ACTIVE", date(2010, 1, 1), date(2019, 1, 1), "synthetic")
    service.add_status(aaa.id, "DELISTED", date(2019, 1, 1), None, "synthetic")
    service.add_membership(
        universe.id,
        aaa.id,
        date(2015, 1, 1),
        date(2020, 1, 1),
        "synthetic",
    )

    service.add_symbol(bbb.id, "BBB", date(2020, 1, 1), None, "synthetic")
    service.add_status(bbb.id, "ACTIVE", date(2020, 1, 1), None, "synthetic")
    service.add_membership(universe.id, bbb.id, date(2020, 1, 1), None, "synthetic")
    return service, universe, aaa, bbb


def complete_capabilities(**overrides) -> ProviderCapabilities:
    values = {
        "historical_prices": CapabilitySupport.SUPPORTED,
        "delisted_securities": CapabilitySupport.SUPPORTED,
        "historical_universe_membership": CapabilitySupport.SUPPORTED,
        "symbol_history": CapabilitySupport.SUPPORTED,
        "listing_history": CapabilitySupport.SUPPORTED,
        "corporate_actions": CapabilitySupport.SUPPORTED,
        "point_in_time_fundamentals": CapabilitySupport.UNKNOWN,
        "historical_news": CapabilitySupport.UNKNOWN,
        "news_available_timestamp": CapabilitySupport.UNKNOWN,
    }
    values.update(overrides)
    return ProviderCapabilities(**values)


def complete_coverage(**overrides) -> HistoricalUniverseCoverage:
    values = {
        "universe_code": "SYNTHETIC_US",
        "provider_name": "synthetic",
        "coverage_start": date(2010, 1, 1),
        "coverage_end": date(2024, 12, 31),
        "historical_population_verified": True,
        "historical_membership_established": True,
        "membership_availability_established": True,
        "symbol_history_established": True,
        "listing_history_established": True,
        "delisted_coverage_established": True,
        "provenance_known": True,
        "source": "synthetic_test_fixture",
    }
    values.update(overrides)
    return HistoricalUniverseCoverage(**values)


def test_historical_membership_returns_only_valid_member(universe_fixture):
    service, _, aaa, _ = universe_fixture

    members = service.get_universe_as_of("SYNTHETIC_US", date(2018, 1, 1))

    assert [(member.security_id, member.ticker) for member in members] == [(aaa.id, "AAA")]


def test_future_member_cannot_leak_backward(universe_fixture):
    service, _, _, bbb = universe_fixture

    security_ids = {
        member.security_id
        for member in service.get_universe_as_of("SYNTHETIC_US", date(2018, 1, 1))
    }

    assert bbb.id not in security_ids


def test_former_member_remains_historically_visible(universe_fixture):
    service, _, aaa, _ = universe_fixture

    security_ids = {
        member.security_id
        for member in service.get_universe_as_of("SYNTHETIC_US", date(2018, 6, 1))
    }

    assert aaa.id in security_ids


def test_delisted_security_is_tradable_only_during_active_history(universe_fixture):
    service, _, aaa, _ = universe_fixture

    assert service.is_security_tradable_as_of(aaa.id, date(2018, 1, 1)) is True
    assert service.is_security_tradable_as_of(aaa.id, date(2020, 1, 1)) is False


def test_ticker_change_preserves_immutable_security_id(session):
    service = HistoricalUniverseService(session)
    security = Security(display_name="Renamed company", current_status="ACTIVE")
    session.add(security)
    session.flush()
    service.add_symbol(security.id, "OLD", date(2010, 1, 1), date(2018, 1, 1), "synthetic")
    service.add_symbol(security.id, "NEW", date(2018, 1, 1), None, "synthetic")

    old = service.resolve_security_as_of("OLD", date(2017, 12, 31))
    new = service.resolve_security_as_of("NEW", date(2018, 1, 1))

    assert old is not None and new is not None
    assert old.id == new.id == security.id
    assert service.get_symbol_as_of(security.id, date(2017, 12, 31)).ticker == "OLD"
    assert service.get_symbol_as_of(security.id, date(2018, 1, 1)).ticker == "NEW"


def test_ticker_reuse_resolves_different_securities_by_date(session):
    service = HistoricalUniverseService(session)
    first = Security(display_name="First reuse", current_status="DELISTED")
    second = Security(display_name="Second reuse", current_status="ACTIVE")
    session.add_all([first, second])
    session.flush()
    service.add_symbol(first.id, "REUSE", date(2000, 1, 1), date(2010, 1, 1), "synthetic")
    service.add_symbol(second.id, "REUSE", date(2010, 1, 1), None, "synthetic")

    assert service.resolve_security_as_of("REUSE", date(2009, 12, 31)).id == first.id
    assert service.resolve_security_as_of("REUSE", date(2010, 1, 1)).id == second.id


def test_half_open_interval_includes_start_and_excludes_end(universe_fixture):
    service, _, aaa, bbb = universe_fixture

    transition = service.get_universe_as_of("SYNTHETIC_US", date(2020, 1, 1))

    assert service.get_symbol_as_of(aaa.id, date(2010, 1, 1)).ticker == "AAA"
    assert service.get_symbol_as_of(aaa.id, date(2019, 12, 31)).ticker == "AAA"
    assert service.get_symbol_as_of(aaa.id, date(2020, 1, 1)) is None
    assert all(member.security_id != aaa.id for member in transition)
    assert [member.security_id for member in transition] == [bbb.id]


def availability_membership_fixture(session, available_at):
    service = HistoricalUniverseService(session)
    universe = UniverseDefinition(
        code="AVAILABILITY_TEST",
        name="Membership availability test",
        source="synthetic_test_fixture",
    )
    security = Security(display_name="Synthetic AAA", current_status="ACTIVE")
    session.add_all([universe, security])
    session.flush()
    service.add_symbol(security.id, "AAA", date(2010, 1, 1), None, "synthetic")
    service.add_status(security.id, "ACTIVE", date(2010, 1, 1), None, "synthetic")
    service.add_membership(
        universe.id,
        security.id,
        date(2020, 1, 1),
        None,
        "synthetic",
        available_at=available_at,
    )
    return service


def test_effective_membership_not_yet_known_is_excluded_from_pit_query(session):
    service = availability_membership_fixture(
        session,
        datetime(2020, 1, 5),
    )

    reference = service.get_universe_as_of("AVAILABILITY_TEST", date(2020, 1, 2))
    point_in_time = service.get_point_in_time_universe(
        "AVAILABILITY_TEST",
        date(2020, 1, 2),
        datetime(2020, 1, 2),
    )

    assert [member.ticker for member in reference] == ["AAA"]
    assert point_in_time == []


def test_membership_becomes_usable_when_availability_is_reached(session):
    service = availability_membership_fixture(
        session,
        datetime(2020, 1, 5),
    )

    point_in_time = service.get_point_in_time_universe(
        "AVAILABILITY_TEST",
        date(2020, 1, 2),
        datetime(2020, 1, 5),
    )

    assert [member.ticker for member in point_in_time] == ["AAA"]
    assert point_in_time[0].membership_available_at == datetime(2020, 1, 5)


def test_null_membership_availability_is_reference_only(session):
    service = availability_membership_fixture(session, None)

    reference = service.get_universe_as_of("AVAILABILITY_TEST", date(2020, 1, 2))
    point_in_time = service.get_point_in_time_universe(
        "AVAILABILITY_TEST",
        date(2020, 1, 2),
        datetime(2020, 1, 10),
    )

    assert [member.ticker for member in reference] == ["AAA"]
    assert point_in_time == []


def test_provider_without_historical_membership_is_not_point_in_time():
    integrity = evaluate_research_integrity(
        complete_capabilities(
            historical_universe_membership=CapabilitySupport.UNSUPPORTED
        ),
        "synthetic",
        "SYNTHETIC_US",
        coverage=complete_coverage(),
        requested_start=date(2015, 1, 1),
        requested_end=date(2024, 12, 31),
    )

    assert integrity.survivorship_status is not SurvivorshipIntegrity.POINT_IN_TIME
    assert integrity.can_qualify_strategy is False


def test_capability_alone_cannot_qualify_without_dataset_evidence():
    integrity = evaluate_research_integrity(
        complete_capabilities(),
        "synthetic",
        "SYNTHETIC_US",
        requested_start=date(2015, 1, 1),
        requested_end=date(2024, 12, 31),
    )

    assert integrity.survivorship_status is not SurvivorshipIntegrity.POINT_IN_TIME
    assert integrity.can_qualify_strategy is False
    assert "Historical universe coverage evidence was not supplied." in integrity.warnings


def test_verified_synthetic_universe_can_qualify():
    integrity = evaluate_research_integrity(
        complete_capabilities(),
        "synthetic",
        "SYNTHETIC_US",
        coverage=complete_coverage(),
        requested_start=date(2015, 1, 1),
        requested_end=date(2024, 12, 31),
    )

    assert integrity.survivorship_status is SurvivorshipIntegrity.POINT_IN_TIME
    assert integrity.can_qualify_strategy is True


def test_coverage_period_too_short_cannot_qualify():
    integrity = evaluate_research_integrity(
        complete_capabilities(),
        "synthetic",
        "SYNTHETIC_US",
        coverage=complete_coverage(coverage_start=date(2020, 1, 1)),
        requested_start=date(2015, 1, 1),
        requested_end=date(2024, 12, 31),
    )

    assert integrity.survivorship_status is SurvivorshipIntegrity.PARTIAL_HISTORY
    assert integrity.can_qualify_strategy is False
    assert "Dataset coverage does not span the requested research period." in integrity.warnings


def test_unverified_empty_dataset_cannot_qualify():
    coverage = complete_coverage(
        historical_population_verified=False,
        historical_membership_established=False,
    )
    integrity = evaluate_research_integrity(
        complete_capabilities(),
        "synthetic",
        "SYNTHETIC_US",
        coverage=coverage,
        requested_start=date(2015, 1, 1),
        requested_end=date(2024, 12, 31),
    )

    assert integrity.survivorship_status is SurvivorshipIntegrity.PARTIAL_HISTORY
    assert integrity.can_qualify_strategy is False
    assert integrity.historical_universe_available is False


def test_provider_without_delisted_coverage_is_partial_not_qualified():
    integrity = evaluate_research_integrity(
        complete_capabilities(delisted_securities=CapabilitySupport.UNSUPPORTED),
        "synthetic",
        "SYNTHETIC_US",
        coverage=complete_coverage(),
        requested_start=date(2015, 1, 1),
        requested_end=date(2024, 12, 31),
    )

    assert integrity.survivorship_status is SurvivorshipIntegrity.PARTIAL_HISTORY
    assert integrity.delisted_security_coverage is False
    assert integrity.can_qualify_strategy is False


def test_unknown_capability_is_never_interpreted_as_supported():
    integrity = evaluate_research_integrity(
        complete_capabilities(symbol_history=CapabilitySupport.UNKNOWN),
        "synthetic",
        "SYNTHETIC_US",
        coverage=complete_coverage(),
        requested_start=date(2015, 1, 1),
        requested_end=date(2024, 12, 31),
    )

    assert integrity.survivorship_status is SurvivorshipIntegrity.PARTIAL_HISTORY
    assert integrity.symbol_history_available is False
    assert integrity.can_qualify_strategy is False


def test_current_constituent_universe_is_explicitly_classified():
    integrity = evaluate_research_integrity(
        complete_capabilities(),
        "synthetic",
        "CURRENT_SCANNER_UNIVERSE",
        uses_current_constituents=True,
    )

    assert integrity.survivorship_status is SurvivorshipIntegrity.CURRENT_CONSTITUENTS_ONLY
    assert integrity.can_qualify_strategy is False
    assert "RESEARCH ONLY." in integrity.warnings


class NoSignalStrategy(Strategy):
    def __init__(self):
        super().__init__(
            StrategyConfig(
                name="No signal",
                description="Stage C metadata fixture",
                min_price=0,
                min_volume=0,
            )
        )

    def get_required_features(self):
        return []

    def generate_signals(self, data: pl.DataFrame) -> pl.DataFrame:
        return data.with_columns(
            pl.lit(0).alias("signal"),
            pl.lit(0.0).alias("score"),
            pl.col("timestamp").alias("feature_timestamp"),
            pl.lit(datetime(2020, 1, 1, 21)).alias("signal_timestamp"),
            pl.lit(datetime(2020, 1, 1, 21)).alias("decision_timestamp"),
            pl.lit(datetime(2020, 1, 1, 21)).alias("available_at"),
        )


def no_signal_price_data() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "timestamp": [date(2020, 1, 2), date(2020, 1, 3)],
            "ticker": ["AAA", "AAA"],
            "open": [100.0, 101.0],
            "high": [101.0, 102.0],
            "low": [99.0, 100.0],
            "close": [100.0, 101.0],
            "volume": [1_000_000, 1_000_000],
        }
    )


def test_backtest_without_integrity_metadata_fails_closed():
    result = BacktestEngine().run(no_signal_price_data(), NoSignalStrategy())
    payload = result.to_dict()

    assert result.research_integrity is not None
    assert payload["research_integrity"]["survivorship_status"] == "UNKNOWN"
    assert payload["research_integrity"]["can_qualify_strategy"] is False
    assert "RESEARCH ONLY." in payload["research_integrity"]["warnings"]


def test_backtest_result_exposes_supplied_research_integrity():
    integrity = evaluate_research_integrity(
        complete_capabilities(),
        "synthetic",
        "SYNTHETIC_US",
        coverage=complete_coverage(),
        requested_start=date(2015, 1, 1),
        requested_end=date(2024, 12, 31),
    )
    result = BacktestEngine().run(
        no_signal_price_data(),
        NoSignalStrategy(),
        research_integrity=integrity,
    )
    payload = result.to_dict()

    assert result.research_integrity is integrity
    assert payload["research_integrity"]["universe_code"] == "SYNTHETIC_US"
    assert payload["research_integrity"]["survivorship_status"] == "POINT_IN_TIME"
    assert payload["research_integrity"]["can_qualify_strategy"] is True


def test_empty_historical_universe_does_not_fall_back_to_current(universe_fixture):
    service, _, _, _ = universe_fixture

    assert service.get_universe_as_of("SYNTHETIC_US", date(1990, 1, 1)) == []
    assert service.get_universe_as_of("MISSING_UNIVERSE", date(2024, 1, 1)) == []


def test_later_delisted_member_changes_historical_universe_size(session):
    service = HistoricalUniverseService(session)
    universe = UniverseDefinition(code="SIZE_TEST", name="Size test", source="synthetic")
    survivor = Security(display_name="Survivor", current_status="ACTIVE")
    delisted = Security(display_name="Later delisted", current_status="DELISTED")
    session.add_all([universe, survivor, delisted])
    session.flush()
    for security, ticker in ((survivor, "LIVE"), (delisted, "GONE")):
        service.add_symbol(security.id, ticker, date(2010, 1, 1), None, "synthetic")
        service.add_membership(universe.id, security.id, date(2010, 1, 1), None, "synthetic")
    service.add_status(survivor.id, "ACTIVE", date(2010, 1, 1), None, "synthetic")
    service.add_status(delisted.id, "ACTIVE", date(2010, 1, 1), date(2019, 1, 1), "synthetic")
    service.add_status(delisted.id, "DELISTED", date(2019, 1, 1), None, "synthetic")

    assert len(service.get_universe_as_of("SIZE_TEST", date(2018, 1, 1))) == 2
    assert len(service.get_universe_as_of("SIZE_TEST", date(2020, 1, 1))) == 1


def test_future_symbol_does_not_resolve_before_valid_from(session):
    service = HistoricalUniverseService(session)
    security = Security(display_name="Future symbol", current_status="ACTIVE")
    session.add(security)
    session.flush()
    service.add_symbol(security.id, "FUTR", date(2030, 1, 1), None, "synthetic")

    assert service.resolve_security_as_of("FUTR", date(2029, 12, 31)) is None
    assert service.get_symbol_as_of(security.id, date(2029, 12, 31)) is None


def test_overlapping_effective_ranges_are_rejected(session):
    service = HistoricalUniverseService(session)
    security = Security(display_name="Overlap", current_status="ACTIVE")
    session.add(security)
    session.flush()
    service.add_symbol(security.id, "ONE", date(2010, 1, 1), date(2020, 1, 1), "synthetic")

    with pytest.raises(HistoricalDataConflictError, match="must not overlap"):
        service.add_symbol(security.id, "TWO", date(2019, 1, 1), None, "synthetic")


def test_missing_status_history_fails_tradability_closed(session):
    service = HistoricalUniverseService(session)
    security = Security(display_name="Unknown history", current_status="ACTIVE")
    session.add(security)
    session.flush()

    assert service.is_security_tradable_as_of(security.id, date(2020, 1, 1)) is False


def test_mock_provider_capabilities_can_be_explicitly_configured(session):
    provider = MockMarketDataProvider(
        num_stocks=1,
        seed=1,
        capabilities=complete_capabilities(),
    )
    universe = UniverseDefinition(
        code="SYNTHETIC_US",
        name="Synthetic coverage universe",
        source="synthetic_test_fixture",
    )
    session.add(universe)
    session.flush()
    service = HistoricalUniverseService(session)
    service.add_coverage(
        complete_coverage(provider_name="MockMarketDataProvider")
    )

    integrity = service.get_integrity_status(
        provider,
        "SYNTHETIC_US",
        requested_start=date(2015, 1, 1),
        requested_end=date(2024, 12, 31),
    )

    assert integrity.survivorship_status is SurvivorshipIntegrity.POINT_IN_TIME
    assert integrity.can_qualify_strategy is True


@pytest.mark.parametrize(
    "provider_class",
    [OpenBBMarketDataProvider, YFinanceMarketDataProvider],
)
def test_real_price_integrations_do_not_claim_survivorship_safety(provider_class):
    capabilities = provider_class.capabilities
    integrity = evaluate_research_integrity(
        capabilities,
        provider_class.__name__,
        "HISTORICAL_RESEARCH",
    )

    assert capabilities.historical_prices is CapabilitySupport.SUPPORTED
    assert capabilities.historical_universe_membership is CapabilitySupport.UNSUPPORTED
    assert capabilities.delisted_securities is CapabilitySupport.UNSUPPORTED
    assert integrity.survivorship_status is not SurvivorshipIntegrity.POINT_IN_TIME
    assert integrity.can_qualify_strategy is False


def test_corporate_action_foundation_preserves_provenance(session):
    security = Security(display_name="Action fixture", current_status="ACTIVE")
    session.add(security)
    session.flush()
    action = CorporateAction(
        security_id=security.id,
        action_type="SYMBOL_CHANGE",
        event_date=date(2019, 12, 1),
        effective_date=date(2020, 1, 1),
        available_at=datetime(2019, 12, 1, 14, 30),
        source="synthetic_test_fixture",
        source_event_id="synthetic-1",
        action_metadata={"old": "OLD", "new": "NEW"},
    )
    session.add(action)
    session.flush()

    restored = session.get(CorporateAction, action.id)
    assert restored.source == "synthetic_test_fixture"
    assert restored.available_at == datetime(2019, 12, 1, 14, 30)
    assert restored.action_metadata == {"old": "OLD", "new": "NEW"}
