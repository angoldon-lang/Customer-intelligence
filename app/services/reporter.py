"""Report generation service."""

from datetime import datetime
from typing import List, Dict, Any
from sqlalchemy.orm import Session
from app.models import NewsItem, Report, Cluster


class ReportGenerator:
    """Generate email reports for clusters."""

    def generate_cluster_report(
        self,
        db: Session,
        cluster: Cluster,
        period_start: datetime,
        period_end: datetime,
    ) -> Report:
        """
        Generate report for cluster with news from period.

        Returns:
            Report object (not yet sent)
        """
        # Get news items for cluster companies from period
        from sqlalchemy import and_, func
        from app.models import CompanyCluster

        company_ids = [cc.company_id for cc in cluster.companies]
        if not company_ids:
            news_items = []
        else:
            # Not every provider supplies a publication date. Fall back to
            # created_at for those, otherwise a NULL published_date makes the
            # comparison NULL and the item silently drops out of every report.
            effective_date = func.coalesce(NewsItem.published_date, NewsItem.created_at)
            news_items = db.query(NewsItem).filter(
                and_(
                    NewsItem.company_id.in_(company_ids),
                    effective_date >= period_start,
                    effective_date <= period_end,
                    NewsItem.status.in_(["Approved", "New"]),
                    NewsItem.relevance_score >= cluster.min_relevance_score,
                )
            ).order_by(NewsItem.relevance_score.desc()).all()

        # Generate report content
        body_html = self._generate_html_report(cluster, news_items, period_start, period_end)
        body_text = self._generate_text_report(cluster, news_items, period_start, period_end)

        # Create subject
        subject = f"Customer Intelligence Report - {cluster.cluster_name} - {period_end.strftime('%Y-%m-%d')}"

        # Create report object
        report = Report(
            cluster_id=cluster.id,
            period_start=period_start,
            period_end=period_end,
            subject=subject,
            body_html=body_html,
            body_text=body_text,
            status="Draft",
        )

        db.add(report)
        db.commit()
        db.refresh(report)

        return report

    def _generate_html_report(
        self,
        cluster: Cluster,
        news_items: List[NewsItem],
        period_start: datetime,
        period_end: datetime,
    ) -> str:
        """Generate HTML report content."""
        period_str = f"{period_start.strftime('%d/%m/%Y')} - {period_end.strftime('%d/%m/%Y')}"

        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .header {{ background-color: #2c3e50; color: white; padding: 20px; margin-bottom: 20px; }}
                .section {{ margin-bottom: 30px; }}
                .news-item {{ border-left: 4px solid #3498db; padding-left: 15px; margin-bottom: 15px; }}
                .score {{ display: inline-block; background-color: #ecf0f1; padding: 5px 10px; margin-right: 10px; border-radius: 3px; }}
                .high {{ color: #e74c3c; }}
                .medium {{ color: #f39c12; }}
                .low {{ color: #27ae60; }}
                a {{ color: #3498db; text-decoration: none; }}
                a:hover {{ text-decoration: underline; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>Customer Intelligence Report</h1>
                <p><strong>Cluster:</strong> {cluster.cluster_name}</p>
                <p><strong>Periodo:</strong> {period_str}</p>
            </div>

            <div class="section">
                <h2>Riepilogo</h2>
                <p>Buongiorno,</p>
                <p>di seguito il riepilogo delle notizie più rilevanti relative al cluster <strong>{cluster.cluster_name}</strong>.</p>
                <p>Nel periodo considerato sono state trovate <strong>{len(news_items)} notizie</strong> che superano il punteggio minimo di rilevanza ({cluster.min_relevance_score}/10).</p>
            </div>
        """

        if news_items:
            html += '<div class="section"><h2>Notizie Principali</h2>'

            for idx, news in enumerate(news_items, 1):
                impact_class = "high" if news.relevance_score >= 8 else "medium" if news.relevance_score >= 6 else "low"
                html += f"""
                <div class="news-item">
                    <h3>{idx}. {news.title}</h3>
                    <p><strong>Azienda:</strong> {news.company.company_name}</p>
                    <p><strong>Categoria:</strong> {news.category}</p>
                    <p><strong>Data:</strong> {news.published_date.strftime('%d/%m/%Y') if news.published_date else 'N/A'}</p>
                    <p><strong>Fonte:</strong> <a href="{news.url}">{news.source_name}</a></p>

                    <div>
                        <span class="score">Rilevanza: <strong class="{impact_class}">{news.relevance_score:.1f}/10</strong></span>
                        <span class="score">Urgenza: <strong>{news.urgency_score:.1f}/10</strong></span>
                        <span class="score">Opportunità: <strong>{news.commercial_score:.1f}/10</strong></span>
                        <span class="score">Rischio: <strong>{news.risk_score:.1f}/10</strong></span>
                    </div>

                    <p><em>{news.summary}</em></p>
                </div>
                """

            html += '</div>'
        else:
            html += '<div class="section"><p>Nessuna notizia rilevante nel periodo considerato.</p></div>'

        html += """
            <div class="section">
                <p style="color: #999; font-size: 12px;">
                    Report generato automaticamente da Customer Intelligence Monitor.
                    Per modifiche alla configurazione dei cluster, contattare l'amministratore.
                </p>
            </div>
        </body>
        </html>
        """

        return html

    def _generate_text_report(
        self,
        cluster: Cluster,
        news_items: List[NewsItem],
        period_start: datetime,
        period_end: datetime,
    ) -> str:
        """Generate plain text report content."""
        period_str = f"{period_start.strftime('%d/%m/%Y')} - {period_end.strftime('%d/%m/%Y')}"

        text = f"""CUSTOMER INTELLIGENCE REPORT
================================

Cluster: {cluster.cluster_name}
Periodo: {period_str}

Buongiorno,

di seguito il riepilogo delle notizie più rilevanti relative al cluster {cluster.cluster_name}.

Nel periodo considerato sono state trovate {len(news_items)} notizie che superano il punteggio minimo di rilevanza ({cluster.min_relevance_score}/10).

"""

        if news_items:
            text += "NOTIZIE PRINCIPALI\n" + "=" * 50 + "\n\n"

            for idx, news in enumerate(news_items, 1):
                text += f"""{idx}. {news.title}

Azienda: {news.company.company_name}
Categoria: {news.category}
Data: {news.published_date.strftime('%d/%m/%Y') if news.published_date else 'N/A'}
Fonte: {news.source_name}
Link: {news.url}

Punteggi:
- Rilevanza: {news.relevance_score:.1f}/10
- Urgenza: {news.urgency_score:.1f}/10
- Opportunità: {news.commercial_score:.1f}/10
- Rischio: {news.risk_score:.1f}/10

Sintesi: {news.summary}

"""

        else:
            text += "Nessuna notizia rilevante nel periodo considerato.\n\n"

        text += """
---
Report generato automaticamente da Customer Intelligence Monitor.
Per modifiche alla configurazione dei cluster, contattare l'amministratore.
"""

        return text
