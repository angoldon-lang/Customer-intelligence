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

    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./app.db")

    # Email
    SMTP_SERVER: str = os.getenv("SMTP_SERVER", "smtp.gmail.com")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER: str = os.getenv("SMTP_USER", "")
    SMTP_PASSWORD: str = os.getenv("SMTP_PASSWORD", "")
    SMTP_FROM_NAME: str = os.getenv("SMTP_FROM_NAME", "Customer Intelligence Monitor")

    # Application
    DEBUG: bool = os.getenv("DEBUG", "False").lower() == "true"
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))

    # News Search
    NEWS_SEARCH_TIMEOUT: int = int(os.getenv("NEWS_SEARCH_TIMEOUT", "30"))
    NEWS_MAX_RESULTS_PER_COMPANY: int = int(os.getenv("NEWS_MAX_RESULTS_PER_COMPANY", "10"))

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
