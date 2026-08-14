"""Features package initialization."""

from .engine import FeatureEngine

# Only import service when database is available
try:
    from .service import FeatureService
    __all__ = ["FeatureEngine", "FeatureService"]
except ImportError:
    __all__ = ["FeatureEngine"]