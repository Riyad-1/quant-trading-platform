"""
Training Pipeline with Walk-Forward Validation

Implements proper time-series cross-validation to avoid lookahead bias.
"""
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass
import numpy as np
import polars as pl

from .ml_engine import MLEngine, ModelType


@dataclass
class TrainingConfig:
    """Configuration for training pipeline."""
    model_type: ModelType = ModelType.LIGHTGBM
    horizon_days: int = 5
    train_window_years: int = 5
    validation_window_years: int = 1
    test_window_years: int = 1
    min_train_samples: int = 500
    target_col: str = "target_5d"
    model_params: Optional[Dict[str, Any]] = None


@dataclass
class WalkForwardResult:
    """Results from walk-forward validation."""
    fold: int
    train_start: str
    train_end: str
    test_start: str
    test_end: str
    train_samples: int
    test_samples: int
    val_auc: float
    val_accuracy: float
    feature_importance: Dict[str, float]


class TrainingPipeline:
    """
    Training pipeline with walk-forward validation.

    Ensures no lookahead bias by only using historical data
    available at each prediction point.
    """

    def __init__(self, config: TrainingConfig):
        self.config = config
        self.results: List[WalkForwardResult] = []
        self.final_model: Optional[MLEngine] = None

    def create_walk_forward_splits(
        self,
        df: pl.DataFrame,
        date_col: str = "date"
    ) -> List[Tuple[pl.DataFrame, pl.DataFrame]]:
        """
        Create walk-forward train/test splits.

        Example with 5y train, 1y test:
        Fold 1: Train 2010-2014, Test 2015
        Fold 2: Train 2011-2015, Test 2016
        Fold 3: Train 2012-2016, Test 2017
        ...
        """
        dates = df[date_col].unique().sort()
        min_date = dates.min()
        max_date = dates.max()

        splits = []
        current_train_end = min_date + timedelta(days=self.config.train_window_years * 365)

        while current_train_end < max_date - timedelta(days=self.config.test_window_years * 365):
            test_start = current_train_end
            test_end = test_start + timedelta(days=self.config.test_window_years * 365)

            # Ensure we don't go beyond available data
            if test_end > max_date:
                test_end = max_date

            train_df = df.filter(
                (pl.col(date_col) >= min_date) &
                (pl.col(date_col) <= current_train_end)
            )

            test_df = df.filter(
                (pl.col(date_col) > current_train_end) &
                (pl.col(date_col) <= test_end)
            )

            if len(train_df) >= self.config.min_train_samples and len(test_df) > 0:
                splits.append((train_df, test_df))

            # Move window forward by 1 year
            current_train_end += timedelta(days=365)

        return splits

    def run_walk_forward(
        self,
        df: pl.DataFrame,
        date_col: str = "date"
    ) -> List[WalkForwardResult]:
        """
        Run walk-forward validation across all folds.

        Returns list of results for each fold.
        """
        splits = self.create_walk_forward_splits(df, date_col)
        self.results = []

        for fold_idx, (train_df, test_df) in enumerate(splits):
            # Prepare datasets
            X_train, y_train, feature_names = self._prepare_data(
                train_df, date_col
            )
            X_test, y_test, _ = self._prepare_data(
                test_df, date_col, feature_names
            )

            if len(X_train) == 0 or len(X_test) == 0:
                continue

            # Create and train model
            model = MLEngine(
                model_type=self.config.model_type,
                horizon_days=self.config.horizon_days,
                **(self.config.model_params or {})
            )

            metrics = model.train(
                X_train, y_train,
                feature_names=feature_names,
                X_val=X_test,
                y_val=y_test
            )

            # Store results
            result = WalkForwardResult(
                fold=fold_idx + 1,
                train_start=str(train_df[date_col].min()),
                train_end=str(train_df[date_col].max()),
                test_start=str(test_df[date_col].min()),
                test_end=str(test_df[date_col].max()),
                train_samples=len(X_train),
                test_samples=len(X_test),
                val_auc=metrics.get("val_auc", 0.0),
                val_accuracy=metrics.get("val_accuracy", 0.0),
                feature_importance=model.get_feature_importance(top_n=10)
            )

            self.results.append(result)

        return self.results

    def _prepare_data(
        self,
        df: pl.DataFrame,
        date_col: str,
        feature_names: Optional[List[str]] = None
    ) -> Tuple[np.ndarray, np.ndarray, List[str]]:
        """Prepare data for training/prediction."""
        # Drop rows with nulls in target
        target_col = self.config.target_col
        df_clean = df.filter(pl.col(target_col).is_not_null())

        # Identify feature columns
        if feature_names is None:
            feature_cols = [
                col for col in df_clean.columns
                if col not in [date_col, target_col]
                and df_clean[col].dtype in [pl.Float32, pl.Float64, pl.Int32, pl.Int64]
            ]
        else:
            feature_cols = [col for col in feature_names if col in df_clean.columns]

        X = df_clean.select(feature_cols).to_numpy()
        y = df_clean[target_col].to_numpy()

        return X, y, feature_cols

    def train_final_model(self, df: pl.DataFrame, date_col: str = "date") -> MLEngine:
        """
        Train final model on all available data.

        Uses the most recent train_window_years for training.
        """
        # Get most recent data for training
        dates = df[date_col].unique().sort()
        cutoff = dates.max() - timedelta(days=self.config.train_window_years * 365)

        train_df = df.filter(pl.col(date_col) >= cutoff)

        X_train, y_train, feature_names = self._prepare_data(train_df, date_col)

        self.final_model = MLEngine(
            model_type=self.config.model_type,
            horizon_days=self.config.horizon_days,
            **(self.config.model_params or {})
        )

        self.final_model.train(X_train, y_train, feature_names=feature_names)

        return self.final_model

    def get_summary(self) -> Dict[str, Any]:
        """Get summary statistics from walk-forward validation."""
        if not self.results:
            return {"error": "No walk-forward results available"}

        aucs = [r.val_auc for r in self.results]
        accuracies = [r.val_accuracy for r in self.results]

        return {
            "num_folds": len(self.results),
            "mean_auc": float(np.mean(aucs)),
            "std_auc": float(np.std(aucs)),
            "min_auc": float(np.min(aucs)),
            "max_auc": float(np.max(aucs)),
            "mean_accuracy": float(np.mean(accuracies)),
            "std_accuracy": float(np.std(accuracies)),
            "folds": [
                {
                    "fold": r.fold,
                    "train_period": f"{r.train_start} to {r.train_end}",
                    "test_period": f"{r.test_start} to {r.test_end}",
                    "auc": r.val_auc,
                    "accuracy": r.val_accuracy,
                }
                for r in self.results
            ]
        }

    def to_dict(self) -> Dict[str, Any]:
        """Serialize pipeline results."""
        return {
            "config": {
                "model_type": self.config.model_type.value,
                "horizon_days": self.config.horizon_days,
                "train_window_years": self.config.train_window_years,
                "validation_window_years": self.config.validation_window_years,
                "test_window_years": self.config.test_window_years,
            },
            "summary": self.get_summary(),
        }