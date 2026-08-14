"""Health check endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy import text
from apps.api.src.core.database import get_db
from sqlalchemy.orm import Session

router = APIRouter()


@router.get("/health")
async def health_status(db: Session = Depends(get_db)):
    """Check API and database health."""
    try:
        # Test database connection
        db.execute(text("SELECT 1"))
        db_status = "connected"
    except Exception as e:
        db_status = f"error: {str(e)}"

    return {
        "status": "healthy",
        "database": db_status,
        "service": "quant-trading-api"
    }