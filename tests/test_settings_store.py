"""Tests for DB-backed settings (Impostazioni -> app_settings)."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import Base, AppSetting
from app.config import settings as env_settings
from app.services import settings_store


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def test_falls_back_to_env_when_nothing_saved(db):
    assert settings_store.get_setting(db, "SMTP_HOST") == env_settings.SMTP_HOST


def test_saved_value_overrides_env(db):
    settings_store.save_settings(db, {"SMTP_HOST": "smtp.example.it"})

    assert settings_store.get_setting(db, "SMTP_HOST") == "smtp.example.it"


def test_value_is_cast_to_declared_type(db):
    settings_store.save_settings(db, {"SMTP_PORT": "2525"})

    assert settings_store.get_setting(db, "SMTP_PORT") == 2525


def test_unknown_keys_are_ignored(db):
    saved = settings_store.save_settings(db, {"NOT_A_SETTING": "x", "SMTP_USER": "u@x.it"})

    assert "NOT_A_SETTING" not in saved
    assert db.query(AppSetting).filter_by(key="NOT_A_SETTING").first() is None


def test_saving_again_updates_in_place(db):
    settings_store.save_settings(db, {"SMTP_HOST": "one.it"})
    settings_store.save_settings(db, {"SMTP_HOST": "two.it"})

    rows = db.query(AppSetting).filter_by(key="SMTP_HOST").all()
    assert len(rows) == 1
    assert rows[0].value == "two.it"


def test_empty_password_does_not_wipe_the_stored_one(db):
    """Saving the SMTP form with a blank password must keep the old one."""
    settings_store.save_settings(db, {"SMTP_PASSWORD": "app-password"})
    settings_store.save_settings(db, {"SMTP_PASSWORD": "", "SMTP_HOST": "smtp.example.it"})

    assert settings_store.get_setting(db, "SMTP_PASSWORD") == "app-password"


def test_saving_applies_to_the_live_config(db):
    """A saved value must take effect without restarting the server."""
    original = env_settings.MIN_RELEVANCE_SCORE
    try:
        settings_store.save_settings(db, {"MIN_RELEVANCE_SCORE": 9})
        assert env_settings.MIN_RELEVANCE_SCORE == 9
    finally:
        env_settings.MIN_RELEVANCE_SCORE = original


def test_classifier_mode_is_normalised_to_lowercase(db):
    original = env_settings.CLASSIFIER_MODE
    try:
        settings_store.save_settings(db, {"CLASSIFIER_MODE": "HEURISTIC"})
        assert env_settings.CLASSIFIER_MODE == "heuristic"
    finally:
        env_settings.CLASSIFIER_MODE = original


def test_classifier_mode_change_applies_to_the_next_run(db):
    """Switching to the free classifier must not need a restart."""
    from app.services.news_searcher import NewsSearcher
    from app.services.heuristic_classifier import HeuristicClassifier

    original = env_settings.CLASSIFIER_MODE
    try:
        env_settings.CLASSIFIER_MODE = "ai"
        searcher = NewsSearcher()
        assert not isinstance(searcher.classifier, HeuristicClassifier)

        settings_store.save_settings(db, {"CLASSIFIER_MODE": "heuristic"})
        assert isinstance(searcher._build_classifier(), HeuristicClassifier)
    finally:
        env_settings.CLASSIFIER_MODE = original


def test_get_all_never_leaks_the_password(db):
    settings_store.save_settings(db, {"SMTP_PASSWORD": "app-password"})

    values = settings_store.get_all(db)
    assert values["SMTP_PASSWORD"] is True  # only "one is set", never the value

    assert settings_store.get_all(db, include_secrets=True)["SMTP_PASSWORD"] == "app-password"
