"""
Model Registry for tracking trained models and metadata.
"""
import json
from typing import Dict, List, Any, Optional
from datetime import datetime
from pathlib import Path
import pickle


class ModelMetadata:
    """Metadata for a trained model."""

    def __init__(
        self,
        model_id: str,
        model_type: str,
        horizon_days: int,
        trained_at: datetime,
        train_period_start: str,
        train_period_end: str,
        val_auc: float,
        val_accuracy: float,
        feature_count: int,
        model_params: Optional[Dict[str, Any]] = None,
        notes: str = ""
    ):
        self.model_id = model_id
        self.model_type = model_type
        self.horizon_days = horizon_days
        self.trained_at = trained_at
        self.train_period_start = train_period_start
        self.train_period_end = train_period_end
        self.val_auc = val_auc
        self.val_accuracy = val_accuracy
        self.feature_count = feature_count
        self.model_params = model_params or {}
        self.notes = notes
        self.is_active = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "model_id": self.model_id,
            "model_type": self.model_type,
            "horizon_days": self.horizon_days,
            "trained_at": self.trained_at.isoformat(),
            "train_period_start": self.train_period_start,
            "train_period_end": self.train_period_end,
            "val_auc": self.val_auc,
            "val_accuracy": self.val_accuracy,
            "feature_count": self.feature_count,
            "model_params": self.model_params,
            "notes": self.notes,
            "is_active": self.is_active,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ModelMetadata":
        metadata = cls(
            model_id=data["model_id"],
            model_type=data["model_type"],
            horizon_days=data["horizon_days"],
            trained_at=datetime.fromisoformat(data["trained_at"]),
            train_period_start=data["train_period_start"],
            train_period_end=data["train_period_end"],
            val_auc=data["val_auc"],
            val_accuracy=data["val_accuracy"],
            feature_count=data["feature_count"],
            model_params=data.get("model_params"),
            notes=data.get("notes", ""),
        )
        metadata.is_active = data.get("is_active", False)
        return metadata


class ModelRegistry:
    """
    Registry for tracking and managing trained models.

    Stores metadata about all trained models and allows
    selecting the best performing model for deployment.
    """

    def __init__(self, storage_path: str = "models/registry"):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.models: Dict[str, ModelMetadata] = {}
        self._load_registry()

    def _load_registry(self) -> None:
        """Load existing registry from disk."""
        registry_file = self.storage_path / "registry.json"
        if registry_file.exists():
            with open(registry_file, 'r') as f:
                data = json.load(f)
                self.models = {
                    k: ModelMetadata.from_dict(v) for k, v in data.items()
                }

    def _save_registry(self) -> None:
        """Save registry to disk."""
        registry_file = self.storage_path / "registry.json"
        data = {k: v.to_dict() for k, v in self.models.items()}
        with open(registry_file, 'w') as f:
            json.dump(data, f, indent=2)

    def register_model(
        self,
        model_id: str,
        model_type: str,
        horizon_days: int,
        val_auc: float,
        val_accuracy: float,
        feature_count: int,
        train_period_start: str,
        train_period_end: str,
        model_params: Optional[Dict[str, Any]] = None,
        notes: str = ""
    ) -> ModelMetadata:
        """Register a newly trained model."""
        metadata = ModelMetadata(
            model_id=model_id,
            model_type=model_type,
            horizon_days=horizon_days,
            trained_at=datetime.now(),
            train_period_start=train_period_start,
            train_period_end=train_period_end,
            val_auc=val_auc,
            val_accuracy=val_accuracy,
            feature_count=feature_count,
            model_params=model_params,
            notes=notes,
        )

        self.models[model_id] = metadata
        self._save_registry()

        return metadata

    def get_model(self, model_id: str) -> Optional[ModelMetadata]:
        """Get metadata for a specific model."""
        return self.models.get(model_id)

    def get_active_model(self, horizon_days: int = 5) -> Optional[ModelMetadata]:
        """Get the currently active model for a given horizon."""
        active_models = [
            m for m in self.models.values()
            if m.is_active and m.horizon_days == horizon_days
        ]

        if not active_models:
            return None

        # Return the one with highest AUC
        return max(active_models, key=lambda m: m.val_auc)

    def activate_model(self, model_id: str) -> bool:
        """Activate a model for production use."""
        if model_id not in self.models:
            return False

        # Deactivate all other models with same horizon
        model = self.models[model_id]
        for m in self.models.values():
            if m.horizon_days == model.horizon_days:
                m.is_active = False

        # Activate selected model
        model.is_active = True
        self._save_registry()

        return True

    def list_models(
        self,
        model_type: Optional[str] = None,
        horizon_days: Optional[int] = None,
        min_auc: Optional[float] = None
    ) -> List[ModelMetadata]:
        """List models with optional filters."""
        models = list(self.models.values())

        if model_type:
            models = [m for m in models if m.model_type == model_type]
        if horizon_days is not None:
            models = [m for m in models if m.horizon_days == horizon_days]
        if min_auc is not None:
            models = [m for m in models if m.val_auc >= min_auc]

        return sorted(models, key=lambda m: m.trained_at, reverse=True)

    def delete_model(self, model_id: str) -> bool:
        """Delete a model from the registry."""
        if model_id in self.models:
            del self.models[model_id]
            self._save_registry()

            # Also delete model file
            model_file = self.storage_path / f"{model_id}.pkl"
            if model_file.exists():
                model_file.unlink()

            return True
        return False

    def get_best_model(
        self,
        horizon_days: int = 5,
        metric: str = "auc"
    ) -> Optional[ModelMetadata]:
        """Get the best performing model by specified metric."""
        models = [m for m in self.models.values() if m.horizon_days == horizon_days]

        if not models:
            return None

        if metric == "auc":
            return max(models, key=lambda m: m.val_auc)
        elif metric == "accuracy":
            return max(models, key=lambda m: m.val_accuracy)
        else:
            return models[0]

    def to_dict(self) -> Dict[str, Any]:
        """Serialize registry to dictionary."""
        return {
            "total_models": len(self.models),
            "active_models": sum(1 for m in self.models.values() if m.is_active),
            "models": [m.to_dict() for m in self.list_models()],
        }
