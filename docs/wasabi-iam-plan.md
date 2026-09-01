# Wasabi IAM — group / user / key structure (implementation plan)

Companion to [`wasabi_iam_provisioning_architecture.md`](wasabi_iam_provisioning_architecture.md)
(the threat model + reference engine). **This** doc is the right-sized plan
for the actual portfolio: a handful of buckets, one operator, no external
tenants. Same principles, less ceremony.

---

## 1. What we're fixing

One shared **"portfolio" access key** (`MMRUUUU…`, whose *ID* leaked into a
public repo on 2026-09-01) is used by **brasil-archives**,
**media-pipeline-agent**, and **ajme**. It is broad (likely a root-account
key or an unscoped sub-user). Consequences:

- Can't revoke or rotate one project's access without breaking the others.
- Every consumer can read/write/delete every bucket.
- A leak anywhere is a leak everywhere.

Goal: **one scoped credential per workload**, the shared key retired, the
root account locked behind MFA.

---

## 2. Target model

```
Root account ── TOTP MFA only, 0 access keys ── billing + break-glass
    │
    ├── grp-iam-admin ──────── srv-ops-admin      (IAM admin; provisioning only, never in an app config)
    │
    ├── grp-brasil-archives-backup ── srv-brasil-archives-backup   (bucket: brasil-archives, prefix pg/*, no delete)
    ├── grp-media-pipeline-media ──── srv-media-pipeline-connector  (bucket: <mpa media>, full object RW)
    ├── grp-media-pipeline-backup ─── srv-media-pipeline-backup     (if mpa gains a backup bucket/prefix)
    └── grp-ajme-<role> ───────────── srv-ajme-<role>
```

Rules:

- **Group carries the policy.** One group per `(project × access-role)`.
  Service users join a group; they never get inline user policies.
- **One programmatic user per workload.** `srv-<project>-<role>`. No console
  password. Keys live only in that workload's config + Proton Pass.
- **No `s3:ListAllMyBuckets`** on any service user — forces explicit bucket
  targets, blocks lateral discovery. (`srv-ops-admin` is the only identity
  that can enumerate.)
- **Retention is a bucket lifecycle rule, not `DeleteObject`.** Backup-role
  users get Get/Put/List only.

### Naming

| kind | pattern | example |
|---|---|---|
| group | `grp-<project>-<role>` | `grp-brasil-archives-backup` |
| service user | `srv-<project>-<role>` | `srv-brasil-archives-backup` |
| inline group policy | `<group>-policy` | `grp-brasil-archives-backup-policy` |

Roles: **`backup`** (Get/Put/List, no Delete) · **`media`** (Get/Put/Delete)
· **`ro`** (Get/List).

---

## 3. Bucket & workload inventory  *(complete this before Phase 1)*

| bucket | region | project | workload | actions needed | group | service user |
|---|---|---|---|---|---|---|
| `brasil-archives` | us-west-1 | brasil-archives | weekly `pg_dump` cron (`scripts/backup_to_wasabi.py`) | Put/Get/List on `pg/*` | `grp-brasil-archives-backup` | `srv-brasil-archives-backup` |
| `‹mpa media bucket›` | us-west-2 | media-pipeline-agent | connector uploads + gallery signed-URL reads | Get/Put/Delete on `*` | `grp-media-pipeline-media` | `srv-media-pipeline-connector` |
| `‹mpa other?›` | ? | media-pipeline-agent | — | — | — | — |
| `‹ajme bucket›` | us-west-2 | ajme | — | — | `grp-ajme-‹role›` | `srv-ajme-‹role›` |

> Cross-region: IAM policy ARNs (`arn:aws:s3:::bucket`) are region-agnostic
> and authored once at `https://iam.wasabisys.com`. The **S3 client** must
> target the bucket's regional endpoint — `s3.us-west-1.wasabisys.com` for
> `brasil-archives`, `s3.us-west-2.wasabisys.com` for mpa/ajme. Each app
> already reads its endpoint from `WASABI_ENDPOINT_URL` / `WASABI_REGION`.

---

## 4. Policy templates

### 4.1 `backup` role — Get / Put / List, **no Delete**, prefix-scoped

```json
{
  "Version": "2012-10-17",
  "Statement": [
    { "Sid": "ListAndLocate", "Effect": "Allow",
      "Action": ["s3:ListBucket", "s3:GetBucketLocation"],
      "Resource": "arn:aws:s3:::BUCKET",
      "Condition": { "StringLike": { "s3:prefix": ["PREFIX/*", "PREFIX"] } } },
    { "Sid": "ObjectRW", "Effect": "Allow",
      "Action": ["s3:GetObject", "s3:PutObject"],
      "Resource": "arn:aws:s3:::BUCKET/PREFIX/*" }
  ]
}
```

Drop the `Condition` and use `Resource: arn:aws:s3:::BUCKET/*` when the
workload writes the whole bucket rather than one prefix.

### 4.2 `media` role — full object RW

Same as 4.1 minus the prefix condition, plus `"s3:DeleteObject"` in
`ObjectRW`, `Resource: arn:aws:s3:::BUCKET/*`.

### 4.3 `ro` role

`s3:GetObject` + `s3:ListBucket` only.

### 4.4 `grp-iam-admin`

Wasabi managed **`AdministratorAccess`**, or a scoped `iam:*` policy with no
`s3:*`. This group's user (`srv-ops-admin`) runs the provisioner and nothing
else.

---

## 5. Provisioning

The engine in the architecture doc §5 (`wasabi_provisioner.py`) already does
idempotent *group → inline policy → user → membership → key emission*.
**Adopt it**, with two small additions:

- `--prefix PREFIX` — scope the object-level `Resource` to
  `arn:aws:s3:::bucket/PREFIX/*` and add the `s3:prefix` list condition
  (needed for `brasil-archives` → `pg/`).
- `--no-delete` — a third mode between `--read-only` (Get only) and the
  default (Get/Put/Delete): Get + Put, no Delete. This is the `backup` role.

Location: `scripts/ops/wasabi_provisioner.py` in a shared ops/dotfiles repo
(it's portfolio-wide, not brasil-archives-specific). Console steps (§6
Phase 0/1) are an acceptable one-time alternative.

---

## 6. Migration runbook  (zero-downtime, project-by-project)

### Phase 0 — admin identity  *(console, as root)*
1. **Users → Create** `srv-ops-admin`, type *Programmatic*.
2. **Groups → Create** `grp-iam-admin`, attach `AdministratorAccess`.
3. Add `srv-ops-admin` to `grp-iam-admin`.
4. Save its key pair → Proton Pass ("Wasabi — srv-ops-admin"). This pair is
   used only to run the provisioner.

### Phase 1 — provision workload identities
```bash
export WASABI_ADMIN_ACCESS_KEY=<srv-ops-admin id>
export WASABI_ADMIN_SECRET_KEY=<srv-ops-admin secret>
```
Run the provisioner once per row in §3, e.g.:
```bash
python scripts/ops/wasabi_provisioner.py provision \
  --group grp-brasil-archives-backup --user srv-brasil-archives-backup \
  --buckets brasil-archives --prefix pg --no-delete --output-json
```
Save each emitted key pair → Proton Pass (one record per `srv-*` user).

### Phase 2 — cut over, one project at a time
Per project, with the old shared key still active:
1. Swap `WASABI_ACCESS_KEY_ID` / `WASABI_SECRET_ACCESS_KEY` in every config
   that project uses (cPanel `.env`, local `.env`, CI secrets, …).
2. Restart / redeploy.
3. Verify: `python -m scripts.backup_to_wasabi --selftest` for
   brasil-archives; a real test upload + read for mpa/ajme.

### Phase 3 — retire the shared portfolio key
Once **every** project verifies on its scoped key:
- Shared key is a sub-user key → deactivate, watch 24 h, delete.
- Shared key is a **root** key → **Access Keys → delete both** → confirm
  root shows `0` active keys.

### Phase 4 — lock root
Enable **TOTP MFA** on the root user. Root login thereafter is billing +
disaster recovery only.

---

## 7. Rotation  (90-day cadence, per workload)

1. `srv-ops-admin`: `create_access_key` on the target `srv-*` user (its 2nd
   key — Wasabi allows 2).
2. Deploy the new key to that workload's configs; restart; verify.
3. `update_access_key --status Inactive` on the old key. Hold 24–48 h,
   watch the cron log / app logs for auth errors.
4. `delete_access_key` on the old key.

A `rotate --user <name>` subcommand on the provisioner would automate 1, 3,
4.

---

## 8. Secret storage (Proton Pass)

One record per identity, never shared:

| record | used by | goes in a config file? |
|---|---|---|
| Wasabi — srv-ops-admin | you, to run the provisioner | **no** |
| Wasabi — srv-brasil-archives-backup | cPanel + local `.env` | yes |
| Wasabi — srv-media-pipeline-connector | mpa configs | yes |
| Wasabi — root | break-glass only | **no** |

Each record holds: Access Key ID, Secret, group, scoped bucket(s), region +
endpoint, created date, rotation-due date.

---

## 9. Concrete: brasil-archives  *(do this first — it unblocks the current backup work)*

- **Group** `grp-brasil-archives-backup`
- **User** `srv-brasil-archives-backup`
- **Policy** `grp-brasil-archives-backup-policy`:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    { "Sid": "ListAndLocate", "Effect": "Allow",
      "Action": ["s3:ListBucket", "s3:GetBucketLocation"],
      "Resource": "arn:aws:s3:::brasil-archives",
      "Condition": { "StringLike": { "s3:prefix": ["pg/*", "pg/"] } } },
    { "Sid": "ObjectRW", "Effect": "Allow",
      "Action": ["s3:GetObject", "s3:PutObject"],
      "Resource": "arn:aws:s3:::brasil-archives/pg/*" }
  ]
}
```

- New key pair → **cPanel `.env`** + **local `.env`** (`WASABI_ACCESS_KEY_ID`,
  `WASABI_SECRET_ACCESS_KEY`) + **Proton Pass**.
- Verify: `python -m scripts.backup_to_wasabi --selftest`, then one real
  `python -m scripts.backup_to_wasabi` run so a backup exists under the new
  key. (`--selftest` will log that it couldn't delete its probe — expected,
  no Delete; the lifecycle rule expires it.)

---

## 10. Rollout checklist

- [ ] Complete the §3 inventory (mpa + ajme bucket names / regions / needs)
- [ ] Phase 0: `srv-ops-admin` + `grp-iam-admin`
- [ ] `wasabi_provisioner.py` → `scripts/ops/`, add `--prefix` + `--no-delete`
- [ ] **brasil-archives** identity provisioned, cut over, `--selftest` green  ← current work
- [ ] media-pipeline-agent identities provisioned + cut over
- [ ] ajme identity provisioned + cut over
- [ ] shared portfolio key deleted
- [ ] root account: `0` access keys, TOTP MFA enabled
- [ ] Proton Pass record for every identity
- [ ] each backup bucket: lifecycle rule for retention (see `docs/wasabi-backup.md` §6)
