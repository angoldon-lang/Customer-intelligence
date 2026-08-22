"""FastAPI application entry point."""

from fastapi import FastAPI, UploadFile, File, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from datetime import datetime, timedelta
import os

from app.config import settings
from app.database import init_db, get_db
from app.models import Company, Cluster, NewsItem, Report, MonitoringRun
from app.services import DataImporter, DataNormalizer, ClusterManager
from app.services.classifier import NewsClassifier
from app.services.reporter import ReportGenerator
from app.providers import MockNewsProvider

# Initialize database tables
init_db()

app = FastAPI(
    title="Customer Intelligence Monitor",
    description="Monitor news and intelligence about companies",
    version="0.1.0",
)

# Setup templates
templates = Jinja2Templates(directory="app/templates")

# Mount static files if they exist
if os.path.exists("app/static"):
    app.mount("/static", StaticFiles(directory="app/static"), name="static")


# ============================================================================
# Page Routes - HTML Templates
# ============================================================================

@app.get("/", response_class=HTMLResponse)
def read_root(request: Request):
    """Root endpoint - dashboard."""
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/api/health")
def health_check(db: Session = Depends(get_db)):
    """Health check endpoint."""
    return {
        "status": "ok",
        "database": True,
        "api": bool(settings.CLAUDE_API_KEY),
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
    limit: int = 50,
    db: Session = Depends(get_db)
):
    """List news items with optional filters."""
    query = db.query(NewsItem)

    if status:
        query = query.filter_by(status=status)
    if category:
        query = query.filter_by(category=category)

    news = query.order_by(NewsItem.created_at.desc()).limit(limit).all()

    return {
        "total": len(news),
        "news": [
            {
                "id": n.id,
                "title": n.title,
                "company_name": n.company.company_name,
                "category": n.category,
                "relevance_score": n.relevance_score,
                "status": n.status,
                "source_name": n.source_name,
            }
            for n in news
        ]
    }


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
                "cluster_name": r.cluster.cluster_name,
                "period_start": r.period_start.isoformat(),
                "period_end": r.period_end.isoformat(),
                "status": r.status,
                "subject": r.subject,
            }
            for r in reports
        ]
    }


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
    return templates.TemplateResponse("upload.html", {"request": request})


@app.get("/companies", response_class=HTMLResponse)
def companies_page(request: Request):
    """Companies management page."""
    return templates.TemplateResponse("companies.html", {"request": request})


@app.get("/clusters", response_class=HTMLResponse)
def clusters_page(request: Request):
    """Clusters configuration page."""
    return templates.TemplateResponse("clusters.html", {"request": request})


@app.get("/news", response_class=HTMLResponse)
def news_page(request: Request):
    """News management page."""
    return templates.TemplateResponse("news.html", {"request": request})


@app.get("/reports", response_class=HTMLResponse)
def reports_page(request: Request):
    """Reports management page."""
    return templates.TemplateResponse("reports.html", {"request": request})


@app.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request):
    """Settings page."""
    return templates.TemplateResponse("settings.html", {"request": request})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=settings.HOST, port=settings.PORT)
