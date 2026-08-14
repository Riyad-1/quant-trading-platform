"""
LLM-based News Event Extractor.

Uses LLM to convert raw news text into structured catalyst events.
For now, uses rule-based extraction as a placeholder for actual LLM integration.
"""
import re
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime

from apps.api.src.db.models_news import NewsArticle, NewsEvent, CatalystScore
from apps.api.src.db.session import get_db_session


class NewsEventExtractor:
    """Extracts structured events from news articles using LLM or rules."""

    # Rule-based patterns for event classification (placeholder for LLM)
    EVENT_PATTERNS = {
        "earnings_beat": [
            r"beats?\s+(estimates|expectations|forecasts)",
            r"exceeds?\s+(expectations|guidance)",
            r"surpasses?\s+estimates",
            r"better\s+than\s+expected",
            r"positive\s+surprise"
        ],
        "earnings_miss": [
            r"misses?\s+(estimates|expectations|forecasts)",
            r"falls\s+short\s+of",
            r"below\s+(expectations|estimates|guidance)",
            r"disappointing\s+(results|earnings)",
            r"negative\s+surprise"
        ],
        "guidance_raise": [
            r"raises?\s+(guidance|forecast|outlook)",
            r"upgrades?\s+(guidance|outlook)",
            r"increases?\s+(forecast|guidance)",
            r"higher\s+(guidance|forecast)"
        ],
        "guidance_cut": [
            r"cuts?\s+(guidance|forecast|outlook)",
            r"lowers?\s+(guidance|forecast|outlook)",
            r"reduces?\s+(guidance|forecast)",
            r"downgrades?\s+(guidance|outlook)",
            r"lower\s+(guidance|forecast)"
        ],
        "upgrade": [
            r"upgrad(?:e|ed|es)\s+to\s+(buy|outperform|overweight)",
            r"raised?\s+(rating|target)",
            r"initiated\s+with\s+(buy|outperform)"
        ],
        "downgrade": [
            r"downgrad(?:e|ed|es)\s+to\s+(sell|underperform|underweight)",
            r"lowered?\s+(rating|target)",
            r"cut\s+(rating|target)"
        ],
        "acquisition": [
            r"acquir(?:e|es|ing|ed)",
            r"merger\s+with",
            r"takeover",
            r"purchases?\s+(company|stake)"
        ],
        "product_launch": [
            r"launches?\s+(new|product)",
            r"unveils?\s+(new|product)",
            r"introduces?\s+(new|product)",
            r"announces?\s+(new|product)"
        ],
        "executive_change": [
            r"ceo\s+(resigns|leaves|steps\s+down)",
            r"cfo\s+(resigns|leaves|steps\s+down)",
            r"(appoints?|hires?)\s+(new\s+)?(ceo|cfo)",
            r"executive\s+(change|shuffle)"
        ],
        "contract_win": [
            r"wins?\s+(contract|deal)",
            r"secures?\s+(contract|deal)",
            r"awarded\s+(contract|deal)"
        ],
        "regulatory_issue": [
            r"investigation\s+(by|into)",
            r"regulatory\s+(scrutiny|issue|probe)",
            r"lawsuit\s+(filed|against)",
            r"sued\s+by"
        ]
    }

    def __init__(self, use_llm: bool = False):
        """
        Initialize extractor.

        Args:
            use_llm: If True, use actual LLM API. If False, use rule-based extraction.
        """
        self.use_llm = use_llm
        # In production, initialize LLM client here if use_llm=True

    def extract_events(self, article: NewsArticle, tickers: List[str]) -> List[NewsEvent]:
        """
        Extract structured events from a news article.

        Args:
            article: NewsArticle object
            tickers: List of tickers mentioned in the article

        Returns:
            List of NewsEvent objects
        """
        events = []
        text_to_analyze = f"{article.headline} {article.summary or ''} {article.content or ''}"
        text_lower = text_to_analyze.lower()

        for ticker in tickers:
            # Find matching event types
            matched_events = []
            for event_type, patterns in self.EVENT_PATTERNS.items():
                for pattern in patterns:
                    if re.search(pattern, text_lower):
                        matched_events.append(event_type)
                        break  # One match per event type is enough

            if not matched_events:
                # Default to neutral if no clear signal
                matched_events = ["neutral"]

            # Create event(s) for this ticker
            for event_type in matched_events:
                sentiment, importance, surprise = self._calculate_metrics(
                    event_type, text_to_analyze
                )

                event = NewsEvent(
                    article_id=article.id,
                    ticker=ticker,
                    event_type=event_type,
                    sentiment_score=sentiment,
                    importance_score=importance,
                    surprise_magnitude=surprise,
                    expected_duration=self._estimate_duration(event_type),
                    llm_reasoning="Rule-based extraction" if not self.use_llm else "LLM analysis",
                    extracted_catalysts=[event_type] if event_type != "neutral" else []
                )
                events.append(event)

        return events

    def _calculate_metrics(
        self,
        event_type: str,
        text: str
    ) -> Tuple[float, float, Optional[float]]:
        """
        Calculate sentiment, importance, and surprise metrics.

        Returns:
            Tuple of (sentiment_score, importance_score, surprise_magnitude)
        """
        # Sentiment mapping
        sentiment_map = {
            "earnings_beat": 0.8,
            "earnings_miss": -0.8,
            "guidance_raise": 0.7,
            "guidance_cut": -0.7,
            "upgrade": 0.6,
            "downgrade": -0.6,
            "acquisition": 0.3,  # Can be positive or negative
            "product_launch": 0.4,
            "executive_change": -0.2,  # Usually negative unless specified
            "contract_win": 0.5,
            "regulatory_issue": -0.7,
            "neutral": 0.0
        }

        # Importance mapping
        importance_map = {
            "earnings_beat": 0.9,
            "earnings_miss": 0.9,
            "guidance_raise": 0.85,
            "guidance_cut": 0.85,
            "upgrade": 0.6,
            "downgrade": 0.6,
            "acquisition": 0.8,
            "product_launch": 0.5,
            "executive_change": 0.7,
            "contract_win": 0.7,
            "regulatory_issue": 0.8,
            "neutral": 0.3
        }

        sentiment = sentiment_map.get(event_type, 0.0)
        importance = importance_map.get(event_type, 0.5)

        # Estimate surprise magnitude for earnings events
        surprise = None
        if event_type in ["earnings_beat", "earnings_miss"]:
            # Look for percentage numbers in text
            percentages = re.findall(r'(\d+)%', text)
            if percentages:
                surprise = float(percentages[0]) / 100.0
                if event_type == "earnings_miss":
                    surprise = -abs(surprise)
                else:
                    surprise = abs(surprise)
            else:
                surprise = 0.1  # Default small surprise

        return sentiment, importance, surprise

    def _estimate_duration(self, event_type: str) -> str:
        """Estimate how long the market impact will last."""
        duration_map = {
            "earnings_beat": "multi_day",
            "earnings_miss": "multi_day",
            "guidance_raise": "multi_week",
            "guidance_cut": "multi_week",
            "upgrade": "intraday",
            "downgrade": "intraday",
            "acquisition": "multi_week",
            "product_launch": "multi_day",
            "executive_change": "multi_day",
            "contract_win": "multi_day",
            "regulatory_issue": "multi_week",
            "neutral": "intraday"
        }
        return duration_map.get(event_type, "intraday")

    def process_unprocessed_articles(self, limit: int = 100) -> int:
        """
        Process all unprocessed articles in the database.

        Args:
            limit: Maximum number of articles to process

        Returns:
            Number of articles processed
        """
        db = next(get_db_session())
        try:
            articles = db.query(NewsArticle).filter(
                NewsArticle.is_processed == False
            ).limit(limit).all()

            processed_count = 0
            for article in articles:
                # Get associated tickers
                ticker_links = db.query(TickerNewsLink).filter(
                    TickerNewsLink.article_id == article.id
                ).all()
                tickers = [link.ticker for link in ticker_links]

                if not tickers:
                    continue

                # Extract events
                events = self.extract_events(article, tickers)
                for event in events:
                    db.add(event)

                # Mark article as processed
                article.is_processed = True
                processed_count += 1

            db.commit()
            return processed_count
        except Exception as e:
            db.rollback()
            raise e
        finally:
            db.close()

    def calculate_daily_catalyst_scores(self, date: datetime) -> int:
        """
        Calculate aggregated daily catalyst scores for all tickers.

        Args:
            date: Date to calculate scores for

        Returns:
            Number of scores calculated
        """
        db = next(get_db_session())
        try:
            # Get all events for the date
            start_dt = date.replace(hour=0, minute=0, second=0)
            end_dt = date.replace(hour=23, minute=59, second=59)

            events = db.query(NewsEvent).join(NewsArticle).filter(
                NewsArticle.published_at >= start_dt,
                NewsArticle.published_at <= end_dt
            ).all()

            # Group by ticker
            ticker_events: Dict[str, List[NewsEvent]] = {}
            for event in events:
                if event.ticker not in ticker_events:
                    ticker_events[event.ticker] = []
                ticker_events[event.ticker].append(event)

            # Calculate scores
            scores_created = 0
            for ticker, events_list in ticker_events.items():
                bullish = sum(1 for e in events_list if e.sentiment_score > 0.2)
                bearish = sum(1 for e in events_list if e.sentiment_score < -0.2)

                # Weighted sentiment
                net_sentiment = sum(
                    e.sentiment_score * e.importance_score
                    for e in events_list
                )

                max_importance = max(e.importance_score for e in events_list) if events_list else 0.0

                # Composite score (0-100)
                # Base 50, add sentiment component, boost for high importance events
                composite = 50.0 + (net_sentiment * 25) + (max_importance * 25)
                composite = max(0, min(100, composite))  # Clamp to 0-100

                score = CatalystScore(
                    ticker=ticker,
                    date=date,
                    net_sentiment=net_sentiment,
                    max_importance=max_importance,
                    event_count=len(events_list),
                    bullish_events=bullish,
                    bearish_events=bearish,
                    composite_score=composite
                )
                db.add(score)
                scores_created += 1

            db.commit()
            return scores_created
        except Exception as e:
            db.rollback()
            raise e
        finally:
            db.close()


# Import to avoid circular dependency
from apps.api.src.db.models_news import TickerNewsLink