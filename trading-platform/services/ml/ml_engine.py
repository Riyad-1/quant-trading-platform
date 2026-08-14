"""
Machine Learning Engine for Stock Ranking and Classification

Supports multiple model types:
- LightGBM (default, fast and accurate)
- XGBoost
- RandomForest (interpretable baseline)
- LogisticRegression (simple baseline)

Focuses on classification/ranking tasks rather than price prediction.
"""
import json
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
from enum import Enum
from pathlib import Path
import pickle

import numpy as np
import polars as pl
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import roc_auc_score, accuracy_score, precision_recall_fscore_support
import lightgbm as lgb
import xgboost as xgb
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression


class ModelType(str, Enum):
    """Supported model types."""
    LIGHTGBM = "lightgbm"
    XGBOOST = "xgboost"
    RANDOM_FOREST = "random_forest"
    LOGISTIC_REGRESSION = "logistic_regression"


class MLEngine:
    """
    Machine Learning Engine for stock ranking/classification.

    Predicts probability that a stock will outperform SPY over
    specified horizons (1, 3, 5, 10, 20 trading days).
    """

    def __init__(
        self,
        model_type: ModelType = ModelType.LIGHTGBM,
        horizon_days: int = 5,
        task_type: str = "classification",  # or "ranking"
        **model_params
    ):
        self.model_type = model_type
        self.horizon_days = horizon_days
        self.task_type = task_type
        self.model = None
        self.feature_names: List[str] = []
        self.is_fitted = False
        self.model_params = model_params or {}

        # Default parameters for each model type
        self._default_params = {
            ModelType.LIGHTGBM: {
                "n_estimators": 100,
                "max_depth": 6,
                "learning_rate": 0.05,
                "num_leaves": 31,
                "min_child_samples": 20,
                "subsample": 0.8,
                "colsample_bytree": 0.8,
                "random_state": 42,
                "verbose": -1,
            },
            ModelType.XGBOOST: {
                "n_estimators": 100,
                "max_depth": 6,
                "learning_rate": 0.05,
                "subsample": 0.8,
                "colsample_bytree": 0.8,
                "random_state": 42,
                "verbosity": 0,
            },
            ModelType.RANDOM_FOREST: {
                "n_estimators": 100,
                "max_depth": 10,
                "min_samples_split": 20,
                "min_samples_leaf": 10,
                "random_state": 42,
                "n_jobs": -1,
            },
            ModelType.LOGISTIC_REGRESSION: {
                "C": 1.0,
                "max_iter": 1000,
                "random_state": 42,
            },
        }

    def _initialize_model(self) -> Any:
        """Initialize the model with parameters."""
        params = {**self._default_params[self.model_type], **self.model_params}

        if self.model_type == ModelType.LIGHTGBM:
            return lgb.LGBMClassifier(**params)
        elif self.model_type == ModelType.XGBOOST:
            return xgb.XGBClassifier(**params)
        elif self.model_type == ModelType.RANDOM_FOREST:
            return RandomForestClassifier(**params)
        elif self.model_type == ModelType.LOGISTIC_REGRESSION:
            return LogisticRegression(**params)
        else:
            raise ValueError(f"Unknown model type: {self.model_type}")

    def prepare_dataset(
        self,
        features_df: pl.DataFrame,
        target_col: str = "target_5d"
    ) -> Tuple[np.ndarray, np.ndarray, List[str]]:
        """
        Prepare feature matrix and target vector from DataFrame.

        Args:
            features_df: DataFrame with features and target
            target_col: Name of target column

        Returns:
            X, y, feature_names
        """
        # Drop rows with nulls in target
        df = features_df.filter(pl.col(target_col).is_not_null())

        # Identify feature columns (all numeric except target)
        feature_cols = [
            col for col in df.columns
            if col != target_col and df[col].dtype in [pl.Float32, pl.Float64, pl.Int32, pl.Int64]
        ]

        X = df.select(feature_cols).to_numpy()
        y = df[target_col].to_numpy()

        return X, y, feature_cols

    def train(
        self,
        X_train: np.ndarray,
        y_train: np.ndarray,
        feature_names: Optional[List[str]] = None,
        X_val: Optional[np.ndarray] = None,
        y_val: Optional[np.ndarray] = None,
    ) -> Dict[str, float]:
        """
        Train the model on provided data.

        Args:
            X_train: Training features
            y_train: Training targets
            feature_names: Names of features
            X_val: Validation features (optional)
            y_val: Validation targets (optional)

        Returns:
            Dictionary with training metrics
        """
        self.model = self._initialize_model()
        self.feature_names = feature_names or [f"feature_{i}" for i in range(X_train.shape[1])]

        # Train with validation if provided
        if (
            X_val is not None
            and y_val is not None
            and self.model_type in {ModelType.LIGHTGBM, ModelType.XGBOOST}
        ):
            self.model.fit(
                X_train, y_train,
                eval_set=[(X_val, y_val)],
            )
        else:
            self.model.fit(X_train, y_train)

        self.is_fitted = True

        # Calculate training metrics
        y_pred_train = self.model.predict(X_train)
        y_proba_train = self.model.predict_proba(X_train)[:, 1]

        metrics = {
            "train_accuracy": accuracy_score(y_train, y_pred_train),
            "train_auc": roc_auc_score(y_train, y_proba_train) if len(np.unique(y_train)) > 1 else 0.5,
        }

        # Validation metrics if available
        if X_val is not None and y_val is not None:
            y_pred_val = self.model.predict(X_val)
            y_proba_val = self.model.predict_proba(X_val)[:, 1]
            metrics["val_accuracy"] = accuracy_score(y_val, y_pred_val)
            metrics["val_auc"] = roc_auc_score(y_val, y_proba_val) if len(np.unique(y_val)) > 1 else 0.5

        return metrics

    def predict(self, X: np.ndarray) -> np.ndarray:
        """Predict class labels."""
        if not self.is_fitted:
            raise RuntimeError("Model must be fitted before prediction")
        return self.model.predict(X)

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """Predict probability of positive class (outperformance)."""
        if not self.is_fitted:
            raise RuntimeError("Model must be fitted before prediction")
        return self.model.predict_proba(X)[:, 1]

    def get_feature_importance(self, top_n: int = 20) -> Dict[str, float]:
        """Get feature importance scores."""
        if not self.is_fitted:
            raise RuntimeError("Model must be fitted before getting importance")

        if hasattr(self.model, 'feature_importances_'):
            importances = self.model.feature_importances_
        else:
            # For logistic regression, use absolute coefficients
            importances = np.abs(self.model.coef_[0])

        # Normalize to sum to 1
        importances = importances / importances.sum()

        importance_dict = dict(zip(self.feature_names, importances))
        sorted_importance = sorted(importance_dict.items(), key=lambda x: x[1], reverse=True)

        return dict(sorted_importance[:top_n])

    def save(self, path: str) -> None:
        """Save model to disk."""
        Path(path).parent.mkdir(parents=True, exist_ok=True)

        model_data = {
            "model": self.model,
            "model_type": self.model_type.value,
            "horizon_days": self.horizon_days,
            "task_type": self.task_type,
            "feature_names": self.feature_names,
            "is_fitted": self.is_fitted,
            "model_params": self.model_params,
            "trained_at": datetime.now().isoformat(),
        }

        with open(path, 'wb') as f:
            pickle.dump(model_data, f)

    def load(self, path: str) -> None:
        """Load model from disk."""
        with open(path, 'rb') as f:
            model_data = pickle.load(f)

        self.model = model_data["model"]
        self.model_type = ModelType(model_data["model_type"])
        self.horizon_days = model_data["horizon_days"]
        self.task_type = model_data["task_type"]
        self.feature_names = model_data["feature_names"]
        self.is_fitted = model_data["is_fitted"]
        self.model_params = model_data.get("model_params", {})

    def to_dict(self) -> Dict[str, Any]:
        """Serialize model metadata to dictionary."""
        return {
            "model_type": self.model_type.value,
            "horizon_days": self.horizon_days,
            "task_type": self.task_type,
            "is_fitted": self.is_fitted,
            "num_features": len(self.feature_names),
            "feature_names": self.feature_names[:10],  # First 10 for brevity
            "model_params": self.model_params,
        }
