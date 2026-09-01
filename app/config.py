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


def _engine_options(uri: str) -> dict:
    """SQLAlchemy engine options, Postgres only.

    On cPanel the app runs under Passenger prefork; a socket-based
    connection pool inherited across a fork is a hazard. The robust
    answer for a low-traffic catalog site is to not pool in the app and
    let Supabase's Supavisor pooler do it — hence ``NullPool`` by
    default whenever the URL is Postgres. Set ``DB_NULLPOOL=0`` to keep
    normal pooling (useful against a local Postgres in dev).

    ``pool_pre_ping`` recycles connections dropped by the pooler; the
    ``connect_args`` cap a hung connect and a runaway query. TLS comes
    from ``?sslmode=require`` in ``DATABASE_URL`` (see
    docs/supabase-migration-spec.md §4).
    """
    if not uri.startswith("postgresql"):
        return {}
    opts: dict = {
        "pool_pre_ping": True,
        "connect_args": {
            "connect_timeout": 10,
            "options": "-c statement_timeout=15000",
        },
    }
    if os.environ.get("DB_NULLPOOL", "1") != "0":
        import sqlalchemy.pool

        opts["poolclass"] = sqlalchemy.pool.NullPool
    return opts


class BaseConfig:
    """Shared defaults."""

    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-me")

    # SQLAlchemy
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL",
        f"sqlite:///{INSTANCE_DIR / 'brasil_archives.db'}",
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = _engine_options(SQLALCHEMY_DATABASE_URI)

    # Babel — bilingual PT/EN, translations added later
    BABEL_DEFAULT_LOCALE = os.environ.get("BABEL_DEFAULT_LOCALE", "en")
    BABEL_DEFAULT_TIMEZONE = os.environ.get("BABEL_DEFAULT_TIMEZONE", "UTC")
    LANGUAGES = ["en", "pt"]

    # App identity
    APP_NAME = "brasil-archives"
    APP_VERSION = "0.1.0"

    # OAI-PMH provider identity (docs/oai-pmh-provider.md). The
    # repository identifier is the host name used in ``oai:<id>:archive:<slug>``
    # identifiers and the <oai-identifier> description block; keep it stable
    # once published to a registry.
    OAI_REPOSITORY_NAME = os.environ.get(
        "OAI_REPOSITORY_NAME",
        "brasil-archives — Catálogo de arquivos digitais brasileiros",
    )
    OAI_REPOSITORY_IDENTIFIER = os.environ.get(
        "OAI_REPOSITORY_IDENTIFIER", "brasil-archives.from-bottom-to.top"
    )
    OAI_ADMIN_EMAIL = os.environ.get("OAI_ADMIN_EMAIL", "stevewil@gmail.com")
    OAI_PAGE_SIZE = int(os.environ.get("OAI_PAGE_SIZE", "100"))

    # Admin/public split. When false (the public default), the scoring
    # forms, the facet editor, and the whole /harvest surface return 404.
    # Set BRASIL_ARCHIVES_ADMIN=1 on the internal deployment only.
    ADMIN_UI_ENABLED = os.environ.get("BRASIL_ARCHIVES_ADMIN") == "1"

    # Public-scores visibility. When false (the public default), the
    # scored judgments — dimension scores, the two axis totals, the
    # quadrant label, the legacy naive sum, and the score-ranked home
    # block — are hidden from the public UI; the catalog and federated
    # search still work. Independent of ADMIN_UI_ENABLED: the internal
    # deployment always sees scores. Set BRASIL_ARCHIVES_PUBLIC_SCORES=1
    # once the judgments are trustworthy enough to publish. See
    # app/visibility.py and docs/DEPLOY.md.
    PUBLIC_SCORES_ENABLED = os.environ.get("BRASIL_ARCHIVES_PUBLIC_SCORES") == "1"


class DevelopmentConfig(BaseConfig):
    DEBUG = True


class TestingConfig(BaseConfig):
    TESTING = True
    DEBUG = False
    # Default: isolated in-memory SQLite per test run. Set TEST_DATABASE_URL
    # to run the suite against a real Postgres (the CI fidelity job, or a
    # local `docker run postgres`). Engine options are forced empty here —
    # the base class computed them from DATABASE_URL, and NullPool /
    # statement_timeout are wrong for a fast test loop.
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "TEST_DATABASE_URL", "sqlite:///:memory:"
    )
    SQLALCHEMY_ENGINE_OPTIONS: dict = {}
    WTF_CSRF_ENABLED = False
    SECRET_KEY = "testing-secret"
    # Exercise the full internal UI by default; the gate itself is
    # covered by tests that build an app with this flipped off.
    ADMIN_UI_ENABLED = True
    # Score-display tests assume scores are visible; the public-scores
    # gate is covered by tests that build an app with this flipped off
    # (tests/test_public_scores_gate.py).
    PUBLIC_SCORES_ENABLED = True


class ProductionConfig(BaseConfig):
    DEBUG = False


CONFIG_MAP = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}


def resolve_config(name: str | None) -> type[BaseConfig]:
    """Return the config class for ``name``, defaulting to development.

    For production, refuse to return the class unless SECRET_KEY is set
    to a real value. A known-public session-signing key would make every
    cookie and CSRF token forgeable, so this is a hard failure.
    """
    if name is None:
        name = os.environ.get("BRASIL_ARCHIVES_CONFIG", "development")
    cls = CONFIG_MAP.get(name, DevelopmentConfig)
    if cls is ProductionConfig:
        secret = os.environ.get("SECRET_KEY")
        if not secret or secret == "dev-secret-change-me":
            raise RuntimeError(
                "SECRET_KEY environment variable must be set to a strong "
                "random value in production. Generate one with: "
                "python -c 'import secrets; print(secrets.token_hex(32))'"
            )
    return cls
