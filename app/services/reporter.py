"""Report generation service."""

from datetime import datetime
from html import escape
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
        from app.services.branding import get_branding
        brand = get_branding(db)

        body_html = self._generate_html_report(cluster, news_items, period_start, period_end, brand)
        body_text = self._generate_text_report(cluster, news_items, period_start, period_end, brand)

        subject = f"{brand['name']} - {cluster.cluster_name} - {period_end.strftime('%Y-%m-%d')}"

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
        brand: dict = None,
    ) -> str:
        """Generate HTML report content."""
        from app.services.branding import default_branding

        brand = brand or default_branding()
        period_str = f"{period_start.strftime('%d/%m/%Y')} - {period_end.strftime('%d/%m/%Y')}"

        # Referenced by Content-ID, not embedded: Gmail and Outlook drop
        # data: images, and a link to the local server is unreachable for
        # whoever receives the email. email_sender attaches the file.
        logo_html = (
            f'<img class="brand-logo" src="cid:{brand["logo_cid"]}" alt="{escape(brand["name"], quote=True)}">'
            if brand.get("logo_path") else ""
        )

        intro = brand.get("intro") or "Buongiorno,\ndi seguito il riepilogo delle notizie piu' rilevanti."
        intro_html = "".join(
            f"<p>{escape(line, quote=False)}</p>"
            for line in intro.splitlines() if line.strip()
        )

        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .header {{ background-color: {brand['color']}; color: white; padding: 20px; margin-bottom: 20px; }}
                .header h1 {{ margin: 0 0 10px 0; }}
                .brand-logo {{ max-height: 52px; max-width: 240px; margin-bottom: 12px; }}
                .section {{ margin-bottom: 30px; }}
                .news-item {{ border-left: 4px solid #3498db; padding-left: 15px; margin-bottom: 26px; }}
                .news-item h3 {{ margin: 0 0 6px 0; line-height: 1.35; }}
                .news-item h3 a {{ color: #2c3e50; }}
                .meta {{ margin: 0 0 10px 0; color: #7f8c8d; font-size: 13px; }}
                .summary {{ margin: 0 0 12px 0; color: #444; line-height: 1.55; }}
                .read-more {{
                    display: inline-block; margin-bottom: 12px; padding: 8px 14px;
                    background-color: #3498db; color: #ffffff !important;
                    border-radius: 4px; font-size: 14px; font-weight: bold;
                    text-decoration: none;
                }}
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
                {logo_html}
                <h1>{escape(brand['name'], quote=False)}</h1>
                <p><strong>Cluster:</strong> {escape(cluster.cluster_name, quote=False)}</p>
                <p><strong>Periodo:</strong> {period_str}</p>
            </div>

            <div class="section">
                <h2>Riepilogo</h2>
                {intro_html}
                <p>Nel periodo considerato sono state trovate <strong>{len(news_items)} notizie</strong> che superano il punteggio minimo di rilevanza ({cluster.min_relevance_score}/10).</p>
            </div>
        """

        if news_items:
            html += '<div class="section"><h2>Notizie Principali</h2>'

            for idx, news in enumerate(news_items, 1):
                impact_class = "high" if news.relevance_score >= 8 else "medium" if news.relevance_score >= 6 else "low"
                link = self.article_link(news)
                published = news.published_date.strftime('%d/%m/%Y') if news.published_date else 'N/A'

                # Everything below comes from third-party feeds and from the
                # model: escape it, or a stray "<" in a headline breaks the
                # email body (or worse, injects markup into it).
                # quote=False for text nodes: only <, > and & need escaping
                # there, and escaping apostrophes would litter Italian prose
                # with &#x27;. Attribute values below use the full escape.
                title = escape(news.title or "", quote=False)
                company = escape(news.company.company_name if news.company else "-", quote=False)
                category = escape(news.category or "-", quote=False)
                source = escape(news.source_name or "-", quote=False)

                body = self.article_text(news)
                body_html = f'<p class="summary">{escape(body, quote=False)}</p>' if body else ""

                scores_html = "" if not brand.get("show_scores") else f"""
                    <div>
                        <span class="score">Rilevanza: <strong class="{impact_class}">{news.relevance_score:.1f}/10</strong></span>
                        <span class="score">Urgenza: <strong>{news.urgency_score:.1f}/10</strong></span>
                        <span class="score">Opportunità: <strong>{news.commercial_score:.1f}/10</strong></span>
                        <span class="score">Rischio: <strong>{news.risk_score:.1f}/10</strong></span>
                    </div>"""

                html += f"""
                <div class="news-item">
                    <h3>{idx}. <a href="{escape(link, quote=True)}">{title}</a></h3>
                    <p class="meta">
                        <strong>{company}</strong> &middot; {source} &middot; {published} &middot; {category}
                    </p>

                    {body_html}

                    <p><a class="read-more" href="{escape(link, quote=True)}">Leggi l'articolo &rarr;</a></p>

                    {scores_html}
                </div>
                """

            html += '</div>'
        else:
            html += '<div class="section"><p>Nessuna notizia rilevante nel periodo considerato.</p></div>'

        html += f"""
            <div class="section">
                <p style="color: #999; font-size: 12px;">
                    {escape(brand['footer'] or '', quote=False)}
                </p>
            </div>
        </body>
        </html>
        """

        return html

    @staticmethod
    def article_link(news: NewsItem) -> str:
        """
        A link the reader can actually open.

        Google News article ids are increasingly opaque blobs that hold no
        publisher URL, and the /rss/ path they sit on serves raw XML
        ("Questo feed non e' disponibile") rather than redirecting. Rows
        saved before this was handled still carry those links, so resolve
        them here too instead of trusting what's stored.
        """
        from app.providers.google_news_rss import GoogleNewsRSSProvider

        return GoogleNewsRSSProvider.normalize_article_url(news.url, news.title)

    @staticmethod
    def article_text(news: NewsItem, max_chars: int = 320) -> str:
        """
        The two or three lines that go under the headline.

        Prefers the article's own summary and adds the classifier's reading
        of why it matters - which is the sentence that makes a report worth
        opening. Falls back gracefully: many Google News entries carry no
        usable description at all.
        """
        parts = []
        for value in (news.summary, news.why_it_matters):
            text = " ".join((value or "").split())
            # Skip the placeholder the fallback classification writes in.
            if not text or text.lower().startswith("classificazione ai"):
                continue
            if text not in parts:
                parts.append(text)

        body = " ".join(parts)
        if len(body) > max_chars:
            body = body[:max_chars].rsplit(" ", 1)[0] + "..."
        return body

    def _generate_text_report(
        self,
        cluster: Cluster,
        news_items: List[NewsItem],
        period_start: datetime,
        period_end: datetime,
        brand: dict = None,
    ) -> str:
        """Generate plain text report content."""
        from app.services.branding import default_branding

        brand = brand or default_branding()
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
                body = self.article_text(news)
                published = news.published_date.strftime('%d/%m/%Y') if news.published_date else 'N/A'
                company = news.company.company_name if news.company else '-'

                text += f"""{idx}. {news.title}

{company} · {news.source_name} · {published} · {news.category}
"""
                if body:
                    text += f"\n{body}\n"

                # Resolved the same way as the HTML version: the stored URL
                # may still be a Google News /rss/ link that serves XML.
                text += f"""
Leggi l'articolo: {self.article_link(news)}

Punteggi: rilevanza {news.relevance_score:.1f}/10 · urgenza {news.urgency_score:.1f}/10 · opportunità {news.commercial_score:.1f}/10 · rischio {news.risk_score:.1f}/10

"""

        else:
            text += "Nessuna notizia rilevante nel periodo considerato.\n\n"

        text += """
---
Report generato automaticamente da Customer Intelligence Monitor.
Per modifiche alla configurazione dei cluster, contattare l'amministratore.
"""

        return text
