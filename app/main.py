"""FastAPI application entry point."""

from fastapi import FastAPI, UploadFile, File, Depends, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
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

# Mount static files if they exist
if os.path.exists("app/static"):
    app.mount("/static", StaticFiles(directory="app/static"), name="static")


# ============================================================================
# API Endpoints
# ============================================================================

@app.get("/", response_class=HTMLResponse)
def read_root():
    """Root endpoint - dashboard."""
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Customer Intelligence Monitor</title>
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body { font-family: Arial, sans-serif; background: #f5f5f5; }
            .header { background: #2c3e50; color: white; padding: 30px; text-align: center; }
            .header h1 { margin-bottom: 10px; }
            .container { max-width: 1200px; margin: 0 auto; padding: 20px; }
            .menu { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin-bottom: 30px; }
            .card { background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); text-align: center; }
            .card h2 { margin-bottom: 10px; color: #2c3e50; }
            .card p { color: #666; margin-bottom: 15px; }
            .btn { display: inline-block; padding: 10px 20px; background: #3498db; color: white; text-decoration: none; border-radius: 4px; border: none; cursor: pointer; }
            .btn:hover { background: #2980b9; }
            .status { margin-top: 30px; background: white; padding: 20px; border-radius: 8px; }
            .status h2 { color: #2c3e50; margin-bottom: 15px; }
            .status-item { padding: 10px; border-bottom: 1px solid #eee; }
            .status-item:last-child { border-bottom: none; }
        </style>
    </head>
    <body>
        <div class="header">
            <h1>Customer Intelligence Monitor</h1>
            <p>Monitora notizie e informazioni su clienti, fornitori e aziende</p>
        </div>

        <div class="container">
            <div class="menu">
                <div class="card">
                    <h2>📁 Importa Dati</h2>
                    <p>Carica file Excel o CSV con anagrafica aziendali</p>
                    <a href="/upload" class="btn">Accedi</a>
                </div>

                <div class="card">
                    <h2>🏢 Aziende</h2>
                    <p>Gestisci aziende da monitorare</p>
                    <a href="/companies" class="btn">Gestisci</a>
                </div>

                <div class="card">
                    <h2>📊 Cluster</h2>
                    <p>Configura cluster e destinatari report</p>
                    <a href="/clusters" class="btn">Configura</a>
                </div>

                <div class="card">
                    <h2>📰 Notizie</h2>
                    <p>Visualizza e approva notizie trovate</p>
                    <a href="/news" class="btn">Visualizza</a>
                </div>

                <div class="card">
                    <h2>📧 Report</h2>
                    <p>Genera e gestisci report email</p>
                    <a href="/reports" class="btn">Gestisci</a>
                </div>

                <div class="card">
                    <h2>⚙️ Impostazioni</h2>
                    <p>Configurazione generale sistema</p>
                    <a href="/settings" class="btn">Configura</a>
                </div>
            </div>

            <div class="status">
                <h2>Stato Sistema</h2>
                <div class="status-item">
                    <strong>Database:</strong> <span id="db-status">Verificando...</span>
                </div>
                <div class="status-item">
                    <strong>API Claude:</strong> <span id="api-status">Verificando...</span>
                </div>
                <div class="status-item">
                    <strong>Provider Notizie:</strong> <span id="provider-status">Mock (MVP)</span>
                </div>
            </div>
        </div>

        <script>
            fetch('/api/health')
                .then(r => r.json())
                .then(d => {
                    document.getElementById('db-status').textContent = d.database ? '✓ OK' : '✗ Errore';
                    document.getElementById('api-status').textContent = d.api ? '✓ OK' : '⚠️ Non configurata';
                });
        </script>
    </body>
    </html>
    """


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
        for company_data in result["companies"]:
            # Check if already exists
            existing = db.query(Company).filter_by(company_name=company_data["company_name"]).first()
            if not existing:
                company = Company(**company_data)
                db.add(company)
                added_count += 1

        db.commit()

        result["added_to_database"] = added_count
        return result

    except Exception as e:
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


# Placeholder endpoints for dashboard pages
@app.get("/upload", response_class=HTMLResponse)
def upload_page():
    return "<h1>Upload Page (To be implemented)</h1>"


@app.get("/companies", response_class=HTMLResponse)
def companies_page():
    return "<h1>Companies Management (To be implemented)</h1>"


@app.get("/clusters", response_class=HTMLResponse)
def clusters_page():
    return "<h1>Clusters Configuration (To be implemented)</h1>"


@app.get("/news", response_class=HTMLResponse)
def news_page():
    return "<h1>News Management (To be implemented)</h1>"


@app.get("/reports", response_class=HTMLResponse)
def reports_page():
    return "<h1>Reports Management (To be implemented)</h1>"


@app.get("/settings", response_class=HTMLResponse)
def settings_page():
    return "<h1>Settings (To be implemented)</h1>"


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=settings.HOST, port=settings.PORT)
