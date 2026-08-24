"""FastAPI application entry point."""

from fastapi import FastAPI, UploadFile, File, Depends, HTTPException, Request, Body
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from datetime import datetime, timedelta
import os

from app import __version__
from app.config import settings
from app.database import init_db, get_db
from sqlalchemy import func
from app.models import Company, Cluster, NewsItem, Report, MonitoringRun, NewsSource, CompanyCluster, ClusterRecipient, SearchLog, AppSetting
from app.services import settings_store
from app.services import DataImporter, DataNormalizer, ClusterManager
from app.services.classifier import NewsClassifier
from app.services.reporter import ReportGenerator
from app.services.news_searcher import NewsSearcher
from app.services.scheduler import monitoring_scheduler
from app.services.email_sender import EmailSender
from app.providers import MockNewsProvider

# Initialize database tables
init_db()


def _check_anthropic_sdk() -> str:
    """
    Warn loudly at startup if the installed anthropic SDK is too old.

    Versions before 0.8 have no Messages API at all (only the legacy
    `client.completions`), so every classification call fails with
    "'Anthropic' object has no attribute 'messages'" - once per article,
    buried in the logs, with no other symptom than news never being
    classified. Surface it once, up front, instead.
    """
    try:
        import anthropic
        version = getattr(anthropic, "__version__", "unknown")
    except ImportError:
        print("\n  ATTENZIONE: pacchetto 'anthropic' non installato.")
        print("  Esegui: pip install -r requirements.txt\n")
        return "not installed"

    if not hasattr(anthropic.Anthropic, "messages"):
        print("\n" + "=" * 72)
        print(f"  ATTENZIONE: anthropic SDK {version} e' troppo vecchia (manca la Messages API).")
        print("  La classificazione AI delle notizie fallira' per OGNI notizia trovata.")
        print("  Risolvi con:  pip install -r requirements.txt")
        print("=" * 72 + "\n")
    return version


ANTHROPIC_SDK_VERSION = _check_anthropic_sdk()

app = FastAPI(
    title="Customer Intelligence Monitor",
    description="Monitor news and intelligence about companies",
    version=__version__,
)


@app.exception_handler(Exception)
def unhandled_exception_handler(request: Request, exc: Exception):
    """
    Always answer with JSON, never a bare text/HTML 500.

    The dashboard does `await response.json()` on every call, so an
    unhandled server error used to surface in the browser as the useless
    "JSON.parse: unexpected character at line 1 column 1".
    """
    print(f"[ERROR] {request.method} {request.url.path}: {type(exc).__name__}: {exc}")
    return JSONResponse(status_code=500, content={"detail": f"Errore interno: {exc}"})


@app.on_event("startup")
def on_startup():
    """Load settings saved from the dashboard over the .env defaults."""
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        settings_store.apply_to_runtime(db)
    except Exception as e:
        print(f"[WARN] Impossibile caricare le impostazioni salvate: {e}")
    finally:
        db.close()


@app.on_event("shutdown")
def on_shutdown():
    """Stop background jobs so the process can exit cleanly on Ctrl+C."""
    monitoring_scheduler.stop()

# Setup templates
templates = Jinja2Templates(directory="app/templates")

# Mount static files if they exist
if os.path.exists("app/static"):
    app.mount("/static", StaticFiles(directory="app/static"), name="static")

# starlette changed Jinja2Templates.TemplateResponse's signature from
# (name, context) to (request, name, context) between versions. Calling it
# the old way on a newer starlette silently misassigns arguments (the
# context dict lands where `name` is expected), which surfaces deep inside
# Jinja2 as a baffling "TypeError: unhashable type: 'dict'". Detect which
# signature is installed once, so page routes work either way.
import inspect as _inspect
_template_response_params = list(_inspect.signature(templates.TemplateResponse).parameters)
_REQUEST_FIRST = bool(_template_response_params) and _template_response_params[0] == "request"


def render(request: Request, name: str, context: dict = None) -> HTMLResponse:
    """Render a Jinja2 template, compatible with old and new starlette."""
    context = dict(context or {})
    if _REQUEST_FIRST:
        return templates.TemplateResponse(request, name, context)
    context["request"] = request
    return templates.TemplateResponse(name, context)


# ============================================================================
# Page Routes - HTML Templates
# ============================================================================

@app.get("/", response_class=HTMLResponse)
def read_root(request: Request):
    """Root endpoint - dashboard."""
    return render(request, "index.html")


@app.get("/api/health")
def health_check(db: Session = Depends(get_db)):
    """Health check endpoint."""
    return {
        "status": "ok",
        "database": True,
        "api": bool(settings.CLAUDE_API_KEY or settings.ANTHROPIC_API_KEY),
        "version": __version__,
        "anthropic_sdk": ANTHROPIC_SDK_VERSION,
        "anthropic_sdk_ok": NewsClassifier.sdk_supports_messages(),
    }


@app.post("/api/import")
async def import_data(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Import company data from Excel or CSV file."""
    importer = DataImporter()

    try:
        content = await file.read()
        result = importer.import_file(content, file.filename)

        # Save companies to database
        added_count = 0
        duplicate_count = 0
        error_companies = []

        for company_data in result["companies"]:
            try:
                existing = db.query(Company).filter_by(company_name=company_data["company_name"]).first()
                if not existing:
                    company = Company(**company_data)
                    db.add(company)
                    db.flush()
                    added_count += 1
                else:
                    duplicate_count += 1
            except IntegrityError:
                db.rollback()
                duplicate_count += 1
                error_companies.append(company_data["company_name"])

        db.commit()

        result["added_to_database"] = added_count
        result["duplicate_companies"] = duplicate_count
        if error_companies:
            result["skipped_duplicates"] = error_companies
        return result

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/companies")
def list_companies(db: Session = Depends(get_db)):
    """List all companies."""
    companies = db.query(Company).all()
    return {
        "total": len(companies),
        "companies": [
            {
                "id": c.id,
                "company_name": c.company_name,
                "relationship_type": c.relationship_type,
                "status": c.status,
                "website": c.website,
                "account_owner": c.account_owner,
            }
            for c in companies
        ]
    }


@app.put("/api/companies/{company_id}")
def update_company(
    company_id: int,
    company_name: str = None,
    relationship_type: str = None,
    status: str = None,
    company_email: str = None,
    ateco_description: str = None,
    tax_code: str = None,
    website: str = None,
    account_owner: str = None,
    db: Session = Depends(get_db)
):
    """Edit an existing company."""
    company = db.query(Company).filter_by(id=company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    for field, value in [
        ("company_name", company_name),
        ("relationship_type", relationship_type),
        ("status", status),
        ("company_email", company_email),
        ("ateco_description", ateco_description),
        ("tax_code", tax_code),
        ("website", website),
        ("account_owner", account_owner),
    ]:
        if value is not None:
            setattr(company, field, value)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="A company with this name already exists")

    return {"id": company.id, "company_name": company.company_name, "message": "Company updated successfully"}


@app.delete("/api/companies/{company_id}")
def delete_company(company_id: int, db: Session = Depends(get_db)):
    """Delete a company (and its news items / cluster assignments)."""
    company = db.query(Company).filter_by(id=company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    db.delete(company)
    db.commit()
    return {"message": "Company deleted"}


@app.get("/api/coverage")
def get_search_coverage(status: str = None, search: str = None, db: Session = Depends(get_db)):
    """
    Per-company search coverage: last time it was searched, on which
    providers, whether anything was found, and if not why (no results vs
    blocked vs skipped as ambiguous vs error vs never searched at all).
    """
    latest_ids = (
        db.query(SearchLog.company_id, func.max(SearchLog.id).label("max_id"))
        .group_by(SearchLog.company_id)
        .subquery()
    )
    latest_logs = (
        db.query(SearchLog)
        .join(latest_ids, SearchLog.id == latest_ids.c.max_id)
        .all()
    )
    logs_by_company = {log.company_id: log for log in latest_logs}

    query = db.query(Company)
    if search:
        query = query.filter(Company.company_name.ilike(f"%{search}%"))
    companies = query.order_by(Company.company_name).all()

    # How many news items are actually stored per company, so the page can
    # link straight to them instead of only reporting the last run's count.
    stored_counts = dict(
        db.query(NewsItem.company_id, func.count(NewsItem.id))
        .group_by(NewsItem.company_id)
        .all()
    )

    coverage = []
    for c in companies:
        log = logs_by_company.get(c.id)
        row_status = log.status if log else "never_searched"
        if status and status != row_status:
            continue
        coverage.append({
            "company_id": c.id,
            "company_name": c.company_name,
            "last_searched_at": log.searched_at.isoformat() if log else None,
            "status": row_status,
            "articles_found": log.articles_found if log else 0,
            "news_in_archive": stored_counts.get(c.id, 0),
            "providers_detail": log.providers_detail if log else None,
            "error_message": log.error_message if log else None,
        })

    return {"total": len(coverage), "coverage": coverage}


@app.delete("/api/coverage")
def clear_search_logs(only_failed: bool = True, db: Session = Depends(get_db)):
    """
    Clear the search-coverage history.

    Old rows keep showing failures from runs that are long over (rate
    limits, providers disabled mid-run). By default only those are cleared,
    so successful entries stay; pass only_failed=false to wipe everything.
    """
    query = db.query(SearchLog)
    if only_failed:
        query = query.filter(SearchLog.status.in_(["blocked", "error", "no_results"]))
    deleted = query.delete(synchronize_session=False)
    db.commit()
    return {"deleted": deleted, "message": "Storico ricerche pulito"}


@app.get("/api/clusters")
def list_clusters(db: Session = Depends(get_db)):
    """List all clusters."""
    clusters = db.query(Cluster).all()
    return {
        "total": len(clusters),
        "clusters": [
            {
                "id": c.id,
                "cluster_name": c.cluster_name,
                "cluster_type": c.cluster_type,
                "frequency": c.frequency,
                "active": c.active,
                "company_count": len(c.companies),
            }
            for c in clusters
        ]
    }


@app.post("/api/clusters")
def create_cluster(
    cluster_name: str,
    cluster_type: str = "manual",
    frequency: str = "weekly",
    db: Session = Depends(get_db)
):
    """Create new cluster."""
    manager = ClusterManager()
    cluster = manager.create_cluster(
        db,
        cluster_name=cluster_name,
        cluster_type=cluster_type,
        frequency=frequency,
    )
    return {
        "id": cluster.id,
        "cluster_name": cluster.cluster_name,
        "message": "Cluster created successfully"
    }


@app.put("/api/clusters/{cluster_id}")
def update_cluster(
    cluster_id: int,
    cluster_name: str = None,
    frequency: str = None,
    min_relevance_score: int = None,
    active: bool = None,
    db: Session = Depends(get_db)
):
    """Edit an existing cluster's settings."""
    cluster = db.query(Cluster).filter_by(id=cluster_id).first()
    if not cluster:
        raise HTTPException(status_code=404, detail="Cluster not found")

    for field, value in [
        ("cluster_name", cluster_name),
        ("frequency", frequency),
        ("min_relevance_score", min_relevance_score),
        ("active", active),
    ]:
        if value is not None:
            setattr(cluster, field, value)

    db.commit()
    return {"id": cluster.id, "cluster_name": cluster.cluster_name, "message": "Cluster updated successfully"}


@app.delete("/api/clusters/{cluster_id}")
def delete_cluster(cluster_id: int, db: Session = Depends(get_db)):
    """Delete a cluster (and its recipients / company assignments / reports)."""
    cluster = db.query(Cluster).filter_by(id=cluster_id).first()
    if not cluster:
        raise HTTPException(status_code=404, detail="Cluster not found")
    db.delete(cluster)
    db.commit()
    return {"message": "Cluster deleted"}


@app.get("/api/clusters/{cluster_id}/companies")
def get_cluster_companies(cluster_id: int, db: Session = Depends(get_db)):
    """List companies assigned to a cluster."""
    cluster = db.query(Cluster).filter_by(id=cluster_id).first()
    if not cluster:
        raise HTTPException(status_code=404, detail="Cluster not found")

    manager = ClusterManager()
    companies = manager.get_companies_for_cluster(db, cluster_id)
    return {
        "total": len(companies),
        "companies": [
            {"id": c.id, "company_name": c.company_name, "relationship_type": c.relationship_type}
            for c in companies
        ]
    }


@app.post("/api/clusters/{cluster_id}/companies")
def add_company_to_cluster(cluster_id: int, company_id: int, db: Session = Depends(get_db)):
    """Manually assign a company to a cluster."""
    cluster = db.query(Cluster).filter_by(id=cluster_id).first()
    if not cluster:
        raise HTTPException(status_code=404, detail="Cluster not found")
    company = db.query(Company).filter_by(id=company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    manager = ClusterManager()
    manager.assign_company_to_cluster(db, company_id, cluster_id, assignment_type="manual")
    return {"message": f"{company.company_name} added to {cluster.cluster_name}"}


@app.delete("/api/clusters/{cluster_id}/companies/{company_id}")
def remove_company_from_cluster(cluster_id: int, company_id: int, db: Session = Depends(get_db)):
    """Remove a company from a cluster."""
    assignment = db.query(CompanyCluster).filter_by(cluster_id=cluster_id, company_id=company_id).first()
    if not assignment:
        raise HTTPException(status_code=404, detail="Company is not in this cluster")
    db.delete(assignment)
    db.commit()
    return {"message": "Company removed from cluster"}


@app.get("/api/clusters/{cluster_id}/recipients")
def get_cluster_recipients(cluster_id: int, db: Session = Depends(get_db)):
    """List email recipients for a cluster."""
    cluster = db.query(Cluster).filter_by(id=cluster_id).first()
    if not cluster:
        raise HTTPException(status_code=404, detail="Cluster not found")

    recipients = db.query(ClusterRecipient).filter_by(cluster_id=cluster_id).all()
    return {
        "total": len(recipients),
        "recipients": [
            {"id": r.id, "email": r.email, "name": r.name, "active": r.active}
            for r in recipients
        ]
    }


@app.delete("/api/clusters/{cluster_id}/recipients/{recipient_id}")
def remove_cluster_recipient(cluster_id: int, recipient_id: int, db: Session = Depends(get_db)):
    """Remove an email recipient from a cluster."""
    recipient = db.query(ClusterRecipient).filter_by(id=recipient_id, cluster_id=cluster_id).first()
    if not recipient:
        raise HTTPException(status_code=404, detail="Recipient not found")
    db.delete(recipient)
    db.commit()
    return {"message": "Recipient removed"}


@app.post("/api/auto-clusters")
def auto_create_clusters(db: Session = Depends(get_db)):
    """Auto-create clusters from company attributes."""
    manager = ClusterManager()
    companies = db.query(Company).all()
    created = manager.create_auto_clusters(db, companies)
    return {
        "created": len(created),
        "message": f"Created {len(created)} clusters"
    }


@app.post("/api/clusters/{cluster_id}/recipients")
def add_cluster_recipient(
    cluster_id: int,
    email: str,
    name: str = None,
    db: Session = Depends(get_db)
):
    """Add recipient to cluster."""
    manager = ClusterManager()
    recipient = manager.add_recipient(db, cluster_id, email, name)
    return {
        "id": recipient.id,
        "email": recipient.email,
        "message": "Recipient added successfully"
    }


@app.get("/api/news")
def list_news(
    status: str = None,
    category: str = None,
    company_id: int = None,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    """List news items with optional filters."""
    query = db.query(NewsItem)

    if status:
        query = query.filter_by(status=status)
    if category:
        query = query.filter_by(category=category)
    if company_id:
        query = query.filter_by(company_id=company_id)

    total = query.count()
    news = query.order_by(NewsItem.created_at.desc()).limit(limit).all()

    return {
        "total": total,
        "returned": len(news),
        "news": [
            {
                "id": n.id,
                "title": n.title,
                "company_name": n.company.company_name if n.company else "-",
                "category": n.category,
                # url was missing here, so every "Leggi"/source link in the
                # news page rendered as undefined
                "url": n.url,
                "summary": n.summary,
                "published_date": n.published_date.isoformat() if n.published_date else None,
                "relevance_score": n.relevance_score,
                "confidence_score": n.confidence_score,
                "status": n.status,
                "source_name": n.source_name,
            }
            for n in news
        ]
    }


@app.put("/api/news/{news_id}/company")
def reassign_news_company(news_id: int, company_id: int, db: Session = Depends(get_db)):
    """
    Move a news item to a different company.

    Searches match on company name, so a headline about a peer ("BPER
    Banca...") can legitimately come back under another bank. Rather than
    just rejecting it, reassign it to the company it really concerns.
    """
    news = db.query(NewsItem).filter_by(id=news_id).first()
    if not news:
        raise HTTPException(status_code=404, detail="News item not found")

    company = db.query(Company).filter_by(id=company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    news.company_id = company.id
    # The scores were computed against the old company, so they no longer
    # mean anything - flag it for a fresh classification.
    news.status = "Needs Review"
    news.confidence_score = 1
    db.commit()

    return {
        "id": news.id,
        "company_name": company.company_name,
        "message": f"Notizia riassegnata a {company.company_name}",
    }


@app.post("/api/news/bulk-status")
def bulk_update_news_status(payload: dict = Body(...), db: Session = Depends(get_db)):
    """Approve/reject many news items at once. Body: {ids: [...], status: "..."}"""
    ids = payload.get("ids") or []
    status = payload.get("status")

    valid = ["New", "Approved", "Rejected", "Duplicate", "Needs Review", "Sent"]
    if status not in valid:
        raise HTTPException(status_code=400, detail=f"Stato non valido, usa uno tra {valid}")
    if not ids:
        raise HTTPException(status_code=400, detail="Nessuna notizia selezionata")

    updated = (
        db.query(NewsItem)
        .filter(NewsItem.id.in_(ids))
        .update({NewsItem.status: status}, synchronize_session=False)
    )
    db.commit()
    return {"updated": updated, "status": status, "message": f"{updated} notizie aggiornate"}


@app.delete("/api/news")
def delete_news(status: str = None, ids: str = None, db: Session = Depends(get_db)):
    """
    Delete news items permanently.

    Pass status=Rejected to clear out everything already rejected, or a
    comma-separated `ids` list to remove specific items.
    """
    query = db.query(NewsItem)
    if ids:
        id_list = [int(i) for i in ids.split(",") if i.strip().isdigit()]
        if not id_list:
            raise HTTPException(status_code=400, detail="Nessun id valido")
        query = query.filter(NewsItem.id.in_(id_list))
    elif status:
        query = query.filter_by(status=status)
    else:
        raise HTTPException(status_code=400, detail="Specifica status oppure ids")

    deleted = query.delete(synchronize_session=False)
    db.commit()
    return {"deleted": deleted, "message": f"{deleted} notizie eliminate"}


@app.post("/api/news/{news_id}/reclassify")
def reclassify_news(news_id: int, db: Session = Depends(get_db)):
    """
    Re-run AI classification on an existing news item.

    Useful for items saved with the neutral fallback because Claude wasn't
    reachable at monitoring time (missing/invalid API key, stale SDK).
    """
    news = db.query(NewsItem).filter_by(id=news_id).first()
    if not news:
        raise HTTPException(status_code=404, detail="News item not found")

    classifier = NewsClassifier()
    if not classifier.client:
        raise HTTPException(
            status_code=400,
            detail="Nessuna API key Claude configurata: impossibile riclassificare",
        )

    company = news.company
    try:
        classification = classifier.classify_news(
            company_name=company.company_name if company else "",
            title=news.title,
            url=news.url,
            source_name=news.source_name,
            article_text=news.summary,
            ateco_description=company.ateco_description if company else None,
            account_owner=company.account_owner if company else None,
            website=company.website if company else None,
            tax_code=company.tax_code if company else None,
        )
    except Exception as e:
        reason = NewsClassifier._fatal_reason(e)
        if reason:
            raise HTTPException(
                status_code=402,
                detail=f"{reason}. Risolvi su console.anthropic.com, poi riprova.",
            )
        raise HTTPException(status_code=502, detail=f"Classificazione fallita: {e}")

    news.summary = classification.get("summary") or news.summary
    news.category = classification.get("category", news.category)
    news.relevance_score = classification.get("relevance_score", news.relevance_score)
    news.urgency_score = classification.get("urgency_score", news.urgency_score)
    news.commercial_score = classification.get("commercial_score", news.commercial_score)
    news.risk_score = classification.get("risk_score", news.risk_score)
    news.confidence_score = classification.get("confidence_score", news.confidence_score)
    if news.status == "Needs Review":
        news.status = "New"
    db.commit()

    return {"id": news.id, "category": news.category, "message": "News reclassified"}


@app.post("/api/news/{news_id}/status")
def update_news_status(news_id: int, status: str, db: Session = Depends(get_db)):
    """Update a news item's status (Approved, Rejected, Needs Review, ...)."""
    valid_statuses = ["New", "Approved", "Rejected", "Duplicate", "Needs Review", "Sent"]
    if status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"Invalid status, must be one of {valid_statuses}")

    news = db.query(NewsItem).filter_by(id=news_id).first()
    if not news:
        raise HTTPException(status_code=404, detail="News item not found")

    news.status = status
    db.commit()
    return {"id": news.id, "status": news.status, "message": "News status updated"}


@app.get("/api/reports")
def list_reports(
    status: str = None,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    """List generated reports."""
    query = db.query(Report)

    if status:
        query = query.filter_by(status=status)

    reports = query.order_by(Report.created_at.desc()).limit(limit).all()

    return {
        "total": len(reports),
        "reports": [
            {
                "id": r.id,
                "cluster_name": r.cluster.cluster_name if r.cluster else "-",
                "period_start": r.period_start.isoformat(),
                "period_end": r.period_end.isoformat(),
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "status": r.status,
                "subject": r.subject,
            }
            for r in reports
        ]
    }


@app.get("/api/reports/schedule")
def get_report_schedule(db: Session = Depends(get_db)):
    """
    Per-cluster automatic delivery schedule.

    Declared before /api/reports/{report_id} on purpose: FastAPI matches
    routes in registration order and "schedule" would otherwise be parsed
    as a report id.
    """
    from app.services.report_scheduler import (
        FREQUENCY_DAYS, DEFAULT_FREQUENCY_DAYS, cluster_is_due,
    )

    labels = {
        "daily": "Giornaliera",
        "2-3x_week": "2-3 volte a settimana",
        "weekly": "Settimanale",
        "monthly": "Mensile",
    }

    clusters = db.query(Cluster).order_by(Cluster.cluster_name).all()
    now = datetime.utcnow()
    rows = []

    for c in clusters:
        recipients = [r.email for r in c.recipients if r.email and r.active]
        last_sent = (
            db.query(Report)
            .filter(Report.cluster_id == c.id, Report.status == "Sent")
            .order_by(Report.sent_at.desc())
            .first()
        )
        days = FREQUENCY_DAYS.get(c.frequency, DEFAULT_FREQUENCY_DAYS)
        next_due = None
        if last_sent and last_sent.sent_at:
            next_due = (last_sent.sent_at + timedelta(days=days)).isoformat()

        rows.append({
            "cluster_id": c.id,
            "cluster_name": c.cluster_name,
            "active": c.active,
            "frequency": c.frequency,
            "frequency_label": labels.get(c.frequency, c.frequency or "-"),
            "period_days": days,
            "recipients": recipients,
            "recipients_count": len(recipients),
            "last_sent_at": last_sent.sent_at.isoformat() if last_sent and last_sent.sent_at else None,
            "next_due_at": next_due,
            "is_due": bool(c.active and recipients and cluster_is_due(db, c, now)),
        })

    return {
        "scheduler_running": monitoring_scheduler.is_running,
        "total": len(rows),
        "clusters": rows,
    }


@app.get("/api/reports/{report_id}")
def get_report(report_id: int, db: Session = Depends(get_db)):
    """Get a single report including its rendered HTML body (for preview)."""
    report = db.query(Report).filter_by(id=report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    return {
        "id": report.id,
        "cluster_name": report.cluster.cluster_name if report.cluster else "-",
        "period_start": report.period_start.isoformat(),
        "period_end": report.period_end.isoformat(),
        "created_at": report.created_at.isoformat() if report.created_at else None,
        "status": report.status,
        "subject": report.subject,
        "body_html": report.body_html,
    }


# ============================================================================
# Phase 2 - News Monitoring
# ============================================================================

@app.post("/api/monitoring/start")
def start_monitoring(
    interval_hours: int = 24,
    db: Session = Depends(get_db)
):
    """Start automatic news monitoring."""
    monitoring_scheduler.start(interval_hours)
    return {
        "status": "started",
        "interval_hours": interval_hours,
        "message": "News monitoring started"
    }


@app.post("/api/monitoring/stop")
def stop_monitoring():
    """Stop automatic news monitoring."""
    monitoring_scheduler.stop()
    return {
        "status": "stopped",
        "message": "News monitoring stopped"
    }


@app.post("/api/monitoring/run-now")
def run_monitoring_now(limit: int = None):
    """
    Start a monitoring run in the background and return immediately.

    A run can take minutes on a large company list (GDELT/GNews are
    rate-limited client-side), so this no longer blocks the HTTP request -
    poll GET /api/monitoring/status for progress and results.

    `limit` restricts this run to at most N due companies (overrides
    MAX_COMPANIES_PER_RUN for this run only) - useful to quickly test on a
    handful of companies instead of waiting on the full list.
    """
    started = monitoring_scheduler.run_now_async(limit=limit)
    if not started:
        raise HTTPException(status_code=409, detail="A monitoring run is already in progress")
    return {"status": "started", "message": "Monitoring run started in background"}


@app.get("/api/monitoring/status")
def get_monitoring_status(db: Session = Depends(get_db)):
    """Get monitoring status."""
    last_run = db.query(MonitoringRun).order_by(MonitoringRun.finished_at.desc()).first()

    return {
        "is_running": monitoring_scheduler.is_running,
        "interval_hours": monitoring_scheduler.interval_hours,
        "run_in_progress": monitoring_scheduler.run_in_progress,
        "classification_issue": monitoring_scheduler.last_classification_issue,
        "last_run": {
            "finished_at": last_run.finished_at.isoformat() if last_run else None,
            "companies_checked": last_run.companies_processed if last_run else 0,
            "news_found": last_run.news_found if last_run else 0,
            "news_saved": last_run.news_found if last_run else 0,
            "status": last_run.status if last_run else "Never run",
        } if last_run else {}
    }


@app.get("/api/monitoring/history")
def get_monitoring_history(limit: int = 10, db: Session = Depends(get_db)):
    """Get monitoring run history."""
    runs = db.query(MonitoringRun).order_by(MonitoringRun.finished_at.desc()).limit(limit).all()

    return {
        "total": len(runs),
        "runs": [
            {
                "finished_at": r.finished_at.isoformat() if r.finished_at else None,
                "companies_checked": r.companies_processed,
                "news_found": r.news_found,
                "news_saved": r.news_found,
                "status": r.status,
            }
            for r in runs
        ]
    }


@app.get("/api/monitoring/providers")
def get_providers_status(db: Session = Depends(get_db)):
    """Report which news providers are active, for the settings page."""
    rss_count = db.query(NewsSource).filter_by(source_type="rss", enabled=True).count()
    return {
        "google_news_rss": {"enabled": settings.GOOGLE_NEWS_RSS_ENABLED, "requires_key": False},
        "gdelt": {"enabled": settings.GDELT_ENABLED, "requires_key": False},
        "gnews": {"enabled": bool(settings.GNEWS_API_KEY), "requires_key": True},
        "rss": {"enabled": settings.RSS_ENABLED and rss_count > 0, "active_feeds": rss_count},
    }


@app.get("/api/news-sources")
def list_news_sources(db: Session = Depends(get_db)):
    """List configured news sources (RSS/official feeds)."""
    sources = db.query(NewsSource).order_by(NewsSource.priority).all()
    return {
        "total": len(sources),
        "sources": [
            {
                "id": s.id,
                "source_name": s.source_name,
                "source_type": s.source_type,
                "base_url": s.base_url,
                "enabled": s.enabled,
                "priority": s.priority,
                "license_scope": s.license_scope,
            }
            for s in sources
        ]
    }


@app.post("/api/news-sources")
def create_news_source(
    source_name: str,
    base_url: str,
    source_type: str = "rss",
    priority: int = 100,
    license_scope: str = "summary_allowed",
    db: Session = Depends(get_db)
):
    """Add a news source (typically an official company/IR RSS feed)."""
    existing = db.query(NewsSource).filter_by(source_name=source_name).first()
    if existing:
        raise HTTPException(status_code=400, detail="A source with this name already exists")

    source = NewsSource(
        source_name=source_name,
        source_type=source_type,
        base_url=base_url,
        enabled=True,
        priority=priority,
        license_scope=license_scope,
    )
    db.add(source)
    db.commit()
    db.refresh(source)
    return {"id": source.id, "source_name": source.source_name, "message": "Source added successfully"}


@app.post("/api/news-sources/{source_id}/toggle")
def toggle_news_source(source_id: int, db: Session = Depends(get_db)):
    """Enable/disable a news source."""
    source = db.query(NewsSource).filter_by(id=source_id).first()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    source.enabled = not source.enabled
    db.commit()
    return {"id": source.id, "enabled": source.enabled}


@app.delete("/api/news-sources/{source_id}")
def delete_news_source(source_id: int, db: Session = Depends(get_db)):
    """Remove a news source."""
    source = db.query(NewsSource).filter_by(id=source_id).first()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    db.delete(source)
    db.commit()
    return {"message": "Source deleted"}


# ============================================================================
# Admin / Maintenance
# ============================================================================

@app.post("/api/admin/cleanup")
def cleanup_database(days: int = 180, db: Session = Depends(get_db)):
    """
    Remove stale news items and old monitoring run history.

    News items with status Approved or Sent are kept regardless of age
    (they're curated/already used in a report); everything else older than
    `days` is removed. Old monitoring run log entries beyond the same
    window are removed too, since they're just diagnostic history.
    """
    cutoff = datetime.utcnow() - timedelta(days=days)

    deleted_news = (
        db.query(NewsItem)
        .filter(NewsItem.created_at < cutoff, NewsItem.status.notin_(["Approved", "Sent"]))
        .delete(synchronize_session=False)
    )
    deleted_runs = (
        db.query(MonitoringRun)
        .filter(MonitoringRun.started_at < cutoff)
        .delete(synchronize_session=False)
    )
    db.commit()

    return {
        "message": "Cleanup completed",
        "deleted_news_items": deleted_news,
        "deleted_monitoring_runs": deleted_runs,
        "cutoff_days": days,
    }


@app.get("/api/settings")
def get_settings(db: Session = Depends(get_db)):
    """Current settings (stored values override .env). Secrets are masked."""
    return settings_store.get_all(db)


@app.post("/api/settings")
def save_settings(payload: dict = Body(...), db: Session = Depends(get_db)):
    """Persist settings edited from the dashboard."""
    saved = settings_store.save_settings(db, payload)
    if not saved:
        raise HTTPException(status_code=400, detail="Nessuna impostazione valida da salvare")
    return {"saved": saved, "message": f"{len(saved)} impostazioni salvate"}


@app.post("/api/admin/fix-news-urls")
def fix_news_urls(db: Session = Depends(get_db)):
    """
    Repair Google News links already stored with the /rss/ path.

    Those open as raw RSS XML ("Questo feed non e' disponibile.") instead of
    redirecting to the article; new items are normalized on save, this fixes
    the ones saved before.
    """
    from app.providers.google_news_rss import GoogleNewsRSSProvider

    # Two independent repairs: a Google News link to decode, and/or a
    # summary still holding raw <description> markup. A row can need either,
    # so don't gate the summary fix behind the URL filter.
    affected = db.query(NewsItem).filter(
        NewsItem.url.like("%news.google.com%") | NewsItem.summary.like("%<%")
    ).all()

    fixed = 0
    cleaned = 0
    for item in affected:
        # Pass the title so undecodable (newer) ids can still fall back to a
        # search on the headline instead of staying on a dead feed link.
        new_url = GoogleNewsRSSProvider.normalize_article_url(item.url, item.title)
        if new_url and new_url != item.url:
            item.url = new_url
            fixed += 1
        # Older rows stored the raw <description> markup as the summary.
        clean = GoogleNewsRSSProvider.clean_summary(item.summary, item.title)
        if clean != item.summary:
            item.summary = clean
            cleaned += 1
    db.commit()

    return {
        "fixed": fixed,
        "cleaned_summaries": cleaned,
        "message": f"{fixed} link corretti, {cleaned} sommari ripuliti (su {len(affected)} notizie)",
    }


@app.post("/api/admin/reset")
def reset_system(confirm: str = "", db: Session = Depends(get_db)):
    """
    Wipe ALL data (companies, clusters, news, reports, sources, run history)
    while keeping the schema intact. Irreversible - requires confirm=RESET.
    """
    if confirm != "RESET":
        raise HTTPException(status_code=400, detail="Pass confirm=RESET to actually wipe all data")

    # Children before parents, to satisfy SQLite's foreign key constraints.
    for model in [NewsItem, CompanyCluster, ClusterRecipient, Report, MonitoringRun, NewsSource, Cluster, Company]:
        db.query(model).delete(synchronize_session=False)
    db.commit()

    return {"message": "All data has been reset"}


# ============================================================================
# Phase 3 - Email Sending
# ============================================================================

@app.post("/api/reports/{report_id}/send")
def send_report(
    report_id: int,
    db: Session = Depends(get_db)
):
    """Send report to recipients."""
    report = db.query(Report).filter_by(id=report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    # Get cluster recipients
    recipients = [r.email for r in report.cluster.recipients if r.email and r.active]
    if not recipients:
        cluster_name = report.cluster.cluster_name if report.cluster else "?"
        raise HTTPException(
            status_code=400,
            detail=(
                f"Nessun destinatario configurato per il cluster '{cluster_name}'. "
                f"Aggiungine uno dalla pagina Cluster > Dettagli."
            ),
        )

    # Send email
    sender = EmailSender(db)
    result = sender.send_report(
        to_emails=recipients,
        subject=report.subject,
        html_content=report.body_html or "<p>Report content</p>",
        text_content=report.body_text or "Report content"
    )

    if result['success']:
        report.status = 'Sent'
        report.sent_at = datetime.utcnow()
        db.commit()

        return {
            "status": "sent",
            "recipients": len(recipients),
            "message": f"Report sent to {len(recipients)} recipients"
        }
    else:
        raise HTTPException(status_code=400, detail=result['error'])


@app.post("/api/reports/send-due")
def send_due_reports_now(force: bool = False, db: Session = Depends(get_db)):
    """
    Generate and email reports for clusters that are due.

    Runs automatically once a day when the scheduler is on; this endpoint
    is the manual trigger. `force=true` sends regardless of the schedule.
    """
    from app.services.report_scheduler import send_due_reports
    return send_due_reports(db, force=force)


@app.post("/api/email/test-smtp")
def test_smtp_connection(db: Session = Depends(get_db)):
    """Test SMTP connection."""
    sender = EmailSender(db)
    result = sender.test_connection()

    return result


@app.post("/api/claude/test")
def test_claude_api():
    """Test the configured Claude API key with a minimal request."""
    if not (settings.CLAUDE_API_KEY or settings.ANTHROPIC_API_KEY):
        return {"success": False, "error": "Nessuna API key configurata (CLAUDE_API_KEY / ANTHROPIC_API_KEY)"}

    try:
        from anthropic import Anthropic
        client = Anthropic(api_key=settings.CLAUDE_API_KEY or settings.ANTHROPIC_API_KEY)
        client.messages.create(
            model="claude-sonnet-5",
            max_tokens=10,
            thinking={"type": "disabled"},
            messages=[{"role": "user", "content": "ping"}],
        )
        return {"success": True, "message": "Connessione a Claude riuscita"}
    except Exception as e:
        reason = NewsClassifier._fatal_reason(e)
        if reason:
            return {"success": False, "error": f"{reason} - vedi console.anthropic.com (Plans & Billing)"}
        return {"success": False, "error": str(e)}


@app.post("/api/email/send-alert")
def send_alert_email(
    news_id: int,
    recipient_email: str,
    db: Session = Depends(get_db)
):
    """Send urgent alert email for critical news."""
    news = db.query(NewsItem).filter_by(id=news_id).first()
    if not news:
        raise HTTPException(status_code=404, detail="News not found")

    sender = EmailSender(db)
    result = sender.send_alert(
        to_email=recipient_email,
        company_name=news.company.company_name,
        news_title=news.title,
        risk_score=news.risk_score
    )

    if result['success']:
        return {"status": "sent", "message": "Alert sent successfully"}
    else:
        raise HTTPException(status_code=400, detail=result['error'])


@app.post("/api/reports/generate")
def generate_report(
    cluster_id: int,
    days_back: int = 7,
    db: Session = Depends(get_db)
):
    """Generate report for cluster."""
    cluster = db.query(Cluster).filter_by(id=cluster_id).first()
    if not cluster:
        raise HTTPException(status_code=404, detail="Cluster not found")

    period_end = datetime.utcnow()
    period_start = period_end - timedelta(days=days_back)

    generator = ReportGenerator()
    report = generator.generate_cluster_report(db, cluster, period_start, period_end)

    return {
        "id": report.id,
        "cluster_name": cluster.cluster_name,
        "status": report.status,
        "message": "Report generated successfully"
    }


@app.get("/upload", response_class=HTMLResponse)
def upload_page(request: Request):
    """Upload page."""
    return render(request, "upload.html")


@app.get("/companies", response_class=HTMLResponse)
def companies_page(request: Request):
    """Companies management page."""
    return render(request, "companies.html")


@app.get("/coverage", response_class=HTMLResponse)
def coverage_page(request: Request):
    """Search coverage page - per-company search history/visibility."""
    return render(request, "coverage.html")


@app.get("/clusters", response_class=HTMLResponse)
def clusters_page(request: Request):
    """Clusters configuration page."""
    return render(request, "clusters.html")


@app.get("/news", response_class=HTMLResponse)
def news_page(request: Request):
    """News management page."""
    return render(request, "news.html")


@app.get("/reports", response_class=HTMLResponse)
def reports_page(request: Request):
    """Reports management page."""
    return render(request, "reports.html")


@app.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request):
    """Settings page."""
    return render(request, "settings.html")


# /monitoring stays disabled: not a bug (the "unhashable dict" issue that
# originally broke it was a starlette API mismatch in render(), now fixed
# above for every page) - its controls were simply moved into Impostazioni
# (/settings) to avoid a duplicate UI. app/templates/monitoring.html is
# unused but left in place in case it's wanted back as a dedicated page.
# @app.get("/monitoring", response_class=HTMLResponse)
# def monitoring_page(request: Request):
#     """Monitoring page."""
#     return render(request, "monitoring.html")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=settings.HOST, port=settings.PORT)
