"""SQLAlchemy models for database tables."""

from datetime import datetime
from sqlalchemy import Column, String, Integer, Boolean, DateTime, ForeignKey, Text, Float
from sqlalchemy.orm import relationship
from app.database import Base


class Company(Base):
    """Company to monitor."""

    __tablename__ = "companies"

    id = Column(Integer, primary_key=True)
    company_name = Column(String(255), nullable=False, unique=True, index=True)
    relationship_type = Column(String(50), default="Unknown")  # Cliente, Fornitore, Prospect, etc.
    status = Column(String(50), default="Unknown")  # Active, Paused, Needs Review, Archived
    internal_customer_code = Column(String(50))
    company_email = Column(String(255))
    ateco_description = Column(String(255))
    tax_code = Column(String(20))
    website = Column(String(255))
    account_owner = Column(String(255))
    enrichment_status = Column(String(50), default="pending")  # pending, completed, needs_review
    last_monitored_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    news_items = relationship("NewsItem", back_populates="company", cascade="all, delete-orphan")
    clusters = relationship("CompanyCluster", back_populates="company", cascade="all, delete-orphan")


class Cluster(Base):
    """Cluster of companies for reporting."""

    __tablename__ = "clusters"

    id = Column(Integer, primary_key=True)
    cluster_name = Column(String(255), nullable=False, unique=True, index=True)
    cluster_type = Column(String(50))  # by_account_owner, by_sector, manual, etc.
    description = Column(Text)
    frequency = Column(String(50), default="weekly")  # daily, weekly, monthly, etc.
    min_relevance_score = Column(Integer, default=5)
    report_type = Column(String(50), default="summary")  # summary, full, alert, direction, account_owner
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    recipients = relationship("ClusterRecipient", back_populates="cluster", cascade="all, delete-orphan")
    companies = relationship("CompanyCluster", back_populates="cluster", cascade="all, delete-orphan")
    reports = relationship("Report", back_populates="cluster", cascade="all, delete-orphan")


class ClusterRecipient(Base):
    """Email recipients for cluster reports."""

    __tablename__ = "cluster_recipients"

    id = Column(Integer, primary_key=True)
    cluster_id = Column(Integer, ForeignKey("clusters.id"), nullable=False)
    email = Column(String(255), nullable=False)
    name = Column(String(255))
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    cluster = relationship("Cluster", back_populates="recipients")


class CompanyCluster(Base):
    """Association between companies and clusters."""

    __tablename__ = "company_clusters"

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)
    cluster_id = Column(Integer, ForeignKey("clusters.id"), nullable=False)
    assignment_type = Column(String(50))  # manual, by_account_owner, by_sector, by_type, by_rule
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    company = relationship("Company", back_populates="clusters")
    cluster = relationship("Cluster", back_populates="companies")


class NewsItem(Base):
    """News article about a company."""

    __tablename__ = "news_items"

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)
    title = Column(String(500), nullable=False)
    source_name = Column(String(255), nullable=False)
    source_type = Column(String(50))  # web, rss, official, news, etc.
    url = Column(String(500), nullable=False, unique=True)
    published_date = Column(DateTime)
    summary = Column(Text)
    category = Column(String(50))  # Investment, M&A, Financial, Management, Cybersecurity, etc.
    relevance_score = Column(Float, default=0)  # 1-10
    urgency_score = Column(Float, default=0)   # 1-10
    commercial_score = Column(Float, default=0)  # 1-10
    risk_score = Column(Float, default=0)  # 1-10
    confidence_score = Column(Float, default=0)  # 1-10
    access_status = Column(String(50), default="available")  # available, paywalled, limited, error
    license_scope = Column(String(50), default="metadata_only")  # metadata_only, summary_allowed, full_text_allowed, etc.
    status = Column(String(50), default="New")  # New, Approved, Rejected, Duplicate, Needs Review, Sent
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    company = relationship("Company", back_populates="news_items")


class NewsSource(Base):
    """Configured news source."""

    __tablename__ = "news_sources"

    id = Column(Integer, primary_key=True)
    source_name = Column(String(255), nullable=False, unique=True)
    source_type = Column(String(50))  # web, rss, api, official, etc.
    base_url = Column(String(500))
    auth_required = Column(Boolean, default=False)
    auth_method = Column(String(50))  # api_key, oauth, basic, etc.
    enabled = Column(Boolean, default=True)
    priority = Column(Integer, default=100)  # Lower number = higher priority
    license_scope = Column(String(50), default="metadata_only")
    rate_limit = Column(Integer)  # Requests per hour
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Report(Base):
    """Generated report for cluster."""

    __tablename__ = "reports"

    id = Column(Integer, primary_key=True)
    cluster_id = Column(Integer, ForeignKey("clusters.id"), nullable=False)
    period_start = Column(DateTime, nullable=False)
    period_end = Column(DateTime, nullable=False)
    subject = Column(String(500))
    body_html = Column(Text)
    body_text = Column(Text)
    status = Column(String(50), default="Draft")  # Draft, Pending Approval, Sent, Failed, Cancelled
    sent_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    cluster = relationship("Cluster", back_populates="reports")


class MonitoringRun(Base):
    """Log of monitoring execution."""

    __tablename__ = "monitoring_runs"

    id = Column(Integer, primary_key=True)
    started_at = Column(DateTime, default=datetime.utcnow)
    finished_at = Column(DateTime)
    status = Column(String(50), default="running")  # running, completed, failed, partial
    companies_processed = Column(Integer, default=0)
    news_found = Column(Integer, default=0)
    reports_generated = Column(Integer, default=0)
    errors_count = Column(Integer, default=0)
