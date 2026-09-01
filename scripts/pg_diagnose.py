"""Diagnose a Postgres cutover that 500s on every page while /healthz is green.

``/healthz`` only reads ``db.engine.dialect.name`` -- that is derived from the
URL string and needs **no connection**, so a green /healthz proves nothing
about reachability. This script walks the connection from the outside in and
stops being polite about where it breaks.

Run on the target box, venv active, in the app dir::

    python -m scripts.pg_diagnose

It loads ``.env`` itself. Read-only: one ``SELECT count(*)`` at most.
"""
from __future__ import annotations

import os
import re
import socket
import sys
import traceback
from urllib.parse import urlsplit


def _mask(url: str) -> str:
    return re.sub(r"(:)([^:@/]{3})[^:@/]*(@)", r"\1\2***\3", url)


def main() -> int:
    try:
        from dotenv import load_dotenv

        load_dotenv()
        print("[env] .env loaded")
    except ImportError:
        print("[env] python-dotenv not installed -- relying on real env")

    url = os.environ.get("DATABASE_URL", "")
    if not url:
        print("[env] DATABASE_URL is UNSET -- app would fall back to SQLite. Stop.")
        return 2
    print(f"[env] DATABASE_URL = {_mask(url)}")
    print(f"[env] BRASIL_ARCHIVES_CONFIG = {os.environ.get('BRASIL_ARCHIVES_CONFIG')!r}")

    # --- versions ---------------------------------------------------------
    try:
        import psycopg

        print(f"[ver] psycopg {psycopg.__version__}")
    except Exception as e:  # noqa: BLE001
        print(f"[ver] psycopg import FAILED: {e!r}")
    try:
        import sqlalchemy

        print(f"[ver] SQLAlchemy {sqlalchemy.__version__}")
    except Exception as e:  # noqa: BLE001
        print(f"[ver] SQLAlchemy import FAILED: {e!r}")

    # --- 1. raw TCP reachability ----------------------------------------
    # strip the +driver and any query for urlsplit
    bare = re.sub(r"^postgresql\+\w+", "postgresql", url).split("?", 1)[0]
    parts = urlsplit(bare)
    host, port = parts.hostname, parts.port or 5432
    print(f"\n[1] TCP connect to {host}:{port} (5s timeout) ...")
    try:
        with socket.create_connection((host, port), timeout=5):
            print("[1] OK -- socket opened. Outbound port is not firewalled.")
    except Exception as e:  # noqa: BLE001
        print(f"[1] FAILED: {type(e).__name__}: {e}")
        print("[1] => the shared host is almost certainly blocking outbound "
              f"port {port}. Ask support to allow it, or move to a permitted "
              "port. Nothing below will work until this does.")
        return 1

    # --- 2. bare psycopg connect, with / without the options packet -----
    dsn = bare.replace("postgresql://", "")  # psycopg wants a URL or kv; build kv
    m = re.match(r"([^:]+):([^@]+)@([^:/]+):?(\d+)?/(.+)", dsn)
    user, pw, h, p, dbname = m.group(1), m.group(2), m.group(3), m.group(4) or "5432", m.group(5)
    import psycopg

    for label, opts in [
        ("plain", {}),
        ("options=-c search_path", {"options": "-c search_path=public -c statement_timeout=15000"}),
    ]:
        print(f"\n[2:{label}] psycopg.connect ...")
        try:
            kw = dict(host=h, port=int(p), user=user, password=pw, dbname=dbname,
                      sslmode="require", connect_timeout=10, **opts)
            with psycopg.connect(**kw) as c:
                cur = c.execute("select count(*) from archives")
                print(f"[2:{label}] OK -- archives = {cur.fetchone()[0]}")
        except Exception as e:  # noqa: BLE001
            print(f"[2:{label}] FAILED: {type(e).__name__}: {repr(e)[:400]}")

    # --- 3. SQLAlchemy engine exactly as the app builds it --------------
    print("\n[3] via app config _engine_options + create_engine ...")
    try:
        from sqlalchemy import create_engine, text

        from app.config import _engine_options

        eo = _engine_options(url)
        print(f"[3] engine_options = {eo}")
        eng = create_engine(url, **eo)
        with eng.connect() as c:
            n = c.execute(text("select count(*) from archives")).scalar()
            sp = c.execute(text("show search_path")).scalar()
            st = c.execute(text("show statement_timeout")).scalar()
        print(f"[3] OK -- archives={n} search_path={sp!r} statement_timeout={st!r}")
        eng.dispose()
    except Exception as e:  # noqa: BLE001
        print(f"[3] FAILED: {type(e).__name__}: {repr(e)[:600]}")
        traceback.print_exc()

    # --- 4. the real app, a real query --------------------------------
    print("\n[4] create_app() + a real ORM query ...")
    try:
        from sqlalchemy import text

        from app import create_app
        from app.extensions import db

        app = create_app()
        with app.app_context():
            n = db.session.execute(text("select count(*) from public.archives")).scalar()
            print(f"[4] OK -- public.archives = {n}")
            v = db.session.execute(
                text("select count(*) from aggregated_records_all")
            ).scalar()
            print(f"[4] OK -- aggregated_records_all = {v}")
    except Exception as e:  # noqa: BLE001
        print(f"[4] FAILED: {type(e).__name__}: {repr(e)[:600]}")
        traceback.print_exc()

    print("\n[done] Report the first FAILED block above.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
