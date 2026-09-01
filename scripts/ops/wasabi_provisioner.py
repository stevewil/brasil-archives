#!/usr/bin/env python3
"""Wasabi IAM provisioning — scoped group / policy / service-user / key.

Implements the structure in ``docs/wasabi-iam-plan.md``: one group per
``(project x role)`` carrying a scoped inline policy, one programmatic
service user per workload joined to that group.

Admin credentials (a Wasabi *root* or IAM-admin key pair) are read from,
in order: ``WASABI_ADMIN_ACCESS_KEY`` / ``WASABI_ADMIN_SECRET_KEY``, else
``WASABI_ACCESS_KEY_ID`` / ``WASABI_SECRET_ACCESS_KEY`` (what a portfolio
``.env`` already holds). ``.env`` at the repo root is auto-loaded.

    python scripts/ops/wasabi_provisioner.py provision \\
        --group grp-brasil-archives-backup \\
        --user  srv-brasil-archives-backup \\
        --buckets brasil-archives --prefix pg --no-delete

    python scripts/ops/wasabi_provisioner.py rotate --user srv-brasil-archives-backup
    python scripts/ops/wasabi_provisioner.py whoami
    python scripts/ops/wasabi_provisioner.py list-regions

Emitted secret keys are shown once. Pipe --output-json into your secrets
manager; never commit them.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)
except ImportError:
    pass

import boto3
from botocore.exceptions import ClientError

WASABI_IAM_ENDPOINT = "https://iam.wasabisys.com"

WASABI_REGIONS = {
    "us-east-1": "https://s3.wasabisys.com",
    "us-east-2": "https://s3.us-east-2.wasabisys.com",
    "us-central-1": "https://s3.us-central-1.wasabisys.com",
    "us-west-1": "https://s3.us-west-1.wasabisys.com",
    "eu-central-1": "https://s3.eu-central-1.wasabisys.com",
    "eu-central-2": "https://s3.eu-central-2.wasabisys.com",
    "eu-west-1": "https://s3.eu-west-1.wasabisys.com",
    "eu-west-2": "https://s3.eu-west-2.wasabisys.com",
    "ap-northeast-1": "https://s3.ap-northeast-1.wasabisys.com",
    "ap-northeast-2": "https://s3.ap-northeast-2.wasabisys.com",
    "ap-southeast-1": "https://s3.ap-southeast-1.wasabisys.com",
    "ap-southeast-2": "https://s3.ap-southeast-2.wasabisys.com",
}


def _log(msg: str) -> None:
    print(f"[wasabi-provisioner] {msg}", file=sys.stderr)


def _admin_client():
    ak = os.environ.get("WASABI_ADMIN_ACCESS_KEY") or os.environ.get("WASABI_ACCESS_KEY_ID")
    sk = os.environ.get("WASABI_ADMIN_SECRET_KEY") or os.environ.get("WASABI_SECRET_ACCESS_KEY")
    if not ak or not sk:
        _log("no admin credentials — set WASABI_ADMIN_ACCESS_KEY/_SECRET_KEY "
             "(or WASABI_ACCESS_KEY_ID/_SECRET_ACCESS_KEY) in the environment / .env")
        sys.exit(2)
    return boto3.client(
        "iam", aws_access_key_id=ak, aws_secret_access_key=sk,
        endpoint_url=WASABI_IAM_ENDPOINT, region_name="us-east-1",
    )


# --------------------------------------------------------------------------- #
# policy
# --------------------------------------------------------------------------- #

def build_policy(bucket_arns: list[str], *, prefix: str | None,
                 read_only: bool, no_delete: bool) -> dict:
    if read_only:
        obj_actions = ["s3:GetObject"]
    elif no_delete:
        obj_actions = ["s3:GetObject", "s3:PutObject"]
    else:
        obj_actions = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]

    list_stmt: dict = {
        "Sid": "ListAndLocate", "Effect": "Allow",
        "Action": ["s3:ListBucket", "s3:GetBucketLocation"],
        "Resource": bucket_arns,
    }
    if prefix:
        p = prefix.strip("/")
        list_stmt["Condition"] = {"StringLike": {"s3:prefix": [f"{p}/*", f"{p}/", p]}}
        obj_resource = [f"{arn}/{p}/*" for arn in bucket_arns]
    else:
        obj_resource = [f"{arn}/*" for arn in bucket_arns]

    return {
        "Version": "2012-10-17",
        "Statement": [
            list_stmt,
            {"Sid": "ObjectOps", "Effect": "Allow",
             "Action": obj_actions, "Resource": obj_resource},
        ],
    }


# --------------------------------------------------------------------------- #
# idempotent IAM ops
# --------------------------------------------------------------------------- #

def _exists(fn, **kw) -> bool:
    try:
        fn(**kw)
        return True
    except ClientError as e:
        if e.response["Error"]["Code"] in ("NoSuchEntity", "NoSuchEntityException"):
            return False
        raise


def ensure_group(iam, name: str) -> None:
    if _exists(iam.get_group, GroupName=name):
        _log(f"group {name}: exists")
    else:
        iam.create_group(GroupName=name)
        _log(f"group {name}: created")


def put_group_policy(iam, group: str, policy_name: str, doc: dict) -> None:
    iam.put_group_policy(GroupName=group, PolicyName=policy_name,
                         PolicyDocument=json.dumps(doc))
    _log(f"policy {policy_name}: attached to {group}")


def ensure_user(iam, name: str) -> None:
    if _exists(iam.get_user, UserName=name):
        _log(f"user {name}: exists")
    else:
        iam.create_user(UserName=name)
        _log(f"user {name}: created")


def ensure_membership(iam, user: str, group: str) -> None:
    members = {u["UserName"] for u in
              iam.get_group(GroupName=group).get("Users", [])}
    if user in members:
        _log(f"membership {user} in {group}: exists")
    else:
        iam.add_user_to_group(GroupName=group, UserName=user)
        _log(f"membership {user} in {group}: added")


def create_key(iam, user: str) -> dict:
    k = iam.create_access_key(UserName=user)["AccessKey"]
    _log(f"access key for {user}: created ({k['AccessKeyId'][:3]}…)")
    return {"UserName": user, "AccessKeyId": k["AccessKeyId"],
            "SecretAccessKey": k["SecretAccessKey"], "Status": k["Status"]}


def list_keys(iam, user: str) -> list[dict]:
    return iam.list_access_keys(UserName=user).get("AccessKeyMetadata", [])


# --------------------------------------------------------------------------- #
# commands
# --------------------------------------------------------------------------- #

def cmd_provision(args) -> int:
    iam = _admin_client()
    bad_regions = [r for r in (args.regions or []) if r not in WASABI_REGIONS]
    if bad_regions:
        _log(f"unknown region(s): {', '.join(bad_regions)}  (see list-regions)")
        return 2
    bucket_arns = [f"arn:aws:s3:::{b.strip()}" for b in args.buckets]
    policy = build_policy(bucket_arns, prefix=args.prefix,
                          read_only=args.read_only, no_delete=args.no_delete)

    ensure_group(iam, args.group)
    put_group_policy(iam, args.group, f"{args.group}-policy", policy)
    ensure_user(iam, args.user)
    ensure_membership(iam, args.user, args.group)

    existing = list_keys(iam, args.user)
    if existing and not args.new_key:
        _log(f"user {args.user} already has {len(existing)} key(s); pass "
             f"--new-key to mint another (max 2), or `rotate` to cycle them")
        creds = None
    else:
        creds = create_key(iam, args.user)

    mode = ("read-only" if args.read_only
            else "no-delete" if args.no_delete else "read-write")
    summary = {
        "group": args.group, "user": args.user,
        "buckets": args.buckets, "prefix": args.prefix, "mode": mode,
        "credentials": creds,
    }
    if args.output_json:
        print(json.dumps(summary, indent=2))
    else:
        print("\n" + "=" * 58)
        print("  WASABI SERVICE USER")
        print("=" * 58)
        print(f"  group   : {args.group}")
        print(f"  user    : {args.user}")
        print(f"  buckets : {', '.join(args.buckets)}"
              + (f"  (prefix {args.prefix}/)" if args.prefix else ""))
        print(f"  mode    : {mode}")
        if creds:
            print(f"  KEY ID  : {creds['AccessKeyId']}")
            print(f"  SECRET  : {creds['SecretAccessKey']}")
            print("  -> into the app .env + Proton Pass. Shown once.")
        else:
            print("  (no new key minted — see the note above)")
        print("=" * 58 + "\n")
    return 0


def cmd_rotate(args) -> int:
    iam = _admin_client()
    keys = list_keys(iam, args.user)
    if len(keys) >= 2:
        _log(f"user {args.user} already has 2 keys "
             f"({', '.join(k['AccessKeyId'][:3] + '…' for k in keys)}); "
             f"delete the retired one first: --delete <KEY_ID>")
        if not args.delete:
            return 2
    if args.delete:
        iam.delete_access_key(UserName=args.user, AccessKeyId=args.delete)
        _log(f"deleted key {args.delete[:3]}… for {args.user}")
        return 0
    creds = create_key(iam, args.user)
    print(json.dumps({"credentials": creds}, indent=2) if args.output_json else
          f"\nNEW KEY ID : {creds['AccessKeyId']}\nNEW SECRET : {creds['SecretAccessKey']}\n"
          f"deploy + verify, then: rotate --user {args.user} --delete <OLD_KEY_ID>\n")
    return 0


def cmd_whoami(_args) -> int:
    iam = _admin_client()
    try:
        u = iam.get_user()["User"]
        _log(f"admin identity: {u.get('UserName', '(root)')}  arn={u.get('Arn')}")
        return 0
    except ClientError as e:
        _log(f"admin credentials rejected: {e.response['Error']['Code']}")
        return 1


def cmd_list_regions(_args) -> int:
    for r, ep in WASABI_REGIONS.items():
        print(f"{r:<16} {ep}")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    pr = sub.add_parser("provision")
    pr.add_argument("--group", required=True)
    pr.add_argument("--user", required=True)
    pr.add_argument("--buckets", required=True, nargs="+")
    pr.add_argument("--prefix", default=None,
                    help="scope object ops + listing to this key prefix")
    pr.add_argument("--regions", nargs="+", default=None,
                    help="validate bucket regions against the known list (informational)")
    mode = pr.add_mutually_exclusive_group()
    mode.add_argument("--read-only", action="store_true", help="s3:GetObject only")
    mode.add_argument("--no-delete", action="store_true",
                      help="Get + Put, no Delete (the backup role)")
    pr.add_argument("--new-key", action="store_true",
                    help="mint a key even if the user already has one (max 2)")
    pr.add_argument("--output-json", action="store_true")
    pr.set_defaults(func=cmd_provision)

    ro = sub.add_parser("rotate")
    ro.add_argument("--user", required=True)
    ro.add_argument("--delete", metavar="KEY_ID", default=None,
                    help="delete this (retired) key instead of minting one")
    ro.add_argument("--output-json", action="store_true")
    ro.set_defaults(func=cmd_rotate)

    sub.add_parser("whoami").set_defaults(func=cmd_whoami)
    sub.add_parser("list-regions").set_defaults(func=cmd_list_regions)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
