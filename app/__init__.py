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
    from .i18n import vocab_label
    app.jinja_env.globals["vocab_label"] = vocab_label

    # Import models so SQLAlchemy metadata is populated for migrations.
    # Import here (not at module top) to avoid circular imports.
    from . import models  # noqa: F401

    # Blueprints
    from .blueprints.main import bp as main_bp
    from .blueprints.archives import bp as archives_bp
    from .blueprints.harvest import bp as harvest_bp
    app.register_blueprint(main_bp)
    app.register_blueprint(archives_bp)
    app.register_blueprint(harvest_bp)

    # Simple health check for deploy monitoring
    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok", "app": app.config["APP_NAME"], "version": app.config["APP_VERSION"]}

    return app
