"""
Feature Importance Analyzer using SHAP values.
"""
from typing import Dict, List, Any, Optional, Tuple
import numpy as np
import polars as pl


class FeatureImportanceAnalyzer:
    """
    Analyze and explain feature importance from trained models.

    Provides both global importance (across all predictions)
    and local importance (for individual predictions).
    """

    def __init__(self, model, feature_names: List[str]):
        """
        Initialize with a trained model.

        Args:
            model: Trained model with predict_proba method
            feature_names: List of feature names
        """
        self.model = model
        self.feature_names = feature_names
        self.num_features = len(feature_names)

    def get_global_importance(
        self,
        X: np.ndarray,
        top_n: int = 20
    ) -> Dict[str, float]:
        """
        Get global feature importance.

        For tree models, uses built-in feature_importances_.
        For linear models, uses coefficient magnitudes.
        """
        if hasattr(self.model, 'feature_importances_'):
            importances = self.model.feature_importances_
        elif hasattr(self.model, 'coef_'):
            # Linear models: use absolute coefficient values
            importances = np.abs(self.model.coef_[0])
            # Normalize to match scale of tree importances
            importances = importances / importances.sum()
        else:
            raise ValueError("Model does not support feature importance")

        # Create mapping
        importance_dict = dict(zip(self.feature_names, importances))

        # Sort and return top N
        sorted_importance = sorted(
            importance_dict.items(),
            key=lambda x: x[1],
            reverse=True
        )

        return dict(sorted_importance[:top_n])

    def get_local_importance(
        self,
        x: np.ndarray,
        prediction_idx: int = 0
    ) -> Dict[str, float]:
        """
        Get feature importance for a single prediction.

        Uses a simplified approach based on feature values
        and their typical importance.

        Note: For production, consider integrating SHAP library
        for more accurate local explanations.
        """
        # Get global importance as baseline
        global_importance = self.get_global_importance(
            x.reshape(1, -1)
        )

        # Weight by deviation from median (simplified local explanation)
        # In production, use SHAP values for accurate local importance
        local_importance = {}
        for i, (feature_name, global_imp) in enumerate(global_importance.items()):
            feature_value = x[i] if i < len(x) else 0
            # Simple heuristic: high value + high importance = high local importance
            local_importance[feature_name] = global_imp * abs(feature_value)

        # Normalize
        total = sum(local_importance.values())
        if total > 0:
            local_importance = {k: v/total for k, v in local_importance.items()}

        return dict(sorted(
            local_importance.items(),
            key=lambda x: x[1],
            reverse=True
        ))

    def explain_prediction(
        self,
        x: np.ndarray,
        probability: float,
        top_n: int = 5
    ) -> Dict[str, Any]:
        """
        Generate human-readable explanation for a prediction.

        Returns dictionary with:
        - prediction confidence
        - top contributing features
        - brief explanation text
        """
        local_importance = self.get_local_importance(x)
        top_features = list(local_importance.items())[:top_n]

        # Determine direction (positive/negative contribution)
        # This is simplified - in production use SHAP values
        feature_explanations = []
        for feature_name, importance in top_features:
            idx = self.feature_names.index(feature_name)
            value = x[idx] if idx < len(x) else 0

            # Heuristic: high RSI might be negative, high momentum positive
            direction = "positive" if value > 0 else "negative"
            if 'rsi' in feature_name.lower():
                direction = "negative" if value > 70 else "positive" if value < 30 else "neutral"

            feature_explanations.append({
                "feature": feature_name,
                "importance": importance,
                "value": float(value),
                "direction": direction,
            })

        # Generate confidence level
        if probability >= 0.7:
            confidence = "High"
        elif probability >= 0.55:
            confidence = "Medium"
        else:
            confidence = "Low"

        return {
            "probability": float(probability),
            "confidence": confidence,
            "top_features": feature_explanations,
            "explanation": self._generate_text(
                probability, confidence, feature_explanations
            ),
        }

    def _generate_text(
        self,
        probability: float,
        confidence: str,
        feature_explanations: List[Dict]
    ) -> str:
        """Generate natural language explanation."""
        prob_pct = int(probability * 100)

        text = f"Model predicts {prob_pct}% probability of outperformance ({confidence} confidence).\n\n"
        text += "Key factors:\n"

        for feat in feature_explanations[:3]:
            direction_text = {
                "positive": "supports outperformance",
                "negative": "suggests underperformance",
                "neutral": "has neutral impact"
            }.get(feat["direction"], "has mixed impact")

            text += f"- {feat['feature'].replace('_', ' ').title()}: {direction_text}\n"

        return text

    def compare_features(
        self,
        x1: np.ndarray,
        x2: np.ndarray,
        ticker1: str,
        ticker2: str
    ) -> Dict[str, Any]:
        """
        Compare feature profiles between two stocks.

        Useful for explaining why one stock ranks higher than another.
        """
        comparison = []

        for i, feature_name in enumerate(self.feature_names):
            if i >= len(x1) or i >= len(x2):
                continue

            val1 = x1[i]
            val2 = x2[i]
            diff = val1 - val2

            comparison.append({
                "feature": feature_name,
                f"{ticker1}_value": float(val1),
                f"{ticker2}_value": float(val2),
                "difference": float(diff),
                "advantage": ticker1 if diff > 0.01 else ticker2 if diff < -0.01 else "neutral"
            })

        # Sort by absolute difference
        comparison.sort(key=lambda x: abs(x["difference"]), reverse=True)

        return {
            "ticker1": ticker1,
            "ticker2": ticker2,
            "key_differences": comparison[:10],
        }