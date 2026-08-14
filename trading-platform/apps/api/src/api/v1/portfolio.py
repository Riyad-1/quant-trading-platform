"""Portfolio management endpoints."""

from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from apps.api.src.core.database import get_db
from apps.api.src.db.models import PaperPortfolio, PaperPosition, PortfolioSnapshot
from apps.api.src.db.schemas import (
    PaperPortfolioResponse,
    PaperPortfolioCreate,
    PaperPositionResponse,
    PortfolioSnapshotResponse,
)

router = APIRouter()


@router.get("", response_model=List[PaperPortfolioResponse])
async def list_portfolios(db: Session = Depends(get_db)):
    """List all paper portfolios."""
    return db.query(PaperPortfolio).all()


@router.get("/{portfolio_id}", response_model=PaperPortfolioResponse)
async def get_portfolio(portfolio_id: int, db: Session = Depends(get_db)):
    """Get a specific portfolio."""
    portfolio = db.query(PaperPortfolio).filter(PaperPortfolio.id == portfolio_id).first()
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    return portfolio


@router.post("", response_model=PaperPortfolioResponse)
async def create_portfolio(
    portfolio_data: PaperPortfolioCreate,
    db: Session = Depends(get_db),
):
    """Create a new paper portfolio."""
    portfolio = PaperPortfolio(**portfolio_data.model_dump())
    db.add(portfolio)
    db.commit()
    db.refresh(portfolio)
    return portfolio


@router.get("/{portfolio_id}/positions", response_model=List[PaperPositionResponse])
async def get_portfolio_positions(portfolio_id: int, db: Session = Depends(get_db)):
    """Get all positions in a portfolio."""
    portfolio = db.query(PaperPortfolio).filter(PaperPortfolio.id == portfolio_id).first()
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    return db.query(PaperPosition).filter(PaperPosition.portfolio_id == portfolio_id).all()


@router.get("/{portfolio_id}/snapshots", response_model=List[PortfolioSnapshotResponse])
async def get_portfolio_snapshots(
    portfolio_id: int,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    """Get portfolio equity curve snapshots."""
    portfolio = db.query(PaperPortfolio).filter(PaperPortfolio.id == portfolio_id).first()
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    return (
        db.query(PortfolioSnapshot)
        .filter(PortfolioSnapshot.portfolio_id == portfolio_id)
        .order_by(PortfolioSnapshot.time.desc())
        .limit(limit)
        .all()
    )
