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
    # Implicit TLS. Inferred from port 465 when not set explicitly; 587 and
    # 25 upgrade with STARTTLS instead.
    SMTP_USE_SSL: bool = os.getenv("SMTP_USE_SSL", "False").lower() == "true"
    SMTP_TIMEOUT: int = int(os.getenv("SMTP_TIMEOUT", "20"))

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

    # How far back each search looks. One setting for every provider: they
    # used to disagree (30 days for Google News and APITube, 3 months for
    # GDELT), so the same run covered different periods depending on which
    # source answered. Articles already seen are skipped anyway, so a wider
    # window costs little after the first run.
    NEWS_SEARCH_DAYS: int = int(os.getenv("NEWS_SEARCH_DAYS", "30"))

    # Remember every article ever offered, so one deleted from the archive
    # is not proposed again at the next run (and not re-classified, which
    # would also cost another Claude call). Cleared on purpose from
    # Impostazioni > Manutenzione.
    REMEMBER_DELETED_NEWS: bool = os.getenv("REMEMBER_DELETED_NEWS", "True").lower() == "true"

    # GDELT (free, no API key, always available)
    GDELT_ENABLED: bool = os.getenv("GDELT_ENABLED", "True").lower() == "true"

    # Google News RSS (free, no API key). Best coverage for small/local
    # Italian companies that GDELT/GNews rarely index.
    GOOGLE_NEWS_RSS_ENABLED: bool = os.getenv("GOOGLE_NEWS_RSS_ENABLED", "True").lower() == "true"

    # GNews.io (requires API key, used to validate/complement GDELT coverage)
    GNEWS_API_KEY: Optional[str] = os.getenv("GNEWS_API_KEY")

    # RSS / official company sources, configured via the news_sources table
    RSS_ENABLED: bool = os.getenv("RSS_ENABLED", "True").lower() == "true"

    # APITube (paid, metered). Used only for companies the free sources
    # found nothing for, and capped per run so a trial key can't be drained
    # by a single pass over the whole company list.
    APITUBE_API_KEY: Optional[str] = os.getenv("APITUBE_API_KEY")
    APITUBE_MAX_REQUESTS_PER_RUN: int = int(os.getenv("APITUBE_MAX_REQUESTS_PER_RUN", "25"))
    # Restrict to sources based in NEWS_COUNTRY. Off by default: Italian
    # companies get covered by foreign outlets too, and the language filter
    # already keeps the results relevant.
    APITUBE_COUNTRY_FILTER: bool = os.getenv("APITUBE_COUNTRY_FILTER", "False").lower() == "true"
    # Set False to query APITube for every company, not just the ones with
    # no free results (burns quota much faster).
    APITUBE_FALLBACK_ONLY: bool = os.getenv("APITUBE_FALLBACK_ONLY", "True").lower() == "true"

    # Safety cap on how many companies a single monitoring run processes.
    # With large company lists this keeps a run's duration and API usage
    # bounded; tiered scheduling (see scheduler.py) decides which companies
    # are actually due, this is just a hard ceiling per run.
    MAX_COMPANIES_PER_RUN: int = int(os.getenv("MAX_COMPANIES_PER_RUN", "200"))

    # Scheduler. SCHEDULER_ENABLED is remembered in the database once you
    # switch it from the dashboard, so the monitoring restarts by itself
    # after a server restart instead of having to be turned on by hand.
    SCHEDULER_ENABLED: bool = os.getenv("SCHEDULER_ENABLED", "False").lower() == "true"
    SCHEDULER_CHECK_INTERVAL_HOURS: int = int(os.getenv("SCHEDULER_CHECK_INTERVAL_HOURS", "24"))

    # Order the news sources are queried in, first to last. Sources not
    # listed here run last; unknown names are ignored.
    PROVIDER_ORDER: str = os.getenv(
        "PROVIDER_ORDER", "google_news_rss,rss,gdelt,gnews,apitube"
    )

    # Default Filters
    DEFAULT_COMPANY_TYPE: str = os.getenv("DEFAULT_COMPANY_TYPE", "Cliente")
    DEFAULT_COMPANY_STATUS: str = os.getenv("DEFAULT_COMPANY_STATUS", "Attiva")
    MIN_RELEVANCE_SCORE: int = int(os.getenv("MIN_RELEVANCE_SCORE", "5"))

    # Google News relaxes a quoted query when it finds few hits, so it
    # returns articles that never mention the company. When the classifier
    # says an article isn't about the company, park it as "Rifiutata"
    # instead of letting it into the flow: still visible and recoverable,
    # but out of the reports. Set False to keep the old behaviour.
    AUTO_REJECT_OFF_TOPIC: bool = os.getenv("AUTO_REJECT_OFF_TOPIC", "True").lower() == "true"
    # Confidence at or below this counts as "not about this company".
    # Confidence 1 is reserved for "not classified at all" and is excluded.
    MIN_CONFIDENCE_SCORE: int = int(os.getenv("MIN_CONFIDENCE_SCORE", "3"))

    # Report branding. Editable from Impostazioni > Personalizza report.
    BRAND_NAME: str = os.getenv("BRAND_NAME", "Customer Intelligence Report")
    BRAND_COLOR: str = os.getenv("BRAND_COLOR", "#2c3e50")
    REPORT_INTRO: str = os.getenv("REPORT_INTRO", "")
    REPORT_FOOTER: str = os.getenv(
        "REPORT_FOOTER",
        "Report generato automaticamente da Customer Intelligence Monitor.",
    )
    REPORT_SHOW_SCORES: bool = os.getenv("REPORT_SHOW_SCORES", "True").lower() == "true"

    # Dashboard
    DASHBOARD_ITEMS_PER_PAGE: int = int(os.getenv("DASHBOARD_ITEMS_PER_PAGE", "20"))

    # Authentication (single administrator). There is no default password:
    # on first run the app asks you to create one.
    AUTH_ENABLED: bool = os.getenv("AUTH_ENABLED", "True").lower() == "true"
    ADMIN_USERNAME: str = os.getenv("ADMIN_USERNAME", "admin")
    SESSION_TTL_HOURS: int = int(os.getenv("SESSION_TTL_HOURS", "12"))
    # Set to True when serving over HTTPS so the cookie is never sent in
    # clear; on http://127.0.0.1 it has to stay False or login won't stick.
    SESSION_COOKIE_SECURE: bool = os.getenv("SESSION_COOKIE_SECURE", "False").lower() == "true"

    @classmethod
    def get_api_key(cls) -> str:
        """Get API key for Claude, preferring CLAUDE_API_KEY."""
        key = cls.CLAUDE_API_KEY or cls.ANTHROPIC_API_KEY
        if not key:
            raise ValueError("No API key configured (CLAUDE_API_KEY or ANTHROPIC_API_KEY)")
        return key


settings = Settings()
