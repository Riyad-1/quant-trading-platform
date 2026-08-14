"""
News Provider Interface and Mock Implementation.

Abstract base class for news data providers with a mock implementation for testing.
"""
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
import random
import sys
from pathlib import Path

# Add project root to path for imports
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from apps.api.src.db.models_news import NewsArticle, NewsEvent, NewsSource, TickerNewsLink
from apps.api.src.db.session import db_session


class NewsProvider(ABC):
    """Abstract base class for news data providers."""

    @abstractmethod
    def fetch_articles(
        self,
        tickers: Optional[List[str]] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Fetch raw news articles from the provider."""
        pass

    @abstractmethod
    def save_articles(self, articles: List[Dict[str, Any]], source_name: str) -> int:
        """Save fetched articles to the database. Returns count saved."""
        pass


class MockNewsProvider(NewsProvider):
    """Mock news provider for testing and development."""

    # Sample headlines for simulation
    _headline_templates = [
        "{ticker} reports strong quarterly earnings, beats estimates",
        "{ticker} announces new product launch in AI sector",
        "{ticker} faces regulatory scrutiny over market practices",
        "{ticker} upgrades guidance following robust demand",
        "{ticker} CEO resigns amid restructuring plan",
        "{ticker} secures major government contract worth $500M",
        "{ticker} stock surges on analyst upgrade to 'Buy'",
        "{ticker} warns of supply chain headwinds in Q4",
        "{ticker} completes acquisition of rival firm",
        "{ticker} launches share buyback program"
    ]

    _event_types = [
        "earnings_beat", "earnings_miss", "guidance_raise", "guidance_cut",
        "upgrade", "downgrade", "acquisition", "lawsuit", "product_launch",
        "executive_change", "contract_win", "regulatory_issue"
    ]

    def fetch_articles(
        self,
        tickers: Optional[List[str]] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Generate mock news articles."""
        if tickers is None:
            tickers = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA"]

        if start_date is None:
            start_date = datetime.now() - timedelta(days=7)
        if end_date is None:
            end_date = datetime.now()

        articles = []
        for i in range(limit):
            ticker = random.choice(tickers)
            headline_template = random.choice(self._headline_templates)
            headline = headline_template.format(ticker=ticker)

            pub_date = start_date + timedelta(
                days=random.random() * (end_date - start_date).days,
                hours=random.randint(0, 23),
                minutes=random.randint(0, 59)
            )

            article = {
                "external_id": f"mock_{i}_{datetime.now().timestamp()}",
                "headline": headline,
                "summary": f"Mock summary for {ticker} news about recent developments.",
                "content": f"Mock full content for {headline}. This is simulated news content.",
                "url": f"https://example.com/news/{i}",
                "published_at": pub_date,
                "tickers": [ticker],
                "source": "MockNews"
            }
            articles.append(article)

        return articles

    def save_articles(self, articles: List[Dict[str, Any]], source_name: str) -> int:
        """Save mock articles to database."""
        db = db_session()
        try:
            # Get or create source
            source = db.query(NewsSource).filter(NewsSource.name == source_name).first()
            if not source:
                source = NewsSource(name=source_name, is_active=True)
                db.add(source)
                db.commit()
                db.refresh(source)

            saved_count = 0
            for article_data in articles:
                # Check if already exists
                existing = db.query(NewsArticle).filter(
                    NewsArticle.external_id == article_data["external_id"]
                ).first()
                if existing:
                    continue

                article = NewsArticle(
                    source_id=source.id,
                    external_id=article_data["external_id"],
                    headline=article_data["headline"],
                    summary=article_data.get("summary"),
                    content=article_data.get("content"),
                    url=article_data["url"],
                    published_at=article_data["published_at"],
                    is_processed=False
                )
                db.add(article)
                saved_count += 1

                # Add ticker links
                for ticker in article_data.get("tickers", []):
                    link = TickerNewsLink(
                        article_id=article.id,
                        ticker=ticker,
                        relevance_score=1.0
                    )
                    db.add(link)

            db.commit()
            return saved_count
        except Exception as e:
            db.rollback()
            raise e
        finally:
            db.close()


# Import here to avoid circular imports
from apps.api.src.db.models_news import TickerNewsLink