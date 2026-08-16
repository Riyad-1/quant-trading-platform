"""In-memory paper-trading API backed by the recovered trading engine."""

from datetime import date
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services.paper_trading.engine import OrderSide, OrderType, PaperTradingEngine


router = APIRouter(prefix="/paper", tags=["paper-trading"])
_engine = PaperTradingEngine()


class ResetRequest(BaseModel):
    initial_capital: float = Field(default=100_000, ge=1_000, le=100_000_000)


class PriceRequest(BaseModel):
    ticker: str = Field(min_length=1, max_length=12)
    price: float = Field(gt=0)
    sector: str = Field(default="Unknown", max_length=80)


class OrderRequest(PriceRequest):
    side: Literal["buy", "sell"]
    quantity: int = Field(gt=0, le=1_000_000)
    order_type: Literal["market", "limit", "stop"] = "market"
    limit_price: float | None = Field(default=None, gt=0)
    stop_price: float | None = Field(default=None, gt=0)


@router.get("/summary")
async def get_summary() -> dict:
    return {
        **_engine.get_portfolio_summary(),
        "persistence": "in-memory",
        "notice": "Paper state resets whenever the API process restarts.",
    }


@router.get("/performance")
async def get_performance() -> dict:
    return _engine.get_performance_metrics()


@router.post("/reset")
async def reset_portfolio(request: ResetRequest) -> dict:
    global _engine
    _engine = PaperTradingEngine(initial_capital=request.initial_capital)
    return await get_summary()


@router.post("/price")
async def update_price(request: PriceRequest) -> dict:
    ticker = request.ticker.strip().upper()
    _engine.set_current_price(ticker, request.price)
    _engine.set_sector_mapping(ticker, request.sector.strip() or "Unknown")
    return {"ticker": ticker, "price": request.price, "summary": _engine.get_portfolio_summary()}


@router.post("/orders")
async def submit_order(request: OrderRequest) -> dict:
    ticker = request.ticker.strip().upper()
    _engine.set_current_price(ticker, request.price)
    _engine.set_sector_mapping(ticker, request.sector.strip() or "Unknown")

    if request.order_type == "limit" and request.limit_price is None:
        raise HTTPException(status_code=400, detail="limit_price is required for limit orders")
    if request.order_type == "stop" and request.stop_price is None:
        raise HTTPException(status_code=400, detail="stop_price is required for stop orders")

    order = _engine.submit_order(
        ticker=ticker,
        side=OrderSide(request.side),
        quantity=request.quantity,
        order_type=OrderType(request.order_type),
        limit_price=request.limit_price,
        stop_price=request.stop_price,
    )
    return {"order": order.to_dict(), "summary": _engine.get_portfolio_summary()}


@router.post("/snapshot")
async def take_snapshot() -> dict:
    snapshot = _engine.take_snapshot(date.today())
    return {"snapshot": snapshot.to_dict(), "performance": _engine.get_performance_metrics()}
