"""Shared pytest fixtures for brasil-archives."""
from __future__ import annotations

import pytest
from sqlalchemy import text

from app import create_app
from app.extensions import db as _db
from app.services.sources import drop_source_views, rebuild_source_views


@pytest.fixture(scope="session", autouse=True)
def _ensure_src_test_schema():
    """On Postgres the per-source models resolve their symbolic ``"source"``
    schema to a single ``src_test`` schema (see ``app/config.py``); it must
    exist before any ``create_all``. No-op on SQLite."""
    app = create_app("testing")
    with app.app_context():
        if _db.engine.dialect.name == "postgresql":
            with _db.engine.begin() as conn:
                # scrub any real per-source schemas a prior aborted run left
                stale = conn.execute(text(
                    "select schema_name from information_schema.schemata "
                    "where schema_name like 'src\\_%' and schema_name <> 'src_test'"
                )).scalars().all()
                for s in stale:
                    conn.execute(text(f'DROP SCHEMA IF EXISTS "{s}" CASCADE'))
                conn.execute(text("CREATE SCHEMA IF NOT EXISTS src_test"))
    yield


@pytest.fixture
def app():
    """Testing app.

    In-memory SQLite by default; a real Postgres when ``TEST_DATABASE_URL``
    is set (the CI fidelity job — see ``app/config.py``). The per-source
    models resolve their symbolic ``"source"`` schema to a single
    ``src_test`` schema on Postgres (``None`` on SQLite), so the suite
    exercises one source namespace exactly as before the per-source split.
    ``drop_all`` runs on both sides so a Postgres DB left dirty by an
    earlier failure can't leak.
    """
    app = create_app("testing")
    with app.app_context():
        drop_source_views(_db.engine)
        _db.drop_all()
        _db.create_all()
        rebuild_source_views(_db.engine)
        yield app
        _db.session.remove()
        drop_source_views(_db.engine)
        _db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def db(app):
    return _db
