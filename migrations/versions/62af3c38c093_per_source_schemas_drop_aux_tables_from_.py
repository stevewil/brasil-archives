"""per-source schemas: drop aux tables from public on Postgres

Revision ID: 62af3c38c093
Revises: e2c3d4f5a6b7
Create Date: 2026-08-31 18:01:57.653786

The four harvested-data tables (``aggregated_records``, ``harvest_runs``,
``harvest_errors``, ``federation_cache``) were created in ``public`` by the
earlier migrations. Under the per-source design they instead live in
per-partner ``src_<slug>`` schemas, stamped from the model definitions by
``app/services/sources.py::ensure_source_schema`` (run by
``scripts/load_upgrade_projects``). So on Postgres we drop the ``public``
copies here — there is no production data to preserve (it re-harvests).

On SQLite (dev + tests) this is a no-op: there are no schemas, the tables
stay put, and the models' symbolic ``"source"`` schema is translated away
(see ``app/config.py`` / ``migrations/env.py``).

See docs/project-schema-design.md.
"""
from alembic import op


revision = "62af3c38c093"
down_revision = "e2c3d4f5a6b7"
branch_labels = None
depends_on = None

# children first (FKs point up the list)
_AUX_TABLES = (
    "aggregated_records",
    "harvest_errors",
    "harvest_runs",
    "federation_cache",
)


def upgrade():
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        for table in _AUX_TABLES:
            op.execute(f'DROP TABLE IF EXISTS public."{table}" CASCADE')

    # Create the cross-source *_all views so a bare `flask db upgrade`
    # leaves a working app. On SQLite this is the JOIN form over the shared
    # tables; on Postgres it's the empty stub, replaced with the real UNION
    # by `scripts/load_upgrade_projects` after the sources are registered.
    from app.services.sources import rebuild_source_views

    rebuild_source_views(bind, slugs=[])


def downgrade():
    # No structural downgrade: the per-source schemas are rebuilt from the
    # models, not from migration history. Recreating empty public copies
    # here would just shadow them.
    pass
