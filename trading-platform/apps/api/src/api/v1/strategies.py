"""Strategy management endpoints."""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from apps.api.src.core.database import get_db
from apps.api.src.db.models import Strategy, Signal
from apps.api.src.db.schemas import (
    StrategyResponse,
    StrategyCreate,
    StrategyUpdate,
    SignalResponse
)

router = APIRouter()


@router.get("", response_model=List[StrategyResponse])
async def list_strategies(
    skip: int = 0,
    limit: int = 100,
    active_only: bool = True,
    db: Session = Depends(get_db)
):
    """List all trading strategies."""
    query = db.query(Strategy)

    if active_only:
        query = query.filter(Strategy.is_active == True)

    strategies = query.offset(skip).limit(limit).all()
    return strategies


@router.get("/{strategy_id}", response_model=StrategyResponse)
async def get_strategy(strategy_id: int, db: Session = Depends(get_db)):
    """Get a specific strategy."""
    strategy = db.query(Strategy).filter(Strategy.id == strategy_id).first()
    if not strategy:
        raise HTTPException(status_code=404, detail="Strategy not found")
    return strategy


@router.post("", response_model=StrategyResponse)
async def create_strategy(
    strategy_data: StrategyCreate,
    db: Session = Depends(get_db)
):
    """Create a new trading strategy."""
    # Check if name already exists
    existing = db.query(Strategy).filter(
        Strategy.name == strategy_data.name
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Strategy name already exists")

    strategy = Strategy(**strategy_data.model_dump())
    db.add(strategy)
    db.commit()
    db.refresh(strategy)
    return strategy


@router.put("/{strategy_id}", response_model=StrategyResponse)
async def update_strategy(
    strategy_id: int,
    strategy_data: StrategyUpdate,
    db: Session = Depends(get_db)
):
    """Update an existing strategy."""
    strategy = db.query(Strategy).filter(Strategy.id == strategy_id).first()
    if not strategy:
        raise HTTPException(status_code=404, detail="Strategy not found")

    update_data = strategy_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(strategy, field, value)

    db.commit()
    db.refresh(strategy)
    return strategy


@router.delete("/{strategy_id}")
async def delete_strategy(strategy_id: int, db: Session = Depends(get_db)):
    """Delete a strategy."""
    strategy = db.query(Strategy).filter(Strategy.id == strategy_id).first()
    if not strategy:
        raise HTTPException(status_code=404, detail="Strategy not found")

    db.delete(strategy)
    db.commit()
    return {"message": f"Strategy {strategy.name} deleted"}


@router.get("/{strategy_id}/signals", response_model=List[SignalResponse])
async def get_strategy_signals(
    strategy_id: int,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """Get recent signals from a strategy."""
    strategy = db.query(Strategy).filter(Strategy.id == strategy_id).first()
    if not strategy:
        raise HTTPException(status_code=404, detail="Strategy not found")

    signals = db.query(Signal).filter(
        Signal.strategy_id == strategy_id
    ).order_by(Signal.generated_at.desc()).limit(limit).all()

    return signals
