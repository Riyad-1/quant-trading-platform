"""Database session management for the API."""
from sqlalchemy.orm import scoped_session

from apps.api.src.core.database import SessionLocal


db_session = scoped_session(SessionLocal)

def get_db():
    """Dependency for FastAPI to get database session."""
    db = db_session()
    try:
        yield db
    finally:
        db.close()

def get_db_session():
    """Yield a database session for service and worker callers."""
    db = db_session()
    try:
        yield db
    finally:
        db.close()
