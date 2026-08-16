"""Model registry and machine-learning readiness endpoints."""

from fastapi import APIRouter, HTTPException

from services.ml.ml_engine import ModelType
from services.ml.model_registry import ModelRegistry


router = APIRouter(prefix="/ml", tags=["machine-learning"])


def _registry() -> ModelRegistry:
    return ModelRegistry(storage_path=".cache/model-registry")


@router.get("/status")
async def get_ml_status() -> dict:
    registry = _registry()
    payload = registry.to_dict()
    return {
        "status": "ready" if payload["total_models"] else "awaiting_training_data",
        "supported_models": [model.value for model in ModelType],
        "training_mode": "walk-forward validation",
        "registered_models": payload["total_models"],
        "active_models": payload["active_models"],
        "notice": "No prediction is produced until a model has been trained and registered.",
    }


@router.get("/models")
async def list_models() -> dict:
    return _registry().to_dict()


@router.post("/models/{model_id}/activate")
async def activate_model(model_id: str) -> dict:
    registry = _registry()
    if not registry.activate_model(model_id):
        raise HTTPException(status_code=404, detail="Model not found")
    model = registry.get_model(model_id)
    return {"activated": model_id, "model": model.to_dict() if model else None}
