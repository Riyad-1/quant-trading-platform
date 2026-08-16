"""Regression tests for the service-to-HTTP feature adapters."""

from datetime import date

import numpy as np
import pandas as pd
import pytest

from apps.api.src.api.v1 import backtest, ml, paper
from services.ml.model_registry import ModelRegistry


def test_spy_trend_backtest_uses_lagged_signal(monkeypatch):
    index = pd.bdate_range("2020-01-01", periods=900)
    close = np.linspace(100, 220, len(index)) + np.sin(np.arange(len(index)) / 20) * 5
    fixture = pd.DataFrame(
        {
            "Open": close * 0.999,
            "High": close * 1.01,
            "Low": close * 0.99,
            "Close": close,
            "Volume": 1_000_000,
        },
        index=index,
    )
    monkeypatch.setattr(backtest.yf, "download", lambda *args, **kwargs: fixture)

    result = backtest._run_spy_trend(
        date(2021, 1, 1), date(2023, 5, 1), 100_000, 200, 5, 5
    )

    assert result["execution"] == "Signal after close; execute at next session open"
    assert result["equity_curve"]
    assert result["strategy"]["final_equity"] > 0
    assert 0 <= result["market_exposure"] <= 1


@pytest.mark.asyncio
async def test_paper_adapter_executes_recovered_engine_order():
    await paper.reset_portfolio(paper.ResetRequest(initial_capital=100_000))
    response = await paper.submit_order(
        paper.OrderRequest(
            ticker="SPY",
            price=500,
            sector="ETF",
            side="buy",
            quantity=10,
        )
    )

    assert response["order"]["status"] == "filled"
    assert response["summary"]["num_positions"] == 1


@pytest.mark.asyncio
async def test_ml_status_reports_empty_registry(monkeypatch, tmp_path):
    monkeypatch.setattr(ml, "_registry", lambda: ModelRegistry(str(tmp_path)))

    status = await ml.get_ml_status()

    assert status["status"] == "awaiting_training_data"
    assert status["registered_models"] == 0
    assert "lightgbm" in status["supported_models"]
