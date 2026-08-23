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
        # Anthropic() with no args only auto-reads the SDK's native
        # ANTHROPIC_API_KEY env var - our own setup docs tell users to set
        # CLAUDE_API_KEY, which the bare constructor never sees. Pass it
        # explicitly so a CLAUDE_API_KEY-only .env actually authenticates.
        api_key = settings.CLAUDE_API_KEY or settings.ANTHROPIC_API_KEY
        self.client = Anthropic(api_key=api_key) if api_key else None
        # Set once an account-level failure (no credit, invalid key, no
        # permission) is seen: those never recover mid-run, so retrying for
        # every remaining article just burns minutes and floods the log.
        self.disabled_reason: str = None

    # Account-level failures: retrying within the same run is pointless.
    _FATAL_ERROR_MARKERS = (
        "credit balance is too low",
        "authentication_error",
        "permission_error",
        "invalid x-api-key",
    )

    @classmethod
    def _fatal_reason(cls, error: Exception) -> str:
        """Return a short human reason if this error is account-level."""
        text = str(error).lower()
        if "credit balance is too low" in text:
            return "credito Anthropic esaurito"
        if "authentication_error" in text or "invalid x-api-key" in text:
            return "API key non valida"
        if "permission_error" in text:
            return "API key senza permessi"
        return None

    # Models that accept an explicit thinking config. Older models (e.g.
    # claude-haiku-4-5) don't take `thinking: disabled` and would 400 on it,
    # and they don't think by default anyway - so we just omit the param.
    _THINKING_CAPABLE_PREFIXES = (
        "claude-opus-5", "claude-opus-4-8", "claude-opus-4-7", "claude-opus-4-6",
        "claude-sonnet-5", "claude-sonnet-4-6", "claude-fable-5",
    )

    @classmethod
    def _thinking_kwargs(cls) -> Dict[str, Any]:
        """Turn thinking off where supported: classification is a short,
        structured task that gains nothing from it and only costs more."""
        model = settings.CLAUDE_MODEL
        if any(model.startswith(p) for p in cls._THINKING_CAPABLE_PREFIXES):
            return {"thinking": {"type": "disabled"}}
        return {}

    @staticmethod
    def sdk_supports_messages() -> bool:
        """True if the installed anthropic SDK has the Messages API."""
        return hasattr(Anthropic, "messages")

    @staticmethod
    def fallback_result(title: str, why: str, action: str) -> Dict[str, Any]:
        """
        Neutral classification used when Claude can't be reached.

        A news item must never be lost just because the AI step failed -
        the article itself is still real and useful. Scores are set to a
        neutral 5 (and confidence to 1) so the item is visible but clearly
        marked as not-yet-AI-reviewed.
        """
        return {
            "summary": title[:200],
            "category": "Da classificare",
            "relevance_score": 5,
            "urgency_score": 5,
            "commercial_score": 5,
            "risk_score": 5,
            "confidence_score": 1,
            "why_it_matters": why,
            "suggested_action": action,
            "email_ready_summary": title[:150],
        }

    def classify_news(
        self,
        company_name: str,
        title: str,
        url: str,
        source_name: str,
        article_text: str = None,
        ateco_description: str = None,
        account_owner: str = None,
        website: str = None,
        tax_code: str = None,
    ) -> Dict[str, Any]:
        """
        Classify news article using Claude.

        Only structured metadata is sent (title, source, url, snippet) -
        never full page content. website/tax_code are passed purely as
        disambiguation hints so Claude can judge whether the article
        genuinely refers to this specific company and not a homonym.

        Returns:
            Dict with category, scores, summary, etc.
        """
        if not article_text:
            article_text = "(Snippet non disponibile)"

        if not self.client:
            return self.fallback_result(
                title,
                "Classificazione AI non disponibile (nessuna API key configurata)",
                "Configura la API key Claude in .env per la classificazione AI",
            )

        if self.disabled_reason:
            # Already established this run that the account can't serve
            # requests - skip the doomed call instead of repeating it once
            # per article.
            return self.fallback_result(
                title,
                f"Classificazione AI sospesa: {self.disabled_reason}",
                "Risolvi il problema sull'account Anthropic, poi usa Riclassifica",
            )

        prompt = f"""Sei un analista di customer intelligence per una società di consulenza IT.

Analizza la seguente notizia relativa al cliente indicato.

Cliente: {company_name}

Sito web cliente: {website or 'N/A'}

P.IVA/Codice fiscale cliente: {tax_code or 'N/A'}

Settore: {ateco_description or 'N/A'}

Referente commerciale: {account_owner or 'N/A'}

Titolo notizia: {title}

Fonte: {source_name}

URL: {url}

Snippet/estratto disponibile (non l'articolo completo):
{article_text}

Prima di tutto valuta se la notizia riguarda davvero QUESTO cliente specifico
(usa nome, sito web, settore come riferimento) e non un'altra azienda con
nome simile o omonimo: se ci sono dubbi, abbassa fortemente confidence_score.

Restituisci un JSON con:
- summary (breve sintesi della notizia, max 200 caratteri)
- category (una tra: {', '.join(self.CATEGORIES)})
- relevance_score (1-10: quanto è rilevante per il cliente)
- urgency_score (1-10: quanto richiede attenzione immediata)
- commercial_score (1-10: opportunità commerciale potenziale)
- risk_score (1-10: criticità o rischio da attenzionare)
- confidence_score (1-10: affidabilità dell'associazione notizia-cliente, basso se potrebbe essere un omonimo)
- why_it_matters (una frase su perché è importante)
- suggested_action (azione consigliata per il team)
- email_ready_summary (sintesi pronta per email, max 150 caratteri)

Regole:
- Non inventare informazioni oltre a quanto fornito nello snippet
- Se la notizia è poco pertinente, assegna relevance_score basso (1-3)
- Se il cliente non è citato chiaramente o potrebbe essere un omonimo, abbassa confidence_score (1-3)
- Se il contenuto completo non è disponibile, non inventare la sintesi
- Mantieni tono professionale, sintetico e operativo
- Restituisci SOLO il JSON, niente altro"""

        try:
            message = self.client.messages.create(
                model=settings.CLAUDE_MODEL,
                max_tokens=1024,
                **self._thinking_kwargs(),
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
        except Exception as e:
            reason = self._fatal_reason(e)
            if reason:
                self.disabled_reason = reason
                print(f"[Classifier] {reason}: classificazione AI sospesa per il resto del run")
            raise

        response_text = next((b.text for b in message.content if b.type == "text"), "").strip()

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
            model=settings.CLAUDE_MODEL,
            max_tokens=2048,
            **self._thinking_kwargs(),
            messages=[
                {"role": "user", "content": prompt}
            ]
        )

        return next((b.text for b in message.content if b.type == "text"), "")
