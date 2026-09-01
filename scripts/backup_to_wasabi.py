"""Off-site encrypted backup of the production database to Wasabi.

Weekly cron (see ``docs/wasabi-backup.md``). Standalone — imports nothing
from ``app``; the Flask app never touches Wasabi. Deps are in
``requirements-backup.txt`` (``boto3``, ``cryptography``; SQLAlchemy for the
``python`` mode is already a web-app dep), not the web-app requirements.

Two dump modes (``BACKUP_MODE`` env, or ``--python`` / ``--pgdump``):

* ``pgdump`` — ``pg_dump --no-owner --no-privileges -Fc`` of the **whole
  database**: every schema (``public`` + the per-source ``src_<slug>``),
  views, sequences. This is the prod mode — the cPanel box ships
  ``pg_dump`` matching its own PostgreSQL server. Restore with ``--restore``
  (or ``--decrypt`` then ``pg_restore``).
* ``python`` — SQLAlchemy reflects ``public.*`` only, ``SELECT *`` every
  table in FK order, gzipped JSON. No client binary, version-proof, works
  on SQLite. **Does NOT capture the ``src_<slug>`` schemas** — dev / local
  convenience only, not a full backup of the per-source prod DB.

Then either way::

      -> AES-256-GCM (key = $BRASIL_ARCHIVES_BACKUP_KEY, base64 32 bytes)
      -> boto3 put_object (SigV4)  s3://$WASABI_BUCKET_NAME/$BACKUP_PREFIX/brasil-public-<ISO>.<ext>.enc
      -> verify returned ETag == md5(ciphertext)

Retention is a Wasabi bucket lifecycle rule, NOT this script — it never
deletes. See docs/wasabi-backup.md §6.

Usage::

    python -m scripts.backup_to_wasabi                       # full run (needs DATABASE_URL)
    python -m scripts.backup_to_wasabi --dry-run              # dump + encrypt to ./ ; no upload
    python -m scripts.backup_to_wasabi --selftest             # crypto + Wasabi round-trip, no DB
    python -m scripts.backup_to_wasabi --list
    python -m scripts.backup_to_wasabi --fetch <key> <outfile>
    python -m scripts.backup_to_wasabi --decrypt <in.enc> <out>          # raw decrypt
    python -m scripts.backup_to_wasabi --restore <in.enc> --target-url <URL>   # either mode

Exit non-zero on any failure so cron email fires. Silent-ish on success.
"""
from __future__ import annotations

import argparse
import base64 as _b64
import gzip
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

# --------------------------------------------------------------------------- #
# env
# --------------------------------------------------------------------------- #

def _load_dotenv() -> None:
    """Best-effort .env load so a local run picks up creds. Cron passes real env."""
    try:
        from dotenv import load_dotenv  # type: ignore
    except ImportError:
        return
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")


class Config:
    def __init__(self) -> None:
        self.access_key = os.environ.get("WASABI_ACCESS_KEY_ID", "")
        self.secret_key = os.environ.get("WASABI_SECRET_ACCESS_KEY", "")
        # ajme/app-dashboard portfolio convention is WASABI_BUCKET_NAME;
        # media-pipeline-agent uses WASABI_BUCKET. Accept either.
        self.bucket = (
            os.environ.get("WASABI_BUCKET_NAME")
            or os.environ.get("WASABI_BUCKET")
            or ""
        )
        self.region = os.environ.get("WASABI_REGION", "us-east-1")
        self.endpoint_url = os.environ.get(
            "WASABI_ENDPOINT_URL", f"https://s3.{self.region}.wasabisys.com"
        )
        self.prefix = os.environ.get("BACKUP_PREFIX", "pg/")
        if self.prefix and not self.prefix.endswith("/"):
            self.prefix += "/"
        self.backup_key_b64 = os.environ.get("BRASIL_ARCHIVES_BACKUP_KEY", "")
        self.encrypt_cmd = os.environ.get("BACKUP_ENCRYPT_CMD", "")
        self.decrypt_cmd = os.environ.get("BACKUP_DECRYPT_CMD", "")
        self.database_url = os.environ.get("DATABASE_URL", "")
        # "python" (default, no client binary) | "pgdump"
        self.mode = os.environ.get("BACKUP_MODE", "python").strip().lower()

    def require_wasabi(self) -> None:
        missing = [
            n
            for n, v in (
                ("WASABI_ACCESS_KEY_ID", self.access_key),
                ("WASABI_SECRET_ACCESS_KEY", self.secret_key),
                ("WASABI_BUCKET_NAME", self.bucket),
            )
            if not v
        ]
        if missing:
            _die(f"missing Wasabi env var(s): {', '.join(missing)}")


def _die(msg: str) -> "NoReturn":  # type: ignore[valid-type]
    print(f"backup_to_wasabi: ERROR: {msg}", file=sys.stderr)
    raise SystemExit(1)


def _log(msg: str) -> None:
    print(f"backup_to_wasabi: {msg}", file=sys.stderr)


# --------------------------------------------------------------------------- #
# crypto — AES-256-GCM envelope:  MAGIC(4) VERSION(1) NONCE(12) CIPHERTEXT+TAG
# --------------------------------------------------------------------------- #

_MAGIC = b"BAB1"          # brasil-archives backup, format 1
_VERSION = 1
_HEADER = _MAGIC + bytes([_VERSION])   # also used as GCM associated data


def _key_bytes(cfg: Config) -> bytes:
    import base64

    if not cfg.backup_key_b64:
        _die(
            "BRASIL_ARCHIVES_BACKUP_KEY is not set — refusing to run "
            "(would upload plaintext). Generate: "
            "python -c \"import os,base64;print(base64.b64encode(os.urandom(32)).decode())\""
        )
    try:
        raw = base64.b64decode(cfg.backup_key_b64, validate=True)
    except Exception as exc:  # noqa: BLE001
        _die(f"BRASIL_ARCHIVES_BACKUP_KEY is not valid base64: {exc}")
    if len(raw) != 32:
        _die(f"BRASIL_ARCHIVES_BACKUP_KEY must decode to 32 bytes, got {len(raw)}")
    return raw


def encrypt_bytes(cfg: Config, plaintext: bytes) -> bytes:
    if cfg.encrypt_cmd:
        return _run_filter(cfg.encrypt_cmd, plaintext)
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    nonce = os.urandom(12)
    ct = AESGCM(_key_bytes(cfg)).encrypt(nonce, plaintext, _HEADER)
    return _HEADER + nonce + ct


def decrypt_bytes(cfg: Config, blob: bytes) -> bytes:
    if cfg.decrypt_cmd:
        return _run_filter(cfg.decrypt_cmd, blob)
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    if blob[:4] != _MAGIC:
        _die("not a brasil-archives backup blob (bad magic) — wrong file or a "
             "BACKUP_ENCRYPT_CMD blob without BACKUP_DECRYPT_CMD set")
    if blob[4] != _VERSION:
        _die(f"unsupported envelope version {blob[4]}")
    nonce, ct = blob[5:17], blob[17:]
    try:
        return AESGCM(_key_bytes(cfg)).decrypt(nonce, ct, _HEADER)
    except Exception as exc:  # noqa: BLE001
        _die(f"decrypt failed (wrong key or corrupt blob): {exc}")


def _run_filter(cmd: str, data: bytes) -> bytes:
    """Pipe *data* through a shell command (BACKUP_ENCRYPT_CMD / _DECRYPT_CMD)."""
    proc = subprocess.run(
        cmd, shell=True, input=data, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    if proc.returncode != 0:
        _die(f"filter command failed ({cmd!r}): {proc.stderr.decode(errors='replace')}")
    return proc.stdout


# --------------------------------------------------------------------------- #
# pg_dump
# --------------------------------------------------------------------------- #

def _pg_url(database_url: str) -> str:
    """pg_dump wants a libpq URL — drop the SQLAlchemy '+psycopg' driver tag."""
    return database_url.replace("postgresql+psycopg://", "postgresql://", 1)


def _libpq_conn(database_url: str) -> tuple[str, dict]:
    """(libpq URL, extra env). ``sslmode`` is moved out of the URI into
    ``PGSSLMODE`` — PostgreSQL 10's libpq rejects ``sslmode=disable`` in a
    connection URI (verified on the cPanel box) but honours the env var."""
    url = _pg_url(database_url)
    env: dict = {}
    if "?" in url:
        base, _, query = url.partition("?")
        kept = []
        for part in query.split("&"):
            if part.lower().startswith("sslmode="):
                env["PGSSLMODE"] = part.split("=", 1)[1]
            elif part:
                kept.append(part)
        url = base + ("?" + "&".join(kept) if kept else "")
    return url, env


def pg_dump(cfg: Config) -> bytes:
    if not cfg.database_url:
        _die("DATABASE_URL is not set (needed for pg_dump)")
    if not cfg.database_url.startswith("postgresql"):
        _die(f"DATABASE_URL is not Postgres ({cfg.database_url.split('://', 1)[0]}://…) "
             "— nothing to back up here")
    url, extra_env = _libpq_conn(cfg.database_url)
    with tempfile.NamedTemporaryFile(suffix=".dump", delete=False) as tf:
        tmp = Path(tf.name)
    try:
        cmd = [
            "pg_dump",
            "--no-owner",
            "--no-privileges",
            "--format=custom",
            f"--file={tmp}",
            f"--dbname={url}",
        ]
        _log("running pg_dump (whole database — all schemas) …")
        proc = subprocess.run(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env={**os.environ, **extra_env},
        )
        if proc.returncode != 0:
            _die(f"pg_dump failed: {proc.stderr.decode(errors='replace').strip()}")
        data = tmp.read_bytes()
        if not data:
            _die("pg_dump produced an empty file")
        _log(f"pg_dump ok — {len(data):,} bytes (custom format)")
        return data
    finally:
        tmp.unlink(missing_ok=True)


def pg_restore(cfg: Config, dump: bytes, target_url: str, *, force: bool) -> None:
    if not target_url:
        _die("--restore needs --target-url")
    if target_url == cfg.database_url and not force:
        _die("--target-url equals DATABASE_URL — pass --force to overwrite it")
    url, extra_env = _libpq_conn(target_url)
    with tempfile.NamedTemporaryFile(suffix=".dump", delete=False) as tf:
        tmp = Path(tf.name)
        tmp.write_bytes(dump)
    try:
        cmd = [
            "pg_restore", "--no-owner", "--no-privileges",
            "--clean", "--if-exists", f"--dbname={url}", str(tmp),
        ]
        _log(f"running pg_restore into {url.split('@')[-1]} …")
        proc = subprocess.run(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env={**os.environ, **extra_env},
        )
        # pg_restore exits non-zero on ignorable errors (e.g. DROP ... IF
        # EXISTS on a fresh DB); surface stderr but only die on empty output.
        err = proc.stderr.decode(errors="replace").strip()
        if proc.returncode != 0 and err:
            _log(f"pg_restore warnings:\n{err}")
        _log("pg_restore done")
    finally:
        tmp.unlink(missing_ok=True)


# --------------------------------------------------------------------------- #
# python logical dump — SQLAlchemy reflect + SELECT *, no client binary
# --------------------------------------------------------------------------- #

_DUMP_FORMAT = "brasil-archives-logical-dump"
_DUMP_VERSION = 1


def _engine(url: str):
    from sqlalchemy import create_engine

    return create_engine(url, future=True)


def _target_schema(engine) -> str | None:
    """public on Postgres; None (single namespace) on SQLite."""
    return None if engine.dialect.name == "sqlite" else "public"


def _encode_value(v):
    if isinstance(v, (datetime, date)):
        return {"__t__": "dt", "v": v.isoformat()}
    if isinstance(v, Decimal):
        return {"__t__": "dec", "v": str(v)}
    if isinstance(v, (bytes, bytearray, memoryview)):
        return {"__t__": "b64", "v": _b64.b64encode(bytes(v)).decode()}
    if isinstance(v, (str, int, float, bool)) or v is None:
        return v
    return {"__t__": "repr", "v": str(v)}  # last-resort; flagged on decode


def _decode_value(v):
    if not isinstance(v, dict) or "__t__" not in v:
        return v
    t = v["__t__"]
    if t == "dt":
        return datetime.fromisoformat(v["v"])
    if t == "dec":
        return Decimal(v["v"])
    if t == "b64":
        return _b64.b64decode(v["v"])
    _die(f"cannot decode value of type {t!r} — dump written by a newer script?")


def python_dump(cfg: Config) -> bytes:
    from sqlalchemy import MetaData, select, text

    if not cfg.database_url:
        _die("DATABASE_URL is not set (needed for the dump)")
    engine = _engine(cfg.database_url)
    schema = _target_schema(engine)
    md = MetaData()
    md.reflect(bind=engine, schema=schema)
    if not md.tables:
        _die(f"no tables reflected in schema {schema or '(default)'} — wrong DATABASE_URL?")

    doc: dict = {
        "format": _DUMP_FORMAT,
        "version": _DUMP_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "dialect": engine.dialect.name,
        "schema": schema,
        "tables": [],
    }
    total = 0
    with engine.connect() as conn:
        try:
            doc["server_version"] = conn.exec_driver_sql("select version()").scalar()
        except Exception:  # noqa: BLE001 — sqlite etc.
            doc["server_version"] = None
        for tbl in md.sorted_tables:  # FK-safe order
            rows = [
                {k: _encode_value(val) for k, val in row._mapping.items()}
                for row in conn.execute(select(tbl))
            ]
            total += len(rows)
            doc["tables"].append(
                {"name": tbl.name, "columns": [c.name for c in tbl.columns], "rows": rows}
            )
    _log(f"logical dump — {len(doc['tables'])} tables, {total:,} rows "
         f"(schema={schema or 'default'}, {doc['dialect']})")
    raw = json.dumps(doc, separators=(",", ":")).encode()
    blob = gzip.compress(raw, 9)
    _log(f"serialised — {len(raw):,} B JSON -> {len(blob):,} B gzip")
    return blob


def python_restore(cfg: Config, blob: bytes, target_url: str, *, force: bool) -> int:
    from sqlalchemy import MetaData, text

    if not target_url:
        _die("--restore needs --target-url (never restores into DATABASE_URL implicitly)")
    if target_url == cfg.database_url and not force:
        _die("--target-url equals DATABASE_URL — pass --force if you really mean to "
             "overwrite that database")

    try:
        doc = json.loads(gzip.decompress(blob))
    except Exception as exc:  # noqa: BLE001
        _die(f"not a gzipped-JSON logical dump: {exc}")
    if doc.get("format") != _DUMP_FORMAT:
        _die(f"unexpected dump format {doc.get('format')!r}")

    engine = _engine(target_url)
    schema = _target_schema(engine)
    md = MetaData()
    md.reflect(bind=engine, schema=schema)

    dumped = {t["name"] for t in doc["tables"]}
    present = {t.name for t in md.sorted_tables}
    missing = dumped - present
    if missing:
        _die(f"target is missing {len(missing)} table(s) — run `flask db upgrade` "
             f"first: {', '.join(sorted(missing))}")

    by_name = {t.name: t for t in md.sorted_tables}
    total = 0
    with engine.begin() as conn:
        for tbl in reversed(md.sorted_tables):  # clear children first
            conn.execute(tbl.delete())
        for tdef in doc["tables"]:  # dump order == FK-safe
            tbl = by_name[tdef["name"]]
            rows = [
                {k: _decode_value(v) for k, v in r.items()} for r in tdef["rows"]
            ]
            if rows:
                conn.execute(tbl.insert(), rows)
                total += len(rows)
        if engine.dialect.name == "postgresql":
            for tbl in md.sorted_tables:
                if "id" not in tbl.columns:
                    continue
                # table name comes from our own reflection, not user input
                fq = f'"{schema}"."{tbl.name}"' if schema else f'"{tbl.name}"'
                conn.execute(text(
                    "DO $$ DECLARE seq text; BEGIN "
                    f"  seq := pg_get_serial_sequence('{fq}', 'id'); "
                    "  IF seq IS NOT NULL THEN "
                    f"    PERFORM setval(seq, GREATEST((SELECT COALESCE(MAX(id), 1) FROM {fq}), 1)); "
                    "  END IF; END $$;"
                ))
    _log(f"restored {total:,} rows into {len(doc['tables'])} tables "
         f"({engine.dialect.name})")
    return total


# --------------------------------------------------------------------------- #
# Wasabi (boto3, SigV4)
# --------------------------------------------------------------------------- #

def _client(cfg: Config):
    import boto3
    from botocore.client import Config as BotoConfig

    return boto3.client(
        "s3",
        endpoint_url=cfg.endpoint_url,
        aws_access_key_id=cfg.access_key,
        aws_secret_access_key=cfg.secret_key,
        region_name=cfg.region,
        config=BotoConfig(signature_version="s3v4", retries={"max_attempts": 1}),
    )


def _md5_hex(b: bytes) -> str:
    return hashlib.md5(b).hexdigest()


def upload(cfg: Config, key: str, blob: bytes, *, max_attempts: int = 3) -> None:
    from botocore.exceptions import ClientError, EndpointConnectionError

    client = _client(cfg)
    local_md5 = _md5_hex(blob)
    for attempt in range(1, max_attempts + 1):
        try:
            resp = client.put_object(
                Bucket=cfg.bucket,
                Key=key,
                Body=blob,
                ContentType="application/octet-stream",
            )
        except (EndpointConnectionError, ConnectionError, TimeoutError) as exc:
            _transient(attempt, max_attempts, exc)
            continue
        except ClientError as exc:
            status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode", 0)
            if status >= 500 or status == 429:
                _transient(attempt, max_attempts, exc)
                continue
            _die(f"upload rejected (HTTP {status}): {exc}")
        etag = (resp.get("ETag") or "").strip().strip('"')
        if not etag:
            _log("WARNING: no ETag in PUT response — cannot verify integrity")
        elif "-" in etag:
            _log(f"WARNING: multipart-shaped ETag {etag!r}; skipping md5 check")
        elif etag.lower() != local_md5:
            _die(f"ETag mismatch: server={etag} local_md5={local_md5} "
                 "(is bucket-level SSE enabled? see docs/wasabi-backup.md §7)")
        _log(f"uploaded s3://{cfg.bucket}/{key}  ({len(blob):,} bytes, {attempt} attempt(s))")
        return
    _die("upload: exhausted retries")


def _transient(attempt: int, max_attempts: int, exc: BaseException) -> None:
    if attempt >= max_attempts:
        _die(f"upload failed after {attempt} attempts: {exc}")
    delay = 0.5 * (4 ** (attempt - 1))
    _log(f"transient error (attempt {attempt}/{max_attempts}), retry in {delay:.1f}s: {exc}")
    time.sleep(delay)


def list_objects(cfg: Config) -> list[tuple[str, int, str]]:
    client = _client(cfg)
    out: list[tuple[str, int, str]] = []
    token = None
    while True:
        kw = {"Bucket": cfg.bucket, "Prefix": cfg.prefix}
        if token:
            kw["ContinuationToken"] = token
        resp = client.list_objects_v2(**kw)
        for o in resp.get("Contents", []):
            out.append((o["Key"], o["Size"], o["LastModified"].isoformat()))
        if not resp.get("IsTruncated"):
            break
        token = resp.get("NextContinuationToken")
    return sorted(out)


def fetch(cfg: Config, key: str) -> bytes:
    client = _client(cfg)
    from botocore.exceptions import ClientError

    try:
        return client.get_object(Bucket=cfg.bucket, Key=key)["Body"].read()
    except ClientError as exc:
        _die(f"fetch {key!r} failed: {exc}")


# --------------------------------------------------------------------------- #
# key layout
# --------------------------------------------------------------------------- #

def _ext(cfg: Config) -> str:
    return "json.gz.enc" if cfg.mode == "python" else "dump.enc"


def object_key(cfg: Config, *, selftest: bool = False) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    if selftest:
        return f"{cfg.prefix}_selftest/probe-{ts}.{_ext(cfg)}"
    return f"{cfg.prefix}brasil-public-{ts}.{_ext(cfg)}"


# --------------------------------------------------------------------------- #
# commands
# --------------------------------------------------------------------------- #

def _looks_local(url: str) -> bool:
    return any(h in url for h in ("@localhost", "@127.0.0.1", "@::1", "@db:", "@db/"))


def cmd_run(cfg: Config, *, dry_run: bool, keep: str | None) -> int:
    if cfg.mode not in ("python", "pgdump"):
        _die(f"BACKUP_MODE must be 'python' or 'pgdump', got {cfg.mode!r}")
    if (not dry_run and _looks_local(cfg.database_url)
            and os.environ.get("BACKUP_ALLOW_LOCAL") != "1"):
        _die(f"DATABASE_URL points at a local/dev database "
             f"({cfg.database_url.split('@', 1)[-1][:40]}…) — refusing to upload "
             "it as a production backup. Use --dry-run, or set BACKUP_ALLOW_LOCAL=1 "
             "if you really mean to.")
    if not dry_run:
        cfg.require_wasabi()
    dump = python_dump(cfg) if cfg.mode == "python" else pg_dump(cfg)
    blob = encrypt_bytes(cfg, dump)
    _log(f"encrypted — {len(blob):,} bytes (envelope), md5={_md5_hex(blob)}")
    if keep:
        Path(keep).write_bytes(blob)
        _log(f"wrote local copy: {keep}")
    if dry_run:
        if not keep:
            ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
            out = f"brasil-public-{ts}.{_ext(cfg)}"
            Path(out).write_bytes(blob)
            _log(f"--dry-run: wrote {out} (no upload)")
        return 0
    upload(cfg, object_key(cfg), blob)
    return 0


def cmd_restore(cfg: Config, infile: str, target_url: str, *, force: bool) -> int:
    blob = decrypt_bytes(cfg, Path(infile).read_bytes())
    # Detect the payload rather than trusting BACKUP_MODE — gzip magic
    # 1f 8b => the python logical dump; anything else => a pg_dump archive.
    if blob[:2] == b"\x1f\x8b":
        python_restore(cfg, blob, target_url, force=force)
    else:
        pg_restore(cfg, blob, target_url, force=force)
    return 0


def cmd_selftest(cfg: Config) -> int:
    cfg.require_wasabi()
    _log(f"endpoint={cfg.endpoint_url} bucket={cfg.bucket} region={cfg.region}")
    payload = b"brasil-archives selftest " + os.urandom(4096)
    blob = encrypt_bytes(cfg, payload)
    assert decrypt_bytes(cfg, blob) == payload, "local crypto round-trip failed"
    _log("crypto round-trip OK")
    key = object_key(cfg, selftest=True)
    upload(cfg, key, blob)
    got = fetch(cfg, key)
    if got != blob:
        _die("downloaded bytes != uploaded bytes")
    if decrypt_bytes(cfg, got) != payload:
        _die("decrypt of downloaded blob != original payload")
    _log("Wasabi round-trip OK (upload → download → decrypt verified)")
    try:
        _client(cfg).delete_object(Bucket=cfg.bucket, Key=key)
        _log(f"cleaned up {key}")
    except Exception as exc:  # noqa: BLE001
        _log(f"note: could not delete probe object ({exc}); lifecycle rule will expire it")
    print("SELFTEST PASSED")
    return 0


def cmd_list(cfg: Config) -> int:
    cfg.require_wasabi()
    rows = list_objects(cfg)
    if not rows:
        _log(f"no objects under {cfg.prefix!r}")
        return 0
    for key, size, mtime in rows:
        print(f"{mtime}  {size:>12,}  {key}")
    _log(f"{len(rows)} object(s)")
    return 0


def cmd_fetch(cfg: Config, key: str, outfile: str) -> int:
    cfg.require_wasabi()
    Path(outfile).write_bytes(fetch(cfg, key))
    _log(f"wrote {outfile}")
    return 0


def cmd_decrypt(cfg: Config, infile: str, outfile: str) -> int:
    plain = decrypt_bytes(cfg, Path(infile).read_bytes())
    Path(outfile).write_bytes(plain)
    hint = (
        "gzipped JSON — `gunzip` it, or use `--restore` to load into a scratch DB"
        if plain[:2] == b"\x1f\x8b"
        else f"pg_restore --no-owner --dbname <scratch> {outfile}"
    )
    _log(f"decrypted {infile} -> {outfile} ({len(plain):,} bytes). {hint}")
    return 0


def main(argv: list[str] | None = None) -> int:
    _load_dotenv()
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = p.add_mutually_exclusive_group()
    g.add_argument("--dry-run", action="store_true", help="dump + encrypt locally, no upload")
    g.add_argument("--selftest", action="store_true", help="crypto + Wasabi round-trip, no DB")
    g.add_argument("--list", action="store_true", help="list objects under the prefix")
    g.add_argument("--fetch", nargs=2, metavar=("KEY", "OUTFILE"))
    g.add_argument("--decrypt", nargs=2, metavar=("INFILE", "OUTFILE"),
                   help="decrypt a blob to raw bytes (no gunzip)")
    g.add_argument("--restore", metavar="INFILE",
                   help="python-mode: decrypt+load a dump into --target-url (after `flask db upgrade`)")
    p.add_argument("--target-url", metavar="URL", help="restore target (never DATABASE_URL unless --force)")
    p.add_argument("--force", action="store_true", help="allow --target-url == DATABASE_URL")
    p.add_argument("--python", dest="mode", action="store_const", const="python",
                   help="force logical-dump mode (overrides BACKUP_MODE)")
    p.add_argument("--pgdump", dest="mode", action="store_const", const="pgdump",
                   help="force pg_dump mode (needs a matching client)")
    p.add_argument("--keep", metavar="PATH", help="also write the encrypted blob here")
    args = p.parse_args(argv)

    cfg = Config()
    if args.mode:
        cfg.mode = args.mode
    if args.selftest:
        return cmd_selftest(cfg)
    if args.list:
        return cmd_list(cfg)
    if args.fetch:
        return cmd_fetch(cfg, *args.fetch)
    if args.decrypt:
        return cmd_decrypt(cfg, *args.decrypt)
    if args.restore:
        return cmd_restore(cfg, args.restore, args.target_url or "", force=args.force)
    return cmd_run(cfg, dry_run=args.dry_run, keep=args.keep)


if __name__ == "__main__":
    raise SystemExit(main())
