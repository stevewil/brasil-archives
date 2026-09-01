"""Per-source schema machinery — docs/partner-schema-design.md.

Pure-function checks run on any backend. The integration checks that
stamp real ``src_<slug>`` schemas only run against Postgres
(``TEST_DATABASE_URL``), on a raw engine without the suite's fixed
``src_test`` translate map.
"""
from __future__ import annotations

import os

import pytest
from sqlalchemy import create_engine, text

from app.services import sources


# --------------------------------------------------------------------------- #
# pure functions

def test_source_schema_naming():
    assert sources.source_schema("mipibu") == "src_mipibu"
    assert sources.source_schema("povos-indigenas-rn") == "src_povos_indigenas_rn"


@pytest.mark.parametrize("bad", ["", "Mipibu", "a b", "x;drop", "-x", "x-", "x--y"])
def test_source_schema_rejects_unsafe_slugs(bad):
    with pytest.raises(ValueError):
        sources.source_schema(bad)


# --------------------------------------------------------------------------- #
# Postgres integration

_PG_URL = os.environ.get("TEST_DATABASE_URL", "")
pg_only = pytest.mark.skipif(
    not _PG_URL.startswith("postgresql"),
    reason="per-source schema stamping is Postgres-only",
)


@pytest.fixture
def raw_pg():
    """A standalone engine on the test DB with NO fixed translate map, so
    ensure_source_schema / the UNION views behave as in production. Builds
    just a minimal ``public.upgrade_projects`` for the cross-schema FK —
    no ORM, no app context, no shared session to deadlock against."""
    eng = create_engine(_PG_URL, future=True)
    with eng.begin() as c:
        c.execute(text(
            "CREATE TABLE IF NOT EXISTS public.upgrade_projects "
            "(id serial PRIMARY KEY, slug text UNIQUE)"
        ))
        c.execute(text(
            "INSERT INTO public.upgrade_projects (slug) VALUES ('alpha'), "
            "('beta-two') ON CONFLICT DO NOTHING"
        ))
    yield eng
    with eng.begin() as c:
        for s in ("src_alpha", "src_beta_two", "src_gamma"):
            c.execute(text(f'DROP SCHEMA IF EXISTS "{s}" CASCADE'))
        for v in ("aggregated_records_all", "harvest_runs_all", "harvest_errors_all"):
            c.execute(text(f'DROP VIEW IF EXISTS public."{v}" CASCADE'))
        c.execute(text("DROP TABLE IF EXISTS public.upgrade_projects CASCADE"))
    eng.dispose()


@pg_only
def test_ensure_source_schema_is_idempotent_and_makes_four_tables(raw_pg):
    sources.ensure_source_schema(raw_pg, "alpha")
    sources.ensure_source_schema(raw_pg, "alpha")  # again — no error
    with raw_pg.connect() as c:
        tables = set(c.execute(text(
            "select table_name from information_schema.tables "
            "where table_schema = 'src_alpha'"
        )).scalars())
    assert tables == {
        "aggregated_records", "harvest_runs", "harvest_errors", "federation_cache"
    }


@pg_only
def test_rebuild_views_unions_registered_sources(raw_pg):
    sources.ensure_source_schema(raw_pg, "alpha")
    sources.ensure_source_schema(raw_pg, "beta-two")
    sources.rebuild_source_views(raw_pg, ["alpha", "beta-two"])
    with raw_pg.connect() as c:
        defn = c.execute(text(
            "select view_definition from information_schema.views "
            "where table_schema='public' and table_name='aggregated_records_all'"
        )).scalar()
    assert "src_alpha" in defn and "src_beta_two" in defn
    # and it actually selects
    with raw_pg.connect() as c:
        assert c.execute(text("select count(*) from public.aggregated_records_all")).scalar() == 0


@pg_only
def test_drop_source_schema_removes_it(raw_pg):
    sources.ensure_source_schema(raw_pg, "gamma")
    sources.drop_source_schema(raw_pg, "gamma")
    with raw_pg.connect() as c:
        exists = c.execute(text(
            "select 1 from information_schema.schemata where schema_name='src_gamma'"
        )).scalar()
    assert exists is None
