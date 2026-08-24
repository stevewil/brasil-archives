"""Configuration classes for brasil-archives.

Loaded by the app factory based on ``BRASIL_ARCHIVES_CONFIG`` env var or
the ``config_name`` argument to :func:`app.create_app`. Values default
to development-friendly settings; secrets should be overridden via env.
"""
from __future__ import annotations

import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
INSTANCE_DIR = BASE_DIR / "instance"


class BaseConfig:
    """Shared defaults."""

    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-me")

    # SQLAlchemy
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL",
        f"sqlite:///{INSTANCE_DIR / 'brasil_archives.db'}",
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Babel — bilingual PT/EN, translations added later
    BABEL_DEFAULT_LOCALE = os.environ.get("BABEL_DEFAULT_LOCALE", "en")
    BABEL_DEFAULT_TIMEZONE = os.environ.get("BABEL_DEFAULT_TIMEZONE", "UTC")
    LANGUAGES = ["en", "pt"]

    # App identity
    APP_NAME = "brasil-archives"
    APP_VERSION = "0.1.0"


class DevelopmentConfig(BaseConfig):
    DEBUG = True


class TestingConfig(BaseConfig):
    TESTING = True
    DEBUG = False
    # Isolated in-memory DB per test run
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    WTF_CSRF_ENABLED = False
    SECRET_KEY = "testing-secret"


class ProductionConfig(BaseConfig):
    DEBUG = False


CONFIG_MAP = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}


def resolve_config(name: str | None) -> type[BaseConfig]:
    """Return the config class for ``name``, defaulting to development."""
    if name is None:
        name = os.environ.get("BRASIL_ARCHIVES_CONFIG", "development")
    return CONFIG_MAP.get(name, DevelopmentConfig)
