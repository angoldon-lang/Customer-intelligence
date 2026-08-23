"""Settings persisted in the database, overriding .env at runtime.

Lets SMTP and the default filters be changed from Impostazioni without
editing files or restarting the server. Anything not saved here falls back
to the corresponding environment variable.
"""

from typing import Any, Dict
from sqlalchemy.orm import Session
from app.models import AppSetting
from app.config import settings

# key -> (env fallback attribute, type)
KNOWN_SETTINGS = {
    "SMTP_HOST": ("SMTP_HOST", str),
    "SMTP_PORT": ("SMTP_PORT", int),
    "SMTP_USER": ("SMTP_USER", str),
    "SMTP_PASSWORD": ("SMTP_PASSWORD", str),
    "SMTP_FROM_EMAIL": ("SMTP_FROM_EMAIL", str),
    "SMTP_FROM_NAME": ("SMTP_FROM_NAME", str),
    "DEFAULT_COMPANY_TYPE": ("DEFAULT_COMPANY_TYPE", str),
    "DEFAULT_COMPANY_STATUS": ("DEFAULT_COMPANY_STATUS", str),
    "MIN_RELEVANCE_SCORE": ("MIN_RELEVANCE_SCORE", int),
    "CLASSIFIER_MODE": ("CLASSIFIER_MODE", str),
    "CLAUDE_MODEL": ("CLAUDE_MODEL", str),
}

# Never send these back to the browser.
SECRET_KEYS = {"SMTP_PASSWORD"}


def get_setting(db: Session, key: str) -> Any:
    """Stored value if present, otherwise the .env fallback."""
    env_attr, caster = KNOWN_SETTINGS.get(key, (key, str))

    row = db.query(AppSetting).filter_by(key=key).first()
    if row and row.value is not None:
        try:
            return caster(row.value)
        except (TypeError, ValueError):
            return row.value

    return getattr(settings, env_attr, None)


def get_all(db: Session, include_secrets: bool = False) -> Dict[str, Any]:
    values = {key: get_setting(db, key) for key in KNOWN_SETTINGS}
    if not include_secrets:
        for key in SECRET_KEYS:
            # Report only whether it's set, never the value itself.
            values[key] = bool(values.get(key))
    return values


def apply_to_runtime(db: Session) -> None:
    """
    Copy the stored settings onto the live `settings` object.

    Everything in the app reads configuration through `app.config.settings`,
    so this is what makes a value saved from Impostazioni take effect
    without a restart. Called at startup and after every save.
    """
    for key in KNOWN_SETTINGS:
        row = db.query(AppSetting).filter_by(key=key).first()
        if not row or row.value is None:
            continue

        _, caster = KNOWN_SETTINGS[key]
        try:
            value = caster(row.value)
        except (TypeError, ValueError):
            continue

        if key == "CLASSIFIER_MODE" and isinstance(value, str):
            value = value.lower()

        setattr(settings, key, value)


def save_settings(db: Session, updates: Dict[str, Any]) -> Dict[str, Any]:
    """Persist the given settings; unknown keys are ignored."""
    saved = {}
    for key, value in updates.items():
        if key not in KNOWN_SETTINGS:
            continue
        # An empty password field means "leave the stored one alone",
        # otherwise saving the form would silently wipe it.
        if key in SECRET_KEYS and value in (None, ""):
            continue

        row = db.query(AppSetting).filter_by(key=key).first()
        if row:
            row.value = None if value is None else str(value)
        else:
            db.add(AppSetting(key=key, value=None if value is None else str(value)))
        saved[key] = "***" if key in SECRET_KEYS else value

    db.commit()
    apply_to_runtime(db)
    return saved
