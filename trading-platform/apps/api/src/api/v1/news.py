"""
News and Catalyst API Endpoints.
"""
from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from apps.api.src.core.database import get_db as get_db_session
from apps.api.src.db.models_news import NewsArticle, NewsEvent, CatalystScore, TickerNewsLink
from services.data.news_provider import MockNewsProvider
from services.news.event_extractor import NewsEventExtractor


router = APIRouter(prefix="/news", tags=["news"])


@router.get("/articles")
def get_articles(
    ticker: Optional[str] = Query(None, description="Filter by ticker"),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db_session)
):
    """Get recent news articles, optionally filtered by ticker."""
    query = db.query(NewsArticle).order_by(NewsArticle.published_at.desc())

    if ticker:
        query = query.join(TickerNewsLink).filter(TickerNewsLink.ticker == ticker)

    articles = query.limit(limit).all()

    return [
        {
            "id": a.id,
            "headline": a.headline,
            "summary": a.summary,
            "published_at": a.published_at.isoformat(),
            "url": a.url,
            "tickers": [link.ticker for link in a.ticker_links],
            "is_processed": a.is_processed
        }
        for a in articles
    ]


@router.get("/events")
def get_events(
    ticker: str = Query(..., description="Ticker to filter events"),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db_session)
):
    """Get structured news events for a specific ticker."""
    events = db.query(NewsEvent).filter(
        NewsEvent.ticker == ticker
    ).order_by(NewsEvent.created_at.desc()).limit(limit).all()

    return [
        {
            "id": e.id,
            "ticker": e.ticker,
            "event_type": e.event_type,
            "sentiment_score": e.sentiment_score,
            "importance_score": e.importance_score,
            "surprise_magnitude": e.surprise_magnitude,
            "expected_duration": e.expected_duration,
            "extracted_catalysts": e.extracted_catalysts,
            "headline": e.article.headline,
            "published_at": e.article.published_at.isoformat()
        }
        for e in events
    ]


@router.get("/catalyst-scores")
def get_catalyst_scores(
    ticker: Optional[str] = Query(None, description="Filter by ticker"),
    start_date: Optional[datetime] = Query(None, description="Start date"),
    end_date: Optional[datetime] = Query(None, description="End date"),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db_session)
):
    """Get aggregated daily catalyst scores."""
    query = db.query(CatalystScore)

    if ticker:
        query = query.filter(CatalystScore.ticker == ticker)

    if start_date:
        query = query.filter(CatalystScore.date >= start_date)

    if end_date:
        query = query.filter(CatalystScore.date <= end_date)

    scores = query.order_by(CatalystScore.date.desc()).limit(limit).all()

    return [
        {
            "ticker": s.ticker,
            "date": s.date.isoformat(),
            "composite_score": s.composite_score,
            "net_sentiment": s.net_sentiment,
            "max_importance": s.max_importance,
            "event_count": s.event_count,
            "bullish_events": s.bullish_events,
            "bearish_events": s.bearish_events
        }
        for s in scores
    ]


@router.post("/ingest")
def ingest_news(
    tickers: Optional[List[str]] = Query(None, description="Tickers to fetch news for"),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db_session)
):
    """Ingest news articles using the configured provider."""
    provider = MockNewsProvider()

    # Fetch articles
    articles = provider.fetch_articles(tickers=tickers, limit=limit)

    # Save to database
    saved_count = provider.save_articles(articles, source_name="MockNews")

    return {
        "fetched": len(articles),
        "saved": saved_count,
        "message": f"Successfully ingested {saved_count} new articles"
    }


@router.post("/process-events")
def process_news_events(
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db_session)
):
    """Process unprocessed articles and extract structured events."""
    extractor = NewsEventExtractor(use_llm=False)  # Use rule-based for now

    processed_count = extractor.process_unprocessed_articles(limit=limit)

    return {
        "processed": processed_count,
        "message": f"Successfully processed {processed_count} articles"
    }


@router.post("/calculate-catalyst-scores")
def calculate_catalyst_scores(
    date: datetime = Query(None, description="Date to calculate scores for (defaults to today)"),
    db: Session = Depends(get_db_session)
):
    """Calculate daily catalyst scores for all tickers."""
    if date is None:
        date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    extractor = NewsEventExtractor(use_llm=False)
    scores_count = extractor.calculate_daily_catalyst_scores(date=date)

    return {
        "scores_created": scores_count,
        "date": date.isoformat(),
        "message": f"Calculated catalyst scores for {scores_count} tickers on {date.date()}"
    }


@router.get("/{ticker}/summary")
def get_ticker_news_summary(
    ticker: str,
    days: int = Query(7, ge=1, le=30),
    db: Session = Depends(get_db_session)
):
    """Get a summary of recent news and catalyst activity for a ticker."""
    from datetime import timedelta
    start_date = datetime.now() - timedelta(days=days)

    # Get recent events
    events = db.query(NewsEvent).join(NewsArticle).filter(
        NewsEvent.ticker == ticker,
        NewsArticle.published_at >= start_date
    ).all()

    if not events:
        return {
            "ticker": ticker,
            "period_days": days,
            "message": "No news events found",
            "event_count": 0
        }

    # Calculate summary statistics
    bullish = sum(1 for e in events if e.sentiment_score > 0.2)
    bearish = sum(1 for e in events if e.sentiment_score < -0.2)
    neutral = len(events) - bullish - bearish

    avg_sentiment = sum(e.sentiment_score for e in events) / len(events)
    max_importance = max(e.importance_score for e in events)

    event_types = {}
    for e in events:
        event_types[e.event_type] = event_types.get(e.event_type, 0) + 1

    return {
        "ticker": ticker,
        "period_days": days,
        "event_count": len(events),
        "bullish_count": bullish,
        "bearish_count": bearish,
        "neutral_count": neutral,
        "average_sentiment": round(avg_sentiment, 3),
        "max_importance": max_importance,
        "event_type_breakdown": event_types,
        "recent_headlines": [
            {
                "headline": e.article.headline,
                "event_type": e.event_type,
                "sentiment": e.sentiment_score,
                "published_at": e.article.published_at.isoformat()
            }
            for e in sorted(events, key=lambda x: x.article.published_at, reverse=True)[:5]
        ]
    }