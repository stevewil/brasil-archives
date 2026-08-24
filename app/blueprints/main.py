"""Main blueprint — landing page and (later) archives index."""
from __future__ import annotations

from flask import Blueprint, render_template
from flask_babel import lazy_gettext as _l
from sqlalchemy import func, select

from ..extensions import db
from ..models import Archive, UpgradeProject

bp = Blueprint("main", __name__)


@bp.get("/")
def index() -> str:
    """Landing page — shows counts once the DB is populated."""
    archive_count = db.session.scalar(select(func.count()).select_from(Archive)) or 0
    upgrade_count = db.session.scalar(select(func.count()).select_from(UpgradeProject)) or 0
    return render_template(
        "index.html",
        page_title=_l("Brazilian Digital Archives"),
        archive_count=archive_count,
        upgrade_count=upgrade_count,
    )
