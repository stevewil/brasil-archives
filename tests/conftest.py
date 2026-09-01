"""Shared pytest fixtures for brasil-archives."""
from __future__ import annotations

import pytest

from app import create_app
from app.extensions import db as _db


@pytest.fixture
def app():
    """Testing app.

    In-memory SQLite by default; a real Postgres when ``TEST_DATABASE_URL``
    is set (the CI fidelity job — see ``app/config.py``). ``drop_all`` runs
    on both sides of the test so a Postgres DB left dirty by an earlier
    failure can't leak into the next test.
    """
    app = create_app("testing")
    with app.app_context():
        _db.drop_all()
        _db.create_all()
        yield app
        _db.session.remove()
        _db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def db(app):
    return _db
