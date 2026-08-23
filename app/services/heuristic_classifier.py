"""Keyword-based news classifier - no API calls, no cost.

A pragmatic alternative to AI classification when you don't want to spend
API credits. It won't judge nuance the way Claude does, but it reliably
does the two things that matter most in practice: put a news item in a
category, and push obvious noise (sport, cronaca, gossip) to a low
relevance score so it stays out of reports.
"""

import re
from typing import Dict, Any, List

# category -> keywords that signal it. Order matters: first match wins.
CATEGORY_KEYWORDS: List[tuple] = [
    ("M&A", ["acquisizione", "acquisisce", "fusione", "merger", "opa ", "cede il",
             "cessione", "rileva il", "joint venture"]),
    ("Investment", ["investimento", "investe", "finanziamento", "round", "aumento di capitale",
                    "fondi pnrr", "stanziat", "milioni di euro per"]),
    ("Financial", ["bilancio", "utile", "fatturato", "ricavi", "semestre", "trimestre",
                   "risultati economic", "perdita", "ebitda", "debito"]),
    ("Cybersecurity", ["cyber", "attacco informatico", "ransomware", "data breach",
                       "violazione dati", "hacker", "phishing"]),
    ("IT/Digital", ["digitale", "digitalizzazione", "software", "cloud", "intelligenza artificiale",
                    "piattaforma", "sistema informativo", "app ", "tecnolog"]),
    ("Tender", ["gara", "appalto", "bando", "aggiudicat", "affidamento", "concorso"]),
    ("Management", ["nomina", "nominato", "nominata", "direttore", "amministratore delegato",
                    "presidente", "ceo", "dimission", "si insedia", "guida"]),
    ("Compliance", ["sanzione", "multa", "ispezione", "normativa", "authority", "garante",
                    "indagine", "procura", "sentenza", "ricorso"]),
    ("Partnership", ["partnership", "accordo con", "collaborazione", "protocollo d'intesa",
                     "intesa con", "alleanza"]),
    ("Operations", ["assunzioni", "assume", "nuova sede", "apertura", "inaugurat",
                    "ampliament", "stabilimento", "riorganizzazione", "sciopero"]),
    ("Risk Signal", ["crisi", "licenziamenti", "cassa integrazione", "fallimento",
                     "concordato", "chiusura", "esuberi"]),
]

# Topics that are almost never commercially relevant for B2B intelligence.
NOISE_KEYWORDS = [
    "calcio", "calciatore", "serie a", "partita", "allenatore", "gol", "campionato",
    "concerto", "festival", "mostra", "spettacolo", "film",
    "meteo", "oroscopo", "ricetta", "turismo", "vacanz",
    "incidente stradale", "arrestato", "rapina", "furto", "aggressione",
    "morte", "morto", "deceduto", "funerali", "lutto", "scomparsa",
]

# Signals that a piece of news is commercially actionable.
OPPORTUNITY_KEYWORDS = [
    "gara", "appalto", "bando", "investimento", "digitalizzazione", "software",
    "cloud", "assunzioni", "nuova sede", "partnership", "pnrr", "innovazione",
]

RISK_KEYWORDS = [
    "cyber", "attacco", "sanzione", "multa", "indagine", "crisi", "licenziament",
    "fallimento", "concordato", "sciopero", "data breach",
]


class HeuristicClassifier:
    """Classify news by keyword matching. Free, offline, deterministic."""

    # Kept API-compatible with NewsClassifier so it can be swapped in.
    client = None
    disabled_reason = None

    @staticmethod
    def _count_hits(text: str, keywords: List[str]) -> int:
        return sum(1 for kw in keywords if kw in text)

    def classify_news(
        self,
        company_name: str,
        title: str,
        url: str = None,
        source_name: str = None,
        article_text: str = None,
        ateco_description: str = None,
        account_owner: str = None,
        website: str = None,
        tax_code: str = None,
    ) -> Dict[str, Any]:
        haystack = f"{title} {article_text or ''}".lower()

        category = "Commercial Signal"
        for name, keywords in CATEGORY_KEYWORDS:
            if self._count_hits(haystack, keywords):
                category = name
                break

        noise = self._count_hits(haystack, NOISE_KEYWORDS)
        opportunity = self._count_hits(haystack, OPPORTUNITY_KEYWORDS)
        risk = self._count_hits(haystack, RISK_KEYWORDS)

        # Does the company name actually appear in the text? Whole-word match
        # on the longest token avoids "ASA" matching inside "casa".
        tokens = [t for t in re.split(r"\W+", (company_name or "").lower()) if len(t) > 3]
        name_hit = any(re.search(rf"\b{re.escape(t)}\b", haystack) for t in tokens) if tokens else False

        relevance = 5
        relevance += 2 if opportunity else 0
        relevance += 1 if risk else 0
        relevance -= 3 if noise else 0
        relevance += 1 if name_hit else -1
        relevance = max(1, min(10, relevance))

        return {
            "summary": (article_text or title)[:200],
            "category": category,
            "relevance_score": relevance,
            "urgency_score": min(10, 4 + 2 * risk),
            "commercial_score": min(10, 3 + 2 * opportunity),
            "risk_score": min(10, 3 + 2 * risk),
            # Never claim high confidence: this is keyword matching, not reading.
            "confidence_score": 6 if name_hit else 3,
            "why_it_matters": f"Classificazione automatica per parole chiave (categoria: {category})",
            "suggested_action": "Verifica manuale, oppure attiva la classificazione AI",
            "email_ready_summary": title[:150],
        }

    @staticmethod
    def sdk_supports_messages() -> bool:
        return True

    @staticmethod
    def fallback_result(title: str, why: str, action: str) -> Dict[str, Any]:
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
