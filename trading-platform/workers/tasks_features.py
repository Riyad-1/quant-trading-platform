"""Background tasks for feature calculation."""

from celery import shared_task
from datetime import datetime, date
from typing import List
import logging

from sqlalchemy.orm import Session
from services.features.service import FeatureService
from services.strategies.scorer import StockScorer
from apps.api.src.core.database import get_db_session
from apps.api.src.db.models import Asset, Signal, Strategy

logger = logging.getLogger(__name__)


@shared_task
def calculate_technical_features(asset_id: int, target_date: str):
    """
    Calculate technical indicators for an asset.

    Features include:
    - Moving averages (SMA20, SMA50, SMA200)
    - RSI, MACD
    - ATR, volatility
    - Returns (5d, 10d, 20d, 60d)
    - Relative strength vs SPY
    """
    logger.info(f"Calculating features for asset {asset_id} on {target_date}")

    try:
        db = next(get_db_session())
        feature_service = FeatureService(db)

        # Parse date
        calc_date = datetime.strptime(target_date, "%Y-%m-%d").date()

        # Calculate features
        features = feature_service.calculate_features_for_asset(asset_id, calc_date)

        if features:
            # Save to database
            count = feature_service.save_features(asset_id, features)
            logger.info(f"Saved {count} features for asset {asset_id}")

            return {
                "asset_id": asset_id,
                "date": target_date,
                "status": "completed",
                "features_calculated": count
            }
        else:
            logger.warning(f"No features calculated for asset {asset_id} - insufficient data")
            return {
                "asset_id": asset_id,
                "date": target_date,
                "status": "skipped",
                "reason": "insufficient_data"
            }

    except Exception as e:
        logger.error(f"Error calculating features for asset {asset_id}: {str(e)}")
        return {
            "asset_id": asset_id,
            "date": target_date,
            "status": "failed",
            "error": str(e)
        }
    finally:
        db.close()


@shared_task
def calculate_universe_features(target_date: str):
    """
    Calculate features for entire stock universe.

    Runs daily after market close.
    """
    logger.info(f"Calculating universe features for {target_date}")

    try:
        db = next(get_db_session())
        feature_service = FeatureService(db)

        calc_date = datetime.strptime(target_date, "%Y-%m-%d").date()

        # Get all active assets
        assets = db.query(Asset).filter(Asset.status == "active").all()

        processed = 0
        failed = 0
        skipped = 0

        for asset in assets:
            try:
                features = feature_service.calculate_features_for_asset(asset.id, calc_date)

                if features:
                    feature_service.save_features(asset.id, features)
                    processed += 1
                else:
                    skipped += 1

            except Exception as e:
                logger.error(f"Error processing asset {asset.ticker}: {str(e)}")
                failed += 1

        logger.info(f"Feature calculation complete: {processed} processed, {skipped} skipped, {failed} failed")

        return {
            "date": target_date,
            "status": "completed",
            "assets_processed": processed,
            "assets_skipped": skipped,
            "assets_failed": failed
        }

    except Exception as e:
        logger.error(f"Error in universe feature calculation: {str(e)}")
        return {
            "date": target_date,
            "status": "failed",
            "error": str(e)
        }


@shared_task
def generate_daily_signals(target_date: str, strategy_id: int = 1):
    """
    Generate trading signals for all stocks based on scoring system.

    This runs after features are calculated and produces ranked opportunities.
    """
    logger.info(f"Generating signals for {target_date}")

    try:
        db = next(get_db_session())
        feature_service = FeatureService(db)
        scorer = StockScorer()

        calc_date = datetime.strptime(target_date, "%Y-%m-%d").date()

        # Get current market regime (simplified - will be enhanced in Phase 4)
        market_regime = "neutral"  # TODO: Fetch from market_regimes table

        # Get all active assets with sufficient liquidity
        assets = db.query(Asset).filter(
            Asset.status == "active",
            Asset.market_cap >= 2_000_000_000  # $2B+ market cap filter
        ).all()

        asset_ids = [a.id for a in assets]

        if not asset_ids:
            return {
                "date": target_date,
                "status": "skipped",
                "reason": "no_assets"
            }

        # Get feature matrix
        feature_matrix = feature_service.get_feature_matrix(
            asset_ids=asset_ids,
            target_date=calc_date
        )

        if feature_matrix.is_empty():
            logger.warning("No features found for signal generation")
            return {
                "date": target_date,
                "status": "skipped",
                "reason": "no_features"
            }

        # Rank stocks
        ranked_stocks = scorer.rank_stocks(
            feature_matrix=feature_matrix,
            market_regime=market_regime
        )

        # Create signals for top-ranked stocks
        signals_created = 0

        # Get strategy
        strategy = db.query(Strategy).filter(Strategy.id == strategy_id).first()
        if not strategy:
            # Create default strategy if it doesn't exist
            strategy = Strategy(
                name="Momentum Breakout",
                description="Momentum + Breakout + Relative Strength strategy",
                version="1.0.0",
                parameters={"weights": scorer.weights}
            )
            db.add(strategy)
            db.commit()
            db.refresh(strategy)

        # Generate signals for top 50 stocks
        for stock in ranked_stocks[:50]:
            if stock["composite_score"] < 70:  # Minimum score threshold
                continue

            signal = Signal(
                generated_at=datetime.now(),
                asset_id=stock["asset_id"],
                strategy_id=strategy.id,
                model_version="scorer_v1.0",
                score=stock["composite_score"],
                direction="long",
                confidence=stock["confidence"],
                explanation=_generate_signal_explanation(stock),
                metadata={
                    "sub_scores": stock["sub_scores"],
                    "setup_type": stock["setup_type"],
                    "rank": stock["rank"]
                }
            )

            db.add(signal)
            signals_created += 1

        db.commit()

        logger.info(f"Generated {signals_created} signals for {target_date}")

        return {
            "date": target_date,
            "status": "completed",
            "signals_generated": signals_created,
            "top_stock": ranked_stocks[0]["ticker"] if ranked_stocks else None,
            "top_score": ranked_stocks[0]["composite_score"] if ranked_stocks else None
        }

    except Exception as e:
        logger.error(f"Error generating signals: {str(e)}")
        return {
            "date": target_date,
            "status": "failed",
            "error": str(e)
        }
    finally:
        db.close()


def _generate_signal_explanation(stock: dict) -> str:
    """Generate human-readable explanation for why a stock was selected."""
    ticker = stock["ticker"]
    setup = stock["setup_type"]
    score = stock["composite_score"]
    sub_scores = stock["sub_scores"]

    explanations = []

    # Find strongest factors
    sorted_factors = sorted(sub_scores.items(), key=lambda x: x[1], reverse=True)

    explanations.append(f"{ticker} ranks #{stock['rank']} with a score of {score}/100.")
    explanations.append(f"Primary setup: {setup}.")

    if sorted_factors[0][1] > 80:
        explanations.append(f"Exceptional {sorted_factors[0][0]} score ({sorted_factors[0][1]:.0f}/100).")

    if sorted_factors[1][1] > 70:
        explanations.append(f"Strong {sorted_factors[1][0]} ({sorted_factors[1][1]:.0f}/100).")

    return " ".join(explanations)