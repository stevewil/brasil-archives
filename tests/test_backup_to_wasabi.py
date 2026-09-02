"""Tests for scripts/backup_to_wasabi.py.

Standalone — no app, no network. boto3 is stubbed. See docs/wasabi-backup.md §12.
"""
from __future__ import annotations

import base64

import pytest

from scripts import backup_to_wasabi as b


KEY_B64 = base64.b64encode(b"\x11" * 32).decode()


@pytest.fixture
def cfg(monkeypatch):
    for k in ("BACKUP_ENCRYPT_CMD", "BACKUP_DECRYPT_CMD"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("BRASIL_ARCHIVES_BACKUP_KEY", KEY_B64)
    monkeypatch.setenv("WASABI_ACCESS_KEY_ID", "AK")
    monkeypatch.setenv("WASABI_SECRET_ACCESS_KEY", "SK")
    monkeypatch.setenv("WASABI_BUCKET_NAME", "brasil-archives")
    monkeypatch.setenv("WASABI_REGION", "us-west-1")
    monkeypatch.delenv("WASABI_ENDPOINT_URL", raising=False)
    return b.Config()


# --------------------------------------------------------------------------- #
# crypto
# --------------------------------------------------------------------------- #

def test_encrypt_decrypt_round_trip(cfg):
    pt = b"PGDMP\x00\x01 fake custom dump " * 500
    blob = b.encrypt_bytes(cfg, pt)
    assert blob[:5] == b._MAGIC + bytes([b._VERSION])  # header present
    assert blob[:4] == b"BAB1"
    assert b.decrypt_bytes(cfg, blob) == pt


def test_flipped_byte_fails_auth_tag(cfg):
    blob = bytearray(b.encrypt_bytes(cfg, b"hello world" * 10))
    blob[-1] ^= 0x01
    with pytest.raises(SystemExit):
        b.decrypt_bytes(cfg, bytes(blob))


def test_wrong_key_rejected(cfg, monkeypatch):
    blob = b.encrypt_bytes(cfg, b"secret")
    monkeypatch.setenv("BRASIL_ARCHIVES_BACKUP_KEY", base64.b64encode(b"\x22" * 32).decode())
    with pytest.raises(SystemExit):
        b.decrypt_bytes(b.Config(), blob)


def test_bad_magic_rejected(cfg):
    with pytest.raises(SystemExit):
        b.decrypt_bytes(cfg, b"NOTABLOB" + b"\x00" * 40)


def test_missing_key_refuses_before_dump(monkeypatch):
    monkeypatch.delenv("BRASIL_ARCHIVES_BACKUP_KEY", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql://x/y")
    with pytest.raises(SystemExit):
        b.encrypt_bytes(b.Config(), b"data")


def test_encrypt_cmd_override(cfg, monkeypatch):
    # a trivial reversible "filter": prepend a marker
    monkeypatch.setenv("BACKUP_ENCRYPT_CMD", "python -c \"import sys;sys.stdout.buffer.write(b'X'+sys.stdin.buffer.read())\"")
    monkeypatch.setenv("BACKUP_DECRYPT_CMD", "python -c \"import sys;sys.stdout.buffer.write(sys.stdin.buffer.read()[1:])\"")
    c = b.Config()
    blob = b.encrypt_bytes(c, b"payload")
    assert blob == b"Xpayload"
    assert b.decrypt_bytes(c, blob) == b"payload"


# --------------------------------------------------------------------------- #
# key layout
# --------------------------------------------------------------------------- #

def test_object_key_iso_sortable(cfg):
    cfg.mode = "pgdump"
    k = b.object_key(cfg)
    assert k.startswith("pg/brasil-public-")
    assert k.endswith(".dump.enc")
    ts = k[len("pg/brasil-public-"):-len(".dump.enc")]
    from datetime import datetime
    datetime.strptime(ts, "%Y-%m-%dT%H-%M-%SZ")  # parses => sortable


def test_selftest_key_segregated(cfg):
    assert b.object_key(cfg, selftest=True).startswith("pg/_selftest/")


# --------------------------------------------------------------------------- #
# pg_dump url handling
# --------------------------------------------------------------------------- #

def test_pg_url_strips_driver_tag():
    assert b._pg_url("postgresql+psycopg://u:p@h:5432/db?sslmode=require") == \
        "postgresql://u:p@h:5432/db?sslmode=require"
    assert b._pg_url("postgresql://u@h/db") == "postgresql://u@h/db"


def test_libpq_conn_moves_sslmode_to_env():
    url, env = b._libpq_conn(
        "postgresql+psycopg://u:p@localhost:5432/db?sslmode=disable"
    )
    assert url == "postgresql://u:p@localhost:5432/db"
    assert env == {"PGSSLMODE": "disable"}
    # other params kept, no query -> untouched
    url, env = b._libpq_conn("postgresql://u@h/db?connect_timeout=5&sslmode=require")
    assert url == "postgresql://u@h/db?connect_timeout=5"
    assert env == {"PGSSLMODE": "require"}
    url, env = b._libpq_conn("postgresql://u@h/db")
    assert url == "postgresql://u@h/db" and env == {}


def test_pg_dump_requires_postgres(cfg, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///instance/x.db")
    with pytest.raises(SystemExit):
        b.pg_dump(b.Config())


def test_dev_target_guard(monkeypatch):
    monkeypatch.delenv("BRASIL_ARCHIVES_CONFIG", raising=False)
    # tunnel port -> always flagged, even if config=production
    monkeypatch.setenv("BRASIL_ARCHIVES_CONFIG", "production")
    assert b._dev_target_reason("postgresql://u:pw@localhost:5433/prod")
    # Docker default creds / db names
    assert b._dev_target_reason("postgresql://postgres:postgres@localhost:5432/x")
    assert b._dev_target_reason("postgresql://u:pw@localhost:5432/app_test")
    # prod: localhost + config=production -> allowed
    assert b._dev_target_reason(
        "postgresql+psycopg://svc:pw@localhost:5432/fromuagq_brasil-archives?sslmode=disable"
    ) is None
    # localhost without config=production -> flagged
    monkeypatch.delenv("BRASIL_ARCHIVES_CONFIG", raising=False)
    assert b._dev_target_reason("postgresql://svc:pw@localhost:5432/fromuagq_brasil-archives")
    # a real remote host -> never flagged
    assert b._dev_target_reason("postgresql://u:pw@db.example.com:5432/prod") is None


def test_cmd_run_refuses_dev_target(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://postgres:postgres@localhost:5432/app")
    monkeypatch.delenv("BACKUP_ALLOW_LOCAL", raising=False)
    monkeypatch.delenv("BRASIL_ARCHIVES_CONFIG", raising=False)
    with pytest.raises(SystemExit):
        b.cmd_run(b.Config(), dry_run=False, keep=None)


# --------------------------------------------------------------------------- #
# upload — boto3 stubbed
# --------------------------------------------------------------------------- #

class _FakeClientError(Exception):
    def __init__(self, status):
        super().__init__(f"HTTP {status}")
        self.response = {"ResponseMetadata": {"HTTPStatusCode": status}}


@pytest.fixture
def stub_boto(monkeypatch):
    import hashlib

    calls = {"put": 0}
    behaviour = {"raise_n": 0, "exc": None, "etag": None}

    class FakeClient:
        def put_object(self, Bucket, Key, Body, ContentType):
            calls["put"] += 1
            if calls["put"] <= behaviour["raise_n"]:
                raise behaviour["exc"]
            etag = behaviour["etag"] or hashlib.md5(Body).hexdigest()
            return {"ETag": f'"{etag}"'}

    monkeypatch.setattr(b, "_client", lambda cfg: FakeClient())
    # make the botocore exception classes importable inside upload()
    import botocore.exceptions as be
    monkeypatch.setattr(be, "ClientError", _FakeClientError, raising=False)
    monkeypatch.setattr(b, "_transient", _fast_transient(b), raising=True)
    return calls, behaviour


def _fast_transient(mod):
    orig = mod._transient

    def _t(attempt, max_attempts, exc):
        if attempt >= max_attempts:
            orig(attempt, max_attempts, exc)  # still raises SystemExit
        # else: no sleep
    return _t


def test_upload_ok_first_try(cfg, stub_boto):
    calls, _ = stub_boto
    b.upload(cfg, "pg/k.enc", b"ciphertext-bytes")
    assert calls["put"] == 1


def test_upload_retries_then_succeeds(cfg, stub_boto):
    calls, behaviour = stub_boto
    behaviour["raise_n"] = 2
    behaviour["exc"] = _FakeClientError(500)
    b.upload(cfg, "pg/k.enc", b"data", max_attempts=3)
    assert calls["put"] == 3


def test_upload_4xx_fails_fast(cfg, stub_boto):
    calls, behaviour = stub_boto
    behaviour["raise_n"] = 1
    behaviour["exc"] = _FakeClientError(403)
    with pytest.raises(SystemExit):
        b.upload(cfg, "pg/k.enc", b"data")
    assert calls["put"] == 1


def test_upload_etag_mismatch_raises(cfg, stub_boto):
    _, behaviour = stub_boto
    behaviour["etag"] = "deadbeef" * 4
    with pytest.raises(SystemExit):
        b.upload(cfg, "pg/k.enc", b"data")


# --------------------------------------------------------------------------- #
# python logical dump / restore
# --------------------------------------------------------------------------- #

from datetime import datetime, timezone
from decimal import Decimal


@pytest.mark.parametrize("val", [
    None, "", "text", 0, 42, -1, 3.5, True, False,
    datetime(2026, 8, 31, 12, 34, 56, tzinfo=timezone.utc),
    Decimal("12.34"),
    b"\x00\x01\xfe\xff",
])
def test_value_codec_round_trip(val):
    assert b._decode_value(b._encode_value(val)) == val


def _sample_db(path):
    """A 2-table DB with a parent/child FK, mixed types — no app import."""
    from sqlalchemy import (Column, DateTime, ForeignKey, Integer, MetaData,
                            String, Table, create_engine, insert)

    eng = create_engine(f"sqlite:///{path}", future=True)
    md = MetaData()
    parent = Table("parent", md,
                   Column("id", Integer, primary_key=True),
                   Column("name", String, nullable=False))
    child = Table("child", md,
                  Column("id", Integer, primary_key=True),
                  Column("parent_id", Integer, ForeignKey("parent.id"), nullable=False),
                  Column("seen_at", DateTime))
    md.create_all(eng)
    with eng.begin() as c:
        c.execute(insert(parent), [{"id": 1, "name": "açaí"}, {"id": 2, "name": "x"}])
        c.execute(insert(child), [
            {"id": 1, "parent_id": 2, "seen_at": datetime(2026, 1, 2, 3, 4, 5)},
            {"id": 2, "parent_id": 1, "seen_at": None},
        ])
    return eng


def test_python_dump_and_restore_round_trip(cfg, tmp_path, monkeypatch):
    import gzip
    import json
    from sqlalchemy import MetaData, create_engine, select

    src = tmp_path / "src.db"
    dst = tmp_path / "dst.db"
    _sample_db(str(src))
    _sample_db(str(dst))  # same schema; restore wipes + reloads

    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{src}")
    cfg.mode = "python"
    cfg.database_url = f"sqlite:///{src}"

    blob = b.python_dump(cfg)
    doc = json.loads(gzip.decompress(blob))
    assert doc["format"] == b._DUMP_FORMAT
    assert [t["name"] for t in doc["tables"]] == ["parent", "child"]  # FK order

    enc = b.encrypt_bytes(cfg, blob)
    n = b.python_restore(cfg, b.decrypt_bytes(cfg, enc), f"sqlite:///{dst}", force=False)
    assert n == 4

    eng = create_engine(f"sqlite:///{dst}", future=True)
    md = MetaData(); md.reflect(bind=eng)
    with eng.connect() as c:
        assert c.execute(select(md.tables["parent"])).all() == [(1, "açaí"), (2, "x")]
        rows = c.execute(select(md.tables["child"])).all()
    assert rows[0] == (1, 2, datetime(2026, 1, 2, 3, 4, 5))
    assert rows[1] == (2, 1, None)


def test_restore_refuses_missing_tables(cfg, tmp_path):
    import gzip, json
    src = tmp_path / "s.db"
    _sample_db(str(src))
    cfg.mode = "python"
    cfg.database_url = f"sqlite:///{src}"
    blob = b.python_dump(cfg)
    empty = tmp_path / "empty.db"
    empty.write_bytes(b"")
    with pytest.raises(SystemExit):
        b.python_restore(cfg, blob, f"sqlite:///{empty}", force=False)


def test_restore_refuses_database_url_without_force(cfg, tmp_path):
    src = tmp_path / "s.db"
    _sample_db(str(src))
    cfg.mode = "python"
    cfg.database_url = f"sqlite:///{src}"
    blob = b.python_dump(cfg)
    with pytest.raises(SystemExit):
        b.python_restore(cfg, blob, cfg.database_url, force=False)


def test_ext_and_key_track_mode(cfg):
    cfg.mode = "python"
    assert b.object_key(cfg).endswith(".json.gz.enc")
    cfg.mode = "pgdump"
    assert b.object_key(cfg).endswith(".dump.enc")
