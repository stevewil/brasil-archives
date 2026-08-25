"""Flask extension singletons.

Kept out of :mod:`app.__init__` so that models and blueprints can import
``db`` without triggering circular imports through the app factory.
"""
from __future__ import annotations

from flask_babel import Babel
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import CSRFProtect
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


db = SQLAlchemy(model_class=Base)
migrate = Migrate()
babel = Babel()
csrf = CSRFProtect()
