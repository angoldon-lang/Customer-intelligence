"""AI-based news classification service."""

import json
from typing import Dict, Any
from anthropic import Anthropic
from app.config import settings


class NewsClassifier:
    """Classify news articles using Claude AI."""

    CATEGORIES = [
        "Investment",
        "M&A",
        "Financial",
        "Management",
        "Cybersecurity",
        "Operations",
        "Compliance",
        "IT/Digital",
        "Tender",
        "Partnership",
        "Commercial Signal",
        "Risk Signal",
    ]

    def __init__(self):
        self.client = Anthropic() if settings.CLAUDE_API_KEY else None

    def classify_news(
        self,
        company_name: str,
        title: str,
        url: str,
        source_name: str,
        article_text: str = None,
        ateco_description: str = None,
        account_owner: str = None,
    ) -> Dict[str, Any]:
        """
        Classify news article using Claude.

        Returns:
            Dict with category, scores, summary, etc.
        """
        if not article_text:
            article_text = "(Content not available)"

        if not self.client:
            # No API key configured: return a neutral default classification
            return {
                "summary": title[:200],
                "category": "Commercial Signal",
                "relevance_score": 5,
                "urgency_score": 5,
                "commercial_score": 5,
                "risk_score": 5,
                "confidence_score": 3,
                "why_it_matters": "AI classification not available (no API key configured)",
                "suggested_action": "Configure Claude API key for AI-based classification",
                "email_ready_summary": title[:150],
            }

        prompt = f"""Sei un analista di customer intelligence per una società di consulenza IT.

Analizza la seguente notizia relativa al cliente indicato.

Cliente: {company_name}

Settore: {ateco_description or 'N/A'}

Referente commerciale: {account_owner or 'N/A'}

Titolo notizia: {title}

Fonte: {source_name}

URL: {url}

Testo o contenuto disponibile:
{article_text}

Restituisci un JSON con:
- summary (breve sintesi della notizia, max 200 caratteri)
- category (una tra: {', '.join(self.CATEGORIES)})
- relevance_score (1-10: quanto è rilevante per il cliente)
- urgency_score (1-10: quanto richiede attenzione immediata)
- commercial_score (1-10: opportunità commerciale potenziale)
- risk_score (1-10: criticità o rischio da attenzionare)
- confidence_score (1-10: affidabilità dell'associazione notizia-cliente)
- why_it_matters (una frase su perché è importante)
- suggested_action (azione consigliata per il team)
- email_ready_summary (sintesi pronta per email, max 150 caratteri)

Regole:
- Non inventare informazioni
- Se la notizia è poco pertinente, assegna relevance_score basso (1-3)
- Se il cliente non è citato chiaramente, abbassa confidence_score
- Se il contenuto completo non è disponibile, non inventare la sintesi
- Mantieni tono professionale, sintetico e operativo
- Restituisci SOLO il JSON, niente altro"""

        message = self.client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=1024,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )

        response_text = message.content[0].text.strip()

        # Parse JSON response
        try:
            # Try to extract JSON from response
            json_start = response_text.find("{")
            json_end = response_text.rfind("}") + 1
            if json_start >= 0 and json_end > json_start:
                json_str = response_text[json_start:json_end]
                result = json.loads(json_str)
            else:
                result = json.loads(response_text)
        except json.JSONDecodeError:
            # Fallback response if JSON parsing fails
            result = {
                "summary": "Unable to parse classification",
                "category": "Commercial Signal",
                "relevance_score": 5,
                "urgency_score": 5,
                "commercial_score": 5,
                "risk_score": 5,
                "confidence_score": 3,
                "why_it_matters": "Classification error",
                "suggested_action": "Manual review required",
                "email_ready_summary": "See full article",
            }

        # Ensure all required fields exist
        for field in [
            "summary", "category", "relevance_score", "urgency_score",
            "commercial_score", "risk_score", "confidence_score",
            "why_it_matters", "suggested_action", "email_ready_summary"
        ]:
            if field not in result:
                result[field] = None

        return result

    def generate_report_summary(
        self,
        cluster_name: str,
        period: str,
        classified_news: list,
    ) -> str:
        """
        Generate email report summary using Claude.

        Args:
            cluster_name: Name of the cluster
            period: Time period (e.g., "July 2024")
            classified_news: List of classified news items

        Returns:
            HTML formatted report
        """
        news_summary = "\n".join([
            f"- {news['company_name']}: {news['title']} (Rilevanza: {news['relevance_score']}/10)"
            for news in classified_news[:5]  # Top 5 news
        ])

        prompt = f"""Genera un report email sintetico e professionale per il cluster indicato.

Cluster: {cluster_name}

Periodo: {period}

Notizie classificate:
{news_summary}

La mail deve contenere:
- introduzione breve
- elenco clienti con notizie rilevanti
- alert critici
- opportunità commerciali
- azioni consigliate
- link alle fonti

Tono: professionale, chiaro, operativo, non troppo lungo.

Regole:
- Non inventare informazioni
- Non riportare articoli integrali
- Cita sempre le fonti
- Separa fatti da interpretazioni commerciali

Restituisci il corpo della email in HTML."""

        message = self.client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=2048,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )

        return message.content[0].text
