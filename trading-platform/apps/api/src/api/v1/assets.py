"""Asset management endpoints."""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from apps.api.src.core.database import get_db
from apps.api.src.db.models import Asset
from apps.api.src.db.schemas import (
    AssetResponse,
    AssetCreate,
    AssetUpdate,
    PriceDailyResponse
)

router = APIRouter()


@router.get("", response_model=List[AssetResponse])
async def list_assets(
    skip: int = 0,
    limit: int = 100,
    sector: Optional[str] = None,
    industry: Optional[str] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """List all assets with optional filtering."""
    query = db.query(Asset)

    if sector:
        query = query.filter(Asset.sector == sector)
    if industry:
        query = query.filter(Asset.industry == industry)
    if status:
        query = query.filter(Asset.status == status)

    assets = query.offset(skip).limit(limit).all()
    return assets


@router.get("/{ticker}", response_model=AssetResponse)
async def get_asset(ticker: str, db: Session = Depends(get_db)):
    """Get a specific asset by ticker."""
    asset = db.query(Asset).filter(Asset.ticker == ticker).first()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    return asset


@router.post("", response_model=AssetResponse)
async def create_asset(asset_data: AssetCreate, db: Session = Depends(get_db)):
    """Create a new asset."""
    # Check if ticker already exists
    existing = db.query(Asset).filter(Asset.ticker == asset_data.ticker).first()
    if existing:
        raise HTTPException(status_code=400, detail="Ticker already exists")

    asset = Asset(**asset_data.model_dump())
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return asset


@router.put("/{ticker}", response_model=AssetResponse)
async def update_asset(ticker: str, asset_data: AssetUpdate, db: Session = Depends(get_db)):
    """Update an existing asset."""
    asset = db.query(Asset).filter(Asset.ticker == ticker).first()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")

    update_data = asset_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(asset, field, value)

    db.commit()
    db.refresh(asset)
    return asset


@router.delete("/{ticker}")
async def delete_asset(ticker: str, db: Session = Depends(get_db)):
    """Delete an asset."""
    asset = db.query(Asset).filter(Asset.ticker == ticker).first()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")

    db.delete(asset)
    db.commit()
    return {"message": f"Asset {ticker} deleted"}


@router.get("/{ticker}/prices", response_model=List[PriceDailyResponse])
async def get_asset_prices(
    ticker: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """Get historical prices for an asset."""
    from apps.api.src.db.models import PriceDaily
    from datetime import datetime

    asset = db.query(Asset).filter(Asset.ticker == ticker).first()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")

    query = db.query(PriceDaily).filter(PriceDaily.asset_id == asset.id)

    if start_date:
        query = query.filter(PriceDaily.time >= start_date)
    if end_date:
        query = query.filter(PriceDaily.time <= end_date)

    prices = query.order_by(PriceDaily.time.desc()).limit(limit).all()
    return prices
