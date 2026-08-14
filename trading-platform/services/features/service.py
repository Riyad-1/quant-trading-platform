"""Feature service for database operations."""

from typing import List, Dict, Any, Optional
from datetime import date, datetime
import polars as pl
from sqlalchemy.orm import Session
from sqlalchemy import select, delete

from ..db.models import FeatureDaily, Asset
from .engine import FeatureEngine


class FeatureService:
    """Service for managing feature calculations and storage."""

    def __init__(self, db_session: Session):
        self.db = db_session
        self.engine = FeatureEngine()

    def get_price_data_for_asset(
        self,
        asset_id: int,
        start_date: date,
        end_date: date
    ) -> Optional[pl.DataFrame]:
        """Fetch price data from database and convert to Polars DataFrame."""

        query = select(
            Asset.ticker,
            FeatureDaily.time,
            # We need to join with prices_daily - this is a simplified version
        ).where(
            # Add proper joins and filters here
        )

        # For now, return None - actual implementation requires price data access
        # This will be implemented when we have the data ingestion working
        return None

    def calculate_features_for_asset(
        self,
        asset_id: int,
        target_date: date
    ) -> List[Dict[str, Any]]:
        """
        Calculate all features for a specific asset on a specific date.

        Args:
            asset_id: Database ID of the asset
            target_date: Date to calculate features for

        Returns:
            List of feature dictionaries ready for database insertion
        """
        # Get historical price data (need ~252 days for 52-week features)
        start_date = date(target_date.year - 1, target_date.month, target_date.day)

        # Fetch price data - placeholder for actual implementation
        price_df = self.get_price_data_for_asset(asset_id, start_date, target_date)

        if price_df is None or len(price_df) < 252:
            return []

        # Calculate all features
        features_df = self.engine.calculate_all_features(price_df)

        # Get the last row (target_date)
        last_row = features_df.filter(pl.col("time") == target_date)

        if len(last_row) == 0:
            return []

        # Convert to list of FeatureDaily objects
        feature_records = []
        feature_columns = self.engine.get_feature_columns()

        for col in feature_columns:
            if col in last_row.columns:
                value = last_row[col][0]
                if value is not None and not (isinstance(value, float) and str(value) == 'nan'):
                    feature_records.append({
                        "asset_id": asset_id,
                        "time": target_date,
                        "feature_name": col,
                        "feature_value": float(value)
                    })

        return feature_records

    def save_features(
        self,
        asset_id: int,
        features: List[Dict[str, Any]]
    ) -> int:
        """
        Save calculated features to database.

        Args:
            asset_id: Asset ID
            features: List of feature dictionaries

        Returns:
            Number of features saved
        """
        saved_count = 0

        for feat in features:
            feature_obj = FeatureDaily(
                asset_id=feat["asset_id"],
                time=feat["time"],
                feature_name=feat["feature_name"],
                feature_value=feat["feature_value"]
            )
            self.db.add(feature_obj)
            saved_count += 1

        try:
            self.db.commit()
        except Exception as e:
            self.db.rollback()
            raise e

        return saved_count

    def get_latest_features(
        self,
        asset_id: int,
        feature_names: Optional[List[str]] = None
    ) -> Dict[str, float]:
        """
        Get the latest feature values for an asset.

        Args:
            asset_id: Asset ID
            feature_names: Optional list of specific features to retrieve

        Returns:
            Dictionary of feature_name -> value
        """
        query = select(FeatureDaily).where(
            FeatureDaily.asset_id == asset_id
        )

        if feature_names:
            query = query.where(
                FeatureDaily.feature_name.in_(feature_names)
            )

        # Order by time descending and get latest for each feature
        query = query.order_by(FeatureDaily.time.desc())

        results = self.db.execute(query).scalars().all()

        # Get latest value for each feature
        features_dict = {}
        seen_features = set()

        for result in results:
            if result.feature_name not in seen_features:
                features_dict[result.feature_name] = float(result.feature_value)
                seen_features.add(result.feature_name)

        return features_dict

    def get_feature_matrix(
        self,
        asset_ids: List[int],
        target_date: date,
        feature_names: Optional[List[str]] = None
    ) -> pl.DataFrame:
        """
        Get feature matrix for multiple assets on a specific date.

        Args:
            asset_ids: List of asset IDs
            target_date: Date to fetch features for
            feature_names: Optional list of specific features

        Returns:
            Polars DataFrame with columns [asset_id, ticker, feature1, feature2, ...]
        """
        query = select(
            FeatureDaily.asset_id,
            Asset.ticker,
            FeatureDaily.feature_name,
            FeatureDaily.feature_value
        ).join(
            Asset, FeatureDaily.asset_id == Asset.id
        ).where(
            FeatureDaily.time == target_date,
            FeatureDaily.asset_id.in_(asset_ids)
        )

        if feature_names:
            query = query.where(
                FeatureDaily.feature_name.in_(feature_names)
            )

        results = self.db.execute(query).all()

        if not results:
            return pl.DataFrame()

        # Convert to wide format
        data = [
            {"asset_id": r[0], "ticker": r[1], "feature_name": r[2], "feature_value": r[3]}
            for r in results
        ]

        df = pl.DataFrame(data)

        # Pivot to wide format
        wide_df = df.pivot(
            index=["asset_id", "ticker"],
            columns="feature_name",
            values="feature_value"
        )

        return wide_df

    def delete_features_for_date(
        self,
        asset_id: int,
        target_date: date
    ) -> int:
        """Delete features for a specific asset and date."""

        stmt = delete(FeatureDaily).where(
            FeatureDaily.asset_id == asset_id,
            FeatureDaily.time == target_date
        )

        result = self.db.execute(stmt)
        self.db.commit()

        return result.rowcount
