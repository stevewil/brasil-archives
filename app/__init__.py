"""Application factory for brasil-archives.

Usage::

    from app import create_app
    app = create_app()

The factory wires up config, extensions (SQLAlchemy, Migrate, Babel),
imports models so migrations can see them, and registers blueprints.
"""
from __future__ import annotations

import os
from pathlib import Path

from flask import Flask, request

from .config import INSTANCE_DIR, resolve_config
from .extensions import babel, csrf, db, migrate


def _select_locale() -> str:
    """Locale selector for Flask-Babel.

    Priority: ``?lang=`` query param → Accept-Language header → default.
    Bilingual PT/EN is a first-class project goal; translations are
    added later.
    """
    from flask import current_app

    supported = current_app.config.get("LANGUAGES", ["en"])
    requested = request.args.get("lang")
    if requested in supported:
        return requested
    best = request.accept_languages.best_match(supported)
    return best or current_app.config.get("BABEL_DEFAULT_LOCALE", "en")


def create_app(config_name: str | None = None) -> Flask:
    """Build and return a configured :class:`~flask.Flask` app."""
    app = Flask(__name__, instance_relative_config=False)
    app.config.from_object(resolve_config(config_name))

    # Ensure instance directory exists for SQLite dev DB
    Path(INSTANCE_DIR).mkdir(parents=True, exist_ok=True)

    # Extensions
    db.init_app(app)
    migrate.init_app(app, db, directory=str(Path(app.root_path).parent / "migrations"))
    babel.init_app(app, locale_selector=_select_locale)
    csrf.init_app(app)

    # Expose get_locale() to Jinja so templates can set <html lang="...">.
    from flask_babel import get_locale
    app.jinja_env.globals["get_locale"] = get_locale

    # Locale-aware vocabulary label helper. Templates call
    # ``vocab_label(obj)`` in place of ``obj.label_en`` so PT visitors
    # see ``label_pt`` where available and fall back cleanly.
    from .i18n import probe_facet_label, vocab_label
    app.jinja_env.globals["vocab_label"] = vocab_label
    app.jinja_env.globals["probe_facet_label"] = probe_facet_label

    # Admin/public split — templates use ``admin_ui_enabled()`` to hide
    # scoring forms, the facet editor, and the Harvest nav link on the
    # public deployment. See app/blueprints/_admin_gate.py.
    app.jinja_env.globals["admin_ui_enabled"] = lambda: bool(
        app.config.get("ADMIN_UI_ENABLED")
    )

    # Public-scores split — templates use ``show_scores()`` to gate the
    # dimension scores, axis totals, quadrant, naive sum, and the
    # score-ranked home block. See app/visibility.py.
    from .visibility import scores_visible
    app.jinja_env.globals["show_scores"] = scores_visible

    # Import models so SQLAlchemy metadata is populated for migrations.
    # Import here (not at module top) to avoid circular imports.
    from . import models  # noqa: F401

    # Per-source schema routing (docs/partner-schema-design.md): clear any
    # ``bind_source()`` binding when the app context tears down so it can't
    # leak from one request into the next on a reused worker thread.
    from .services.sources import reset_source

    @app.teardown_appcontext
    def _reset_source(_exc: BaseException | None) -> None:
        reset_source()

    # Blueprints
    from .blueprints.main import bp as main_bp
    from .blueprints.archives import bp as archives_bp
    from .blueprints.harvest import bp as harvest_bp
    from .blueprints.admin import bp as admin_bp
    from .oai import bp as oai_bp
    app.register_blueprint(main_bp)
    app.register_blueprint(archives_bp)
    app.register_blueprint(harvest_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(oai_bp)

    # The OAI-PMH provider is a public, read-only, machine surface that
    # accepts POST per the spec (§3.1.1). It has no forms and no session,
    # so CSRF protection would only break conformant harvesters.
    csrf.exempt(oai_bp)

    # Health check for deploy monitoring. Runs a real ``SELECT 1`` so a
    # DATABASE_URL that parses but can't be reached (a blocked outbound
    # port, a dead pooler) fails here with 503 instead of only surfacing
    # as a 500 on every content page.
    @app.get("/healthz")
    def healthz() -> tuple[dict[str, object], int] | dict[str, object]:
        from sqlalchemy import text

        payload: dict[str, object] = {
            "status": "ok",
            "app": app.config["APP_NAME"],
            "version": app.config["APP_VERSION"],
            "database": db.engine.dialect.name,  # "sqlite" | "postgresql"
        }
        try:
            db.session.execute(text("SELECT 1"))
            payload["database_connected"] = True
        except Exception as exc:  # noqa: BLE001 - report any failure to the caller
            payload["status"] = "degraded"
            payload["database_connected"] = False
            payload["database_error"] = str(exc)[:200]
            return payload, 503
        return payload

    # Optional fail-fast: verify the database answers before the app serves
    # a single request. Off by default — it would break `flask db upgrade`
    # against a not-yet-created DB and offline dev. Set
    # BRASIL_ARCHIVES_DB_CHECK=1 in the cPanel .env so a bad DATABASE_URL
    # lands in the Passenger startup log instead of as a per-request 500.
    if os.environ.get("BRASIL_ARCHIVES_DB_CHECK") == "1":
        import logging

        from sqlalchemy import text

        log = logging.getLogger("brasil_archives")
        with app.app_context():
            try:
                db.session.execute(text("SELECT 1"))
                log.info(
                    "database connectivity OK (%s)", db.engine.dialect.name
                )
            except Exception:
                log.exception(
                    "database unreachable at startup — check DATABASE_URL "
                    "and that the host can reach the Postgres pooler"
                )
                raise

    return app
