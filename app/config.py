"""Configuration management."""

import os
from typing import Optional
from dotenv import load_dotenv

load_dotenv()


class Settings:
    """Application settings loaded from environment variables."""

    # API Keys
    CLAUDE_API_KEY: Optional[str] = os.getenv("CLAUDE_API_KEY")
    ANTHROPIC_API_KEY: Optional[str] = os.getenv("ANTHROPIC_API_KEY")

    # Classification mode:
    #   "ai"        -> classify with Claude (best quality, consumes credits)
    #   "heuristic" -> keyword-based scoring, no API calls, zero cost
    #   "off"       -> save news with neutral scores, classify manually
    CLASSIFIER_MODE: str = os.getenv("CLASSIFIER_MODE", "ai").lower()

    # Model used for AI classification. Haiku is ~5x cheaper than Sonnet and
    # plenty for scoring a short news snippet.
    CLAUDE_MODEL: str = os.getenv("CLAUDE_MODEL", "claude-haiku-4-5")

    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./app.db")

    # Email
    SMTP_HOST: str = os.getenv("SMTP_HOST", os.getenv("SMTP_SERVER", "smtp.gmail.com"))
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER: str = os.getenv("SMTP_USER", "")
    SMTP_PASSWORD: str = os.getenv("SMTP_PASSWORD", "")
    SMTP_FROM_EMAIL: str = os.getenv("SMTP_FROM_EMAIL", os.getenv("SMTP_USER", ""))
    SMTP_FROM_NAME: str = os.getenv("SMTP_FROM_NAME", "Customer Intelligence Monitor")

    # Application
    DEBUG: bool = os.getenv("DEBUG", "False").lower() == "true"
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))

    # News Search
    NEWS_SEARCH_TIMEOUT: int = int(os.getenv("NEWS_SEARCH_TIMEOUT", "30"))
    NEWS_MAX_RESULTS_PER_COMPANY: int = int(os.getenv("NEWS_MAX_RESULTS_PER_COMPANY", "10"))
    NEWS_LANGUAGE: str = os.getenv("NEWS_LANGUAGE", "it")
    NEWS_COUNTRY: str = os.getenv("NEWS_COUNTRY", "IT")

    # GDELT (free, no API key, always available)
    GDELT_ENABLED: bool = os.getenv("GDELT_ENABLED", "True").lower() == "true"

    # Google News RSS (free, no API key). Best coverage for small/local
    # Italian companies that GDELT/GNews rarely index.
    GOOGLE_NEWS_RSS_ENABLED: bool = os.getenv("GOOGLE_NEWS_RSS_ENABLED", "True").lower() == "true"

    # GNews.io (requires API key, used to validate/complement GDELT coverage)
    GNEWS_API_KEY: Optional[str] = os.getenv("GNEWS_API_KEY")

    # RSS / official company sources, configured via the news_sources table
    RSS_ENABLED: bool = os.getenv("RSS_ENABLED", "True").lower() == "true"

    # Safety cap on how many companies a single monitoring run processes.
    # With large company lists this keeps a run's duration and API usage
    # bounded; tiered scheduling (see scheduler.py) decides which companies
    # are actually due, this is just a hard ceiling per run.
    MAX_COMPANIES_PER_RUN: int = int(os.getenv("MAX_COMPANIES_PER_RUN", "200"))

    # Scheduler
    SCHEDULER_ENABLED: bool = os.getenv("SCHEDULER_ENABLED", "True").lower() == "true"
    SCHEDULER_CHECK_INTERVAL_HOURS: int = int(os.getenv("SCHEDULER_CHECK_INTERVAL_HOURS", "24"))

    # Default Filters
    DEFAULT_COMPANY_TYPE: str = os.getenv("DEFAULT_COMPANY_TYPE", "Cliente")
    DEFAULT_COMPANY_STATUS: str = os.getenv("DEFAULT_COMPANY_STATUS", "Attiva")
    MIN_RELEVANCE_SCORE: int = int(os.getenv("MIN_RELEVANCE_SCORE", "5"))

    # Dashboard
    DASHBOARD_ITEMS_PER_PAGE: int = int(os.getenv("DASHBOARD_ITEMS_PER_PAGE", "20"))

    @classmethod
    def get_api_key(cls) -> str:
        """Get API key for Claude, preferring CLAUDE_API_KEY."""
        key = cls.CLAUDE_API_KEY or cls.ANTHROPIC_API_KEY
        if not key:
            raise ValueError("No API key configured (CLAUDE_API_KEY or ANTHROPIC_API_KEY)")
        return key


settings = Settings()
