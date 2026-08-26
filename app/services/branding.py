"""Report branding: logo, colours and the texts around the news.

The logo travels as an inline MIME attachment referenced by `cid:`, not as
a data: URI and not as a remote URL: Gmail and Outlook strip data: images,
and a link to http://127.0.0.1 is unreachable for anyone receiving the
email.
"""

import os
from typing import Any, Dict

from sqlalchemy.orm import Session

from app.config import settings

# Where uploaded logos live. Served from /static for the dashboard preview
# and read from disk when an email is sent.
LOGO_DIR = os.path.join("app", "static", "branding")

# Content-ID used in the HTML (<img src="cid:brandlogo">) and set on the
# attachment. The two must match or the image shows as broken.
LOGO_CID = "brandlogo"

ALLOWED_LOGO_TYPES = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/gif": ".gif",
}
MAX_LOGO_BYTES = 1_000_000


def logo_path(db: Session) -> str:
    """Absolute-ish path of the configured logo, or None."""
    from app.services import settings_store

    filename = settings_store.get_setting(db, "BRAND_LOGO")
    if not filename:
        return None

    # Guard against a stored value trying to escape the directory.
    filename = os.path.basename(filename)
    path = os.path.join(LOGO_DIR, filename)
    return path if os.path.exists(path) else None


def get_branding(db: Session) -> Dict[str, Any]:
    """Everything the report generator needs to style an email."""
    from app.services import settings_store

    def value(key, fallback):
        stored = settings_store.get_setting(db, key)
        return stored if stored not in (None, "") else fallback

    return {
        "name": value("BRAND_NAME", settings.BRAND_NAME),
        "color": _safe_color(value("BRAND_COLOR", settings.BRAND_COLOR)),
        "intro": value("REPORT_INTRO", settings.REPORT_INTRO),
        "footer": value("REPORT_FOOTER", settings.REPORT_FOOTER),
        "show_scores": bool(value("REPORT_SHOW_SCORES", settings.REPORT_SHOW_SCORES)),
        "logo_path": logo_path(db),
        "logo_cid": LOGO_CID,
    }


def default_branding() -> Dict[str, Any]:
    """Branding without a database session (background jobs, tests)."""
    return {
        "name": settings.BRAND_NAME,
        "color": _safe_color(settings.BRAND_COLOR),
        "intro": settings.REPORT_INTRO,
        "footer": settings.REPORT_FOOTER,
        "show_scores": settings.REPORT_SHOW_SCORES,
        "logo_path": None,
        "logo_cid": LOGO_CID,
    }


def _safe_color(value: str) -> str:
    """
    Accept only a hex colour.

    The value is interpolated straight into the email's CSS, so anything
    else could inject style rules - and a typo would silently break the
    header rather than falling back to the default.
    """
    import re

    candidate = (value or "").strip()
    if re.fullmatch(r"#[0-9a-fA-F]{3}|#[0-9a-fA-F]{6}", candidate):
        return candidate
    return "#2c3e50"


def save_logo(db: Session, content: bytes, content_type: str, filename: str) -> str:
    """Store an uploaded logo and record it in the settings."""
    from app.services import settings_store

    if content_type not in ALLOWED_LOGO_TYPES:
        raise ValueError(
            f"Formato non supportato ({content_type}). Usa PNG, JPG o GIF."
        )
    if len(content) > MAX_LOGO_BYTES:
        raise ValueError(
            f"Il file supera {MAX_LOGO_BYTES // 1000} KB: usa un logo piu' leggero."
        )
    if not content:
        raise ValueError("File vuoto")

    os.makedirs(LOGO_DIR, exist_ok=True)

    # One fixed name per type: re-uploading replaces the logo instead of
    # leaving orphan files behind.
    target = "logo" + ALLOWED_LOGO_TYPES[content_type]
    for extension in set(ALLOWED_LOGO_TYPES.values()):
        stale = os.path.join(LOGO_DIR, "logo" + extension)
        if os.path.exists(stale):
            os.remove(stale)

    with open(os.path.join(LOGO_DIR, target), "wb") as handle:
        handle.write(content)

    settings_store.save_settings(db, {"BRAND_LOGO": target})
    return target


def remove_logo(db: Session) -> bool:
    """Delete the stored logo. True if there was one."""
    from app.services import settings_store

    path = logo_path(db)
    settings_store.save_settings(db, {"BRAND_LOGO": ""})
    if path and os.path.exists(path):
        os.remove(path)
        return True
    return False
