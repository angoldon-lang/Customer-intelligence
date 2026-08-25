"""Google News RSS provider - free, no API key required.

Uses the public RSS search feed (not the HTML search page, which is
protected by a cookie-consent wall and blocked scraping in earlier
attempts). This endpoint returns plain XML and tends to have much better
coverage of small/local businesses than GDELT or GNews.io, which mostly
index larger outlets.
"""

from typing import List, Dict, Any
from datetime import datetime
from urllib.parse import quote_plus
from html import unescape
import base64
import re
import time
import requests
import feedparser
from app.providers.base import NewsSourceProvider, NewsArticle
from app.config import settings

GOOGLE_NEWS_RSS_ENDPOINT = "https://news.google.com/rss/search"

# Google News throttles bursts with 503/429. Keeping a comfortable gap
# between requests is what actually prevents them; retries only paper over
# a rate that is already too fast.
MIN_REQUEST_INTERVAL = 2.5  # seconds between requests

# Transient HTTP statuses: retried with backoff instead of counting as a
# provider failure. 503 in particular is Google's "slow down", not an
# outage, and treating it as fatal used to kill the whole run.
RETRY_STATUSES = {429, 500, 502, 503, 504}
RETRY_BACKOFF = [5, 15, 40]  # seconds before each retry

# A connection error (no network, DNS, proxy) won't clear in 40s and would
# apply to every company, so it gets one quick retry instead of the full
# ladder; the consecutive-failure breaker then pauses the provider.
CONNECTION_RETRY_BACKOFF = [3]

# Used once the previous company already failed: Google is throttling us,
# not hiccuping, so one short retry then move on to the pause.
SATURATED_BACKOFF = [5]

# After this many consecutive failed companies the provider pauses (it is
# clearly not working right now), then reopens automatically so a temporary
# block doesn't skip every remaining company in the run.
MAX_CONSECUTIVE_FAILURES = 4
COOLDOWN_SECONDS = 180
# If it's still blocked after a pause, wait longer each time instead of
# retrying every 3 minutes for the whole run.
MAX_COOLDOWN_SECONDS = 1800

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"


class GoogleNewsRSSProvider(NewsSourceProvider):
    """Search Google News via its public RSS search feed."""

    def __init__(self, timeout: int = None, days: int = 30):
        self.timeout = timeout or settings.NEWS_SEARCH_TIMEOUT
        self.days = days
        self._last_request_at = 0.0
        self.blocked = False
        self._blocked_until = 0.0
        self._cooldown = COOLDOWN_SECONDS
        self._pauses = 0
        self._consecutive_failures = 0
        self.last_call_error = None
        self._skip_notice_shown = False

    def _throttle(self):
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < MIN_REQUEST_INTERVAL:
            time.sleep(MIN_REQUEST_INTERVAL - elapsed)
        self._last_request_at = time.monotonic()

    def _record_failure(self, reason: str):
        """
        Pause the provider after repeated failures, don't kill it.

        Google News is the main free source: disabling it for the rest of
        the run (the old behaviour, after just 2 errors) meant one burst of
        503s left every remaining company unsearched. Now it pauses and
        reopens by itself after a cooldown.
        """
        self._consecutive_failures += 1
        if self._consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
            self.blocked = True
            self._cooldown = min(self._cooldown * 2, MAX_COOLDOWN_SECONDS) if self._pauses else COOLDOWN_SECONDS
            self._pauses += 1
            self._blocked_until = time.monotonic() + self._cooldown
            self._skip_notice_shown = False
            print(
                f"[GoogleNewsRSS] {reason}: {self._consecutive_failures} fallimenti consecutivi, "
                f"pausa di {self._cooldown}s poi riprova automaticamente"
            )
        else:
            print(
                f"[GoogleNewsRSS] {reason} "
                f"({self._consecutive_failures}/{MAX_CONSECUTIVE_FAILURES} prima della pausa)"
            )

    def _cooldown_expired(self) -> bool:
        """Reopen the circuit once the cooldown has elapsed (half-open)."""
        if not self.blocked:
            return True
        if time.monotonic() < self._blocked_until:
            return False

        print("[GoogleNewsRSS] Pausa terminata, riprovo")
        self.blocked = False
        self._consecutive_failures = 0
        self._skip_notice_shown = False
        return True

    def _get_with_retry(self, params: dict, company_name: str):
        """
        GET the feed, retrying transient errors with backoff.

        Returns the response, or None if every attempt failed (the reason is
        left in self.last_call_error).
        """
        # The full ladder is worth it when the provider is otherwise
        # healthy: one company hit a blip. Once the previous company has
        # already failed, Google is throttling us systematically and
        # retrying each company for a minute only delays the pause, so
        # shorten the ladder to a single quick attempt.
        status_backoff = RETRY_BACKOFF if self._consecutive_failures == 0 else SATURATED_BACKOFF
        attempts = len(status_backoff) + 1

        for attempt in range(attempts):
            self._throttle()
            try:
                response = requests.get(
                    GOOGLE_NEWS_RSS_ENDPOINT,
                    params=params,
                    timeout=self.timeout,
                    headers={"User-Agent": USER_AGENT},
                )
            except requests.RequestException as e:
                self.last_call_error = "request exception"
                backoff = (
                    CONNECTION_RETRY_BACKOFF
                    if isinstance(e, requests.ConnectionError)
                    else status_backoff
                )
                if attempt >= len(backoff):
                    print(f"[GoogleNewsRSS] Error searching '{company_name}': {e}")
                    return None
                wait = backoff[attempt]
                print(f"[GoogleNewsRSS] '{company_name}': {type(e).__name__}, riprovo tra {wait}s")
                time.sleep(wait)
                continue

            if response.status_code in RETRY_STATUSES:
                self.last_call_error = f"HTTP {response.status_code}"
                if attempt == attempts - 1:
                    print(
                        f"[GoogleNewsRSS] '{company_name}': HTTP {response.status_code} "
                        f"dopo {attempts} tentativi"
                    )
                    return None
                # Honour Retry-After when Google sends one.
                wait = status_backoff[attempt]
                retry_after = response.headers.get("Retry-After")
                if retry_after and retry_after.isdigit():
                    wait = max(wait, min(int(retry_after), 120))
                print(
                    f"[GoogleNewsRSS] '{company_name}': HTTP {response.status_code} "
                    f"(temporaneo), riprovo tra {wait}s"
                )
                time.sleep(wait)
                continue

            if response.status_code == 403:
                # Not transient: a consent/robot wall, retrying won't help.
                self.last_call_error = "HTTP 403"
                print(f"[GoogleNewsRSS] '{company_name}': HTTP 403 (bloccato)")
                return None

            try:
                response.raise_for_status()
            except requests.RequestException as e:
                self.last_call_error = f"HTTP {response.status_code}"
                print(f"[GoogleNewsRSS] Error searching '{company_name}': {e}")
                return None

            # Clear the error left by an earlier attempt: this company was
            # searched successfully, and a stale reason here would show it
            # as blocked on the coverage page.
            self.last_call_error = None
            return response

        return None

    def search_company_news(
        self, company_name: str, keywords: List[str] = None
    ) -> List[NewsArticle]:
        # Reset per-call: distinguishes "0 results, request genuinely
        # succeeded" from "0 results because this specific call failed"
        # (which the `blocked` flag alone can't show before the circuit
        # breaker actually trips).
        self.last_call_error = None

        if not self._cooldown_expired():
            if not self._skip_notice_shown:
                remaining = int(self._blocked_until - time.monotonic())
                print(
                    f"[GoogleNewsRSS] In pausa per altri ~{remaining}s "
                    f"(troppi errori consecutivi): le aziende di questo intervallo vengono saltate"
                )
                self._skip_notice_shown = True
            self.last_call_error = "in pausa dopo errori ripetuti"
            return []

        query = f'"{company_name}" when:{self.days}d'
        if keywords:
            query += " " + " ".join(keywords)

        ceid = f"{settings.NEWS_COUNTRY}:{settings.NEWS_LANGUAGE}"
        params = {
            "q": query,
            "hl": settings.NEWS_LANGUAGE,
            "gl": settings.NEWS_COUNTRY,
            "ceid": ceid,
        }

        response = self._get_with_retry(params, company_name)
        if response is None:
            self._record_failure(self.last_call_error or "richiesta fallita")
            return []

        parsed = feedparser.parse(response.content)

        if parsed.bozo and not parsed.entries:
            # A 200 OK with a malformed/non-RSS body (e.g. a consent or
            # CAPTCHA page) - feedparser silently returns 0 entries with no
            # exception, so without this check a block looks identical to
            # "genuinely no news found".
            print(f"[GoogleNewsRSS] Response for '{company_name}' wasn't valid RSS ({parsed.get('bozo_exception')}), likely blocked")
            self._record_failure("malformed RSS response")
            self.last_call_error = "malformed RSS response"
            return []

        # A clean search means the provider recovered: start the pause
        # ladder from scratch if it gets blocked again later on.
        self._consecutive_failures = 0
        self._cooldown = COOLDOWN_SECONDS
        self._pauses = 0
        results = []

        for entry in parsed.entries:
            title = entry.get("title")
            url = entry.get("link")
            if not title or not url:
                continue

            source_name = "Google News"
            source_obj = entry.get("source")
            if isinstance(source_obj, dict) and source_obj.get("title"):
                source_name = source_obj["title"]
            elif " - " in title:
                # Google News often suffixes the title with " - Source Name"
                title, _, maybe_source = title.rpartition(" - ")
                source_name = maybe_source or source_name

            results.append(NewsArticle(
                title=title,
                url=self.normalize_article_url(url, title),
                source_name=source_name,
                source_type="google_news_rss",
                published_date=self._parse_entry_date(entry),
                summary=self.clean_summary(entry.get("summary"), title),
                access_status="available",
                license_scope="summary_allowed",
            ))

        return results

    @staticmethod
    def clean_summary(summary: str, title: str = None) -> str:
        """
        Google News puts markup, not prose, in <description>: typically just
        an <a> wrapping the headline plus the publisher name. Rendered raw it
        shows as literal HTML in the card, and it adds nothing over the title,
        so strip the tags and drop it when it merely repeats the headline.
        """
        if not summary:
            return None

        text = re.sub(r"<[^>]+>", " ", summary)
        # A summary cut short mid-tag (something upstream truncated it)
        # leaves "<a href="https://news.google.com/rss/articles/CBMixgF..."
        # with no closing ">", which the rule above cannot match: the raw
        # markup then reached the card verbatim. Drop the dangling fragment.
        text = re.sub(r"<[^>]*$", " ", text)
        text = unescape(text)
        text = re.sub(r"\s+", " ", text).strip()

        if not text:
            return None

        # What survives is sometimes just the article URL (the anchor's href
        # with its text truncated away): a link is not a summary.
        if re.fullmatch(r"https?://\S*", text):
            return None

        def key(value: str) -> str:
            return re.sub(r"\W+", "", (value or "")).lower()

        if title and key(text)[:60] == key(title)[:60]:
            return None
        return text

    @staticmethod
    def normalize_article_url(url: str, title: str = None) -> str:
        """
        Turn an RSS item link into one a browser can actually open.

        Google News RSS items link to news.google.com/rss/articles/<id>.
        A browser opening that path gets the RSS XML back, or a redirect to
        /rss/unsupported - never the article. Two cases:

        * Older ids embed the publisher URL in a base64 protobuf: decode it
          and return the real article link (best outcome).
        * Newer ids (AU_yqL...) are opaque and can only be resolved by
          Google itself, so fall back to a news search on the headline,
          which reliably lands on the article.
        """
        if not url or "news.google.com" not in url:
            return url

        match = re.search(r"/articles/([A-Za-z0-9_\-]+)", url)
        if match:
            decoded = GoogleNewsRSSProvider._decode_article_id(match.group(1))
            if decoded:
                return decoded

        if title:
            # Strip the " - Publisher" suffix Google appends to headlines.
            query = re.sub(r"\s+-\s+[^-]+$", "", title).strip() or title
            return "https://www.google.com/search?q=" + quote_plus(query)

        # No title to search on. Returning the /rss/ link would hand back a
        # URL we know opens raw XML ("Questo feed non e' disponibile"), so
        # send the reader to Google News rather than to a dead end.
        if "/rss/" in url:
            return "https://news.google.com/"

        return url

    @staticmethod
    def _decode_article_id(article_id: str) -> str:
        """Extract the publisher URL from a Google News article id, if present."""
        try:
            padded = article_id + "=" * (-len(article_id) % 4)
            raw = base64.urlsafe_b64decode(padded)
        except Exception:
            return None

        # The payload is a small protobuf. Read length-delimited fields
        # (tag 0x22 = field 4, wire type 2) properly rather than regexing
        # for "http", which can't tell where the string ends and would drag
        # in the next field's tag byte.
        i = 0
        while i < len(raw):
            if raw[i] != 0x22:
                i += 1
                continue
            i += 1
            length, shift = 0, 0
            while i < len(raw):
                byte = raw[i]
                i += 1
                length |= (byte & 0x7F) << shift
                if not byte & 0x80:
                    break
                shift += 7
            value = raw[i:i + length]
            i += length
            if value.startswith((b"http://", b"https://")):
                candidate = value.decode("utf-8", errors="ignore")
                if "news.google.com" not in candidate:
                    return candidate
        return None

    @staticmethod
    def _parse_entry_date(entry) -> datetime:
        parsed_time = entry.get("published_parsed")
        if parsed_time:
            return datetime(*parsed_time[:6])
        return datetime.utcnow()

    def fetch_article_metadata(self, url: str) -> Dict[str, Any]:
        return {"title": None, "published_date": None, "summary": None, "source": "google_news_rss"}

    def fetch_article_content(self, url: str) -> str:
        return None

    def check_access(self) -> bool:
        try:
            response = requests.get(
                GOOGLE_NEWS_RSS_ENDPOINT,
                params={"q": "test", "hl": "it", "gl": "IT", "ceid": "IT:it"},
                timeout=self.timeout,
                headers={"User-Agent": USER_AGENT},
            )
            return response.status_code == 200
        except requests.RequestException:
            return False

    def is_enabled(self) -> bool:
        return settings.GOOGLE_NEWS_RSS_ENABLED
