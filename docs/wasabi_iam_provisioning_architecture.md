# Wasabi Zero-Trust IAM & Multi-Region Key Provisioning Architecture

**Document Version:** 1.0.0  
**Target Audience:** Staff / Senior Systems & Cloud Infrastructure Engineers  
**Scope:** Wasabi Hot Cloud Storage, AWS-Compatible IAM & S3 Protocols, Zero-Root Bootstrap Lifecycle  

---

## 1. Executive Summary & Threat Model

The default operating state of many cloud storage accounts relies on long-lived **Root Account API Keys**. In Wasabi, root keys possess unrestricted superuser privileges:
- Uncontrolled read/write/delete access to all buckets across all storage regions.
- Inability to enforce fine-grained IAM resource-level restrictions.
- Inability to isolate compromised environments or microservices without breaking global operational workflows.

### Objective
1. **Root De-escalation & Quarantine:** Perform a deterministic, zero-downtime bootstrap migration from legacy root access keys to a dedicated, least-privilege `SecurityAdmin` IAM identity.
2. **Permanent Root Key Revocation:** Safely delete all root access keys, locking the root account behind Hardware/TOTP Multi-Factor Authentication (MFA) reserved solely for billing and disaster recovery.
3. **Automated IAM & Multi-Region Provisioning Engine:** Build an idempotent CLI/API engine to dynamically provision scoped User Groups, service sub-users, scoped IAM policies, and region-aware S3 bucket clients.

---

## 2. Global Identity vs. Regional Storage Architecture

Wasabi implements an architectural split between the **Identity Control Plane** and the **Data Storage Plane**:

```
                              ┌─────────────────────────────────────────┐
                              │       Wasabi Root Account (MFA)         │
                              │    (Billing & Break-Glass Recovery)     │
                              └────────────────────┬────────────────────┘
                                                   │
                  ┌────────────────────────────────┴────────────────────────────────┐
                  ▼                                                                 ▼
   Identity Plane (Global)                                          Storage Plane (Regional)
   Endpoint: https://iam.wasabisys.com                              Endpoints: https://s3.<region>.wasabisys.com
   ┌──────────────────────────────────────────────────┐             ┌──────────────────────────────────────────────┐
   │ IAM Groups & Scoped Policies                     │             │ US-East-1 (s3.wasabisys.com)                 │
   │  ├── Group: App-Backups-Prod                     │             │  └── Bucket: prod-backups-us                 │
   │  ├── Group: Media-Transcoding                    │────────────►│                                              │
   │  └── Group: Tenant-Isolated-Storage              │             │ EU-Central-1 (s3.eu-central-1.wasabisys.com) │
   │                                                  │             │  └── Bucket: prod-backups-eu                 │
   │ Sub-Users (Programmatic API Keys Only)           │             │                                              │
   │  ├── srv-backup-prod                             │             │ AP-Northeast-1 (s3.ap-northeast-1...)        │
   │  └── srv-transcoder-01                           │             │  └── Bucket: media-tokyo                     │
   └──────────────────────────────────────────────────┘             └──────────────────────────────────────────────┘
```

### Key Protocol Invariants
1. **IAM Global Consistency:** `https://iam.wasabisys.com` is region-agnostic. All users, groups, inline/managed policies, and access keys are authored and evaluated globally across all buckets regardless of where those buckets reside geographically.
2. **S3 Regional Endpoints:** Data operations (`s3:PutObject`, `s3:GetObject`, `s3:ListBucket`) require targeting the exact regional endpoint where the bucket was created. Using the default US endpoint (`s3.wasabisys.com`) for a European bucket will produce `PermanentRedirect` / `301` routing errors.

---

## 3. Zero-Trust Bootstrap & Root Decommissioning Runbook

To safely revoke root keys without locking yourself out, follow this sequence:

```
[Phase 0: Web Console] ──> Create IAM Admin User + Group (Full IAM Permissions)
                                   │
[Phase 1: Local Creds] ──> Generate & Configure Admin API Key Pair in Local CLI
                                   │
[Phase 2: Validation]  ──> Verify IAM Endpoint Access via Local Script/CLI
                                   │
[Phase 3: Migration]   ──> Provision All Workload Groups, Sub-Users & Policies
                                   │
[Phase 4: Cutover]     ──> Distribute Workload API Keys to Dependent Apps
                                   │
[Phase 5: Revocation]  ──> Delete Both Root Keys via Web Console & Enable Root MFA
```

### Phase Details

#### Step 1: Bootstrap Identity Creation (Wasabi Web Console)
1. Log in to `https://console.wasabisys.com` using root email and password.
2. Navigate to **Users** -> **Create User**:
   - Username: `ops-security-admin`
   - Type: **Programmatic (create API key)**
3. Navigate to **Groups** -> **Create Group**:
   - Group Name: `Security-Administrators`
   - Attach Policy: `AdministratorAccess` (or custom IAM-delegated admin policy).
4. Add `ops-security-admin` to `Security-Administrators`.
5. Securely download the generated API Key and Secret.

#### Step 2: Establish Local Admin Context
Set the bootstrap admin credentials in your execution environment:

```bash
export WASABI_ADMIN_ACCESS_KEY="<OPS_ADMIN_KEY_ID>"
export WASABI_ADMIN_SECRET_KEY="<OPS_ADMIN_SECRET_KEY>"
```

#### Step 3: Run Automation Pipeline
Execute the Python CLI provisioning engine (detailed in Section 5) to construct the target topology.

#### Step 4: Verification & Root Key Destruction
1. Verify that all applications and pipelines can read/write using their dedicated sub-user keys.
2. Log back into the Wasabi Web Console as Root.
3. Navigate to **Access Keys**.
4. Identify the two existing Root Access Keys.
5. Click **Delete** on both keys.
6. Verify under **Users** that root has `0` active access keys.
7. Confirm hardware or TOTP MFA is active on the root user account.

---

## 4. Policy Design Architecture

### 4.1 Strict Bucket Isolation Policy (Cross-Region Compatible)
Allows read/write operations against specific buckets across distinct geographical regions while blocking discovery of unowned buckets.

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowTargetBucketListing",
      "Effect": "Allow",
      "Action": [
        "s3:ListBucket",
        "s3:GetBucketLocation"
      ],
      "Resource": [
        "arn:aws:s3:::prod-backup-us-east",
        "arn:aws:s3:::prod-backup-eu-central"
      ]
    },
    {
      "Sid": "AllowObjectLevelOperations",
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:PutObject",
        "s3:DeleteObject"
      ],
      "Resource": [
        "arn:aws:s3:::prod-backup-us-east/*",
        "arn:aws:s3:::prod-backup-eu-central/*"
      ]
    }
  ]
}
```

### 4.2 Dynamic Prefix/Folder Isolation Policy
Enforces multi-tenancy inside a single shared bucket by leveraging the `${aws:username}` policy variable.

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowListHomeDirectoryOnly",
      "Effect": "Allow",
      "Action": "s3:ListBucket",
      "Resource": "arn:aws:s3:::enterprise-shared-bucket",
      "Condition": {
        "StringLike": {
          "s3:prefix": [
            "home/${aws:username}/*",
            "home/${aws:username}"
          ]
        }
      }
    },
    {
      "Sid": "AllowTenantObjectRW",
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:PutObject",
        "s3:DeleteObject"
      ],
      "Resource": "arn:aws:s3:::enterprise-shared-bucket/home/${aws:username}/*"
    }
  ]
}
```

---

## 5. Production Automation Engine (Python / Boto3)

Below is the production-grade CLI engine `wasabi_provisioner.py`. It implements idempotent creation of groups, dynamic generation of least-privilege IAM policies, creation of programmatic sub-users, group membership assignment, and credential emission.

```python
#!/usr/bin/env python3
"""
Wasabi IAM & Multi-Region Access Provisioning CLI
--------------------------------------------------
Automates zero-trust provisioning across Wasabi regions.
Requires: boto3, botocore
"""

import argparse
import json
import logging
import os
import sys
from typing import Dict, List, Optional
import boto3
from botocore.exceptions import ClientError

# Global IAM Endpoint
WASABI_IAM_ENDPOINT = "https://iam.wasabisys.com"

# Standard Regional S3 Endpoints
WASABI_REGIONS: Dict[str, str] = {
    "us-east-1": "https://s3.wasabisys.com",
    "us-east-2": "https://s3.us-east-2.wasabisys.com",
    "us-central-1": "https://s3.us-central-1.wasabisys.com",
    "us-west-1": "https://s3.us-west-1.wasabisys.com",
    "eu-central-1": "https://s3.eu-central-1.wasabisys.com",
    "eu-west-1": "https://s3.eu-west-1.wasabisys.com",
    "eu-west-2": "https://s3.eu-west-2.wasabisys.com",
    "ap-northeast-1": "https://s3.ap-northeast-1.wasabisys.com",
    "ap-northeast-2": "https://s3.ap-northeast-2.wasabisys.com",
    "ap-southeast-1": "https://s3.ap-southeast-1.wasabisys.com",
    "ap-southeast-2": "https://s3.ap-southeast-2.wasabisys.com",
}

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("wasabi-provisioner")


class WasabiIAMManager:
    def __init__(self, access_key: str, secret_key: str):
        self.iam_client = boto3.client(
            "iam",
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            endpoint_url=WASABI_IAM_ENDPOINT,
            region_name="us-east-1",
        )

    def ensure_group(self, group_name: str) -> bool:
        try:
            self.iam_client.get_group(GroupName=group_name)
            logger.info(f"Group '{group_name}' already exists.")
            return True
        except ClientError as e:
            if e.response["Error"]["Code"] == "NoSuchEntity":
                logger.info(f"Creating group: {group_name}")
                self.iam_client.create_group(GroupName=group_name)
                return True
            logger.error(f"Failed to check/create group {group_name}: {e}")
            raise

    def attach_bucket_policy_to_group(
        self, group_name: str, policy_name: str, bucket_arns: List[str], read_only: bool = False
    ) -> None:
        actions_objects = ["s3:GetObject"] if read_only else ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
        
        policy_document = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Sid": "AllowBucketListingAndLocation",
                    "Effect": "Allow",
                    "Action": ["s3:ListBucket", "s3:GetBucketLocation"],
                    "Resource": bucket_arns,
                },
                {
                    "Sid": "AllowObjectOperations",
                    "Effect": "Allow",
                    "Action": actions_objects,
                    "Resource": [f"{arn}/*" for arn in bucket_arns],
                },
            ],
        }

        logger.info(f"Attaching inline policy '{policy_name}' to group '{group_name}'...")
        self.iam_client.put_group_policy(
            GroupName=group_name,
            PolicyName=policy_name,
            PolicyDocument=json.dumps(policy_document, indent=2),
        )

    def ensure_user(self, user_name: str) -> None:
        try:
            self.iam_client.get_user(UserName=user_name)
            logger.info(f"User '{user_name}' already exists.")
        except ClientError as e:
            if e.response["Error"]["Code"] == "NoSuchEntity":
                logger.info(f"Creating sub-user: {user_name}")
                self.iam_client.create_user(UserName=user_name)
            else:
                logger.error(f"Failed checking/creating user {user_name}: {e}")
                raise

    def add_user_to_group(self, user_name: str, group_name: str) -> None:
        logger.info(f"Adding user '{user_name}' to group '{group_name}'...")
        self.iam_client.add_user_to_group(GroupName=group_name, UserName=user_name)

    def create_api_key(self, user_name: str) -> Dict[str, str]:
        logger.info(f"Generating access key for user: {user_name}")
        response = self.iam_client.create_access_key(UserName=user_name)
        key_data = response["AccessKey"]
        return {
            "UserName": key_data["UserName"],
            "AccessKeyId": key_data["AccessKeyId"],
            "SecretAccessKey": key_data["SecretAccessKey"],
            "Status": key_data["Status"],
        }


def parse_args():
    parser = argparse.ArgumentParser(
        description="Wasabi IAM & Access Key Generation Engine",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Provision command
    prov_parser = subparsers.add_parser("provision", help="Provision group, policy, user and keys")
    prov_parser.add_argument("--group", required=True, help="Target IAM group name")
    prov_parser.add_argument("--user", required=True, help="Target programmatic sub-user name")
    prov_parser.add_argument(
        "--buckets",
        required=True,
        nargs="+",
        help="One or more bucket names (e.g. bucket-us-1 bucket-eu-1)",
    )
    prov_parser.add_argument(
        "--read-only",
        action="store_true",
        help="Restrict policy to Read-Only operations",
    )
    prov_parser.add_argument(
        "--output-json",
        action="store_true",
        help="Output created credentials directly as raw JSON",
    )

    # List regions command
    subparsers.add_parser("list-regions", help="List supported Wasabi S3 regional endpoints")

    return parser.parse_args()


def main():
    args = parse_args()

    if args.command == "list-regions":
        print(f"{'Region Name':<20} | {'S3 Endpoint URL'}")
        print("-" * 65)
        for region, endpoint in WASABI_REGIONS.items():
            print(f"{region:<20} | {endpoint}")
        return

    admin_key = os.getenv("WASABI_ADMIN_ACCESS_KEY")
    admin_secret = os.getenv("WASABI_ADMIN_SECRET_KEY")

    if not admin_key or not admin_secret:
        logger.error("Environment variables WASABI_ADMIN_ACCESS_KEY and WASABI_ADMIN_SECRET_KEY are required.")
        sys.exit(1)

    manager = WasabiIAMManager(access_key=admin_key, secret_key=admin_secret)

    if args.command == "provision":
        group_name = args.group
        user_name = args.user
        bucket_arns = [f"arn:aws:s3:::{b.strip()}" for b in args.buckets]
        policy_name = f"{group_name}-StoragePolicy"

        try:
            # 1. Idempotently establish Group
            manager.ensure_group(group_name)

            # 2. Attach cross-region scoped policy
            manager.attach_bucket_policy_to_group(
                group_name=group_name,
                policy_name=policy_name,
                bucket_arns=bucket_arns,
                read_only=args.read_only,
            )

            # 3. Idempotently establish Sub-User
            manager.ensure_user(user_name)

            # 4. Associate User with Group
            manager.add_user_to_group(user_name, group_name)

            # 5. Issue dedicated API Keys
            credentials = manager.create_api_key(user_name)

            if args.output_json:
                print(json.dumps(credentials, indent=2))
            else:
                print("\n========================================================")
                print("         WASABI SUB-USER CREDENTIALS PROVISIONED       ")
                print("========================================================")
                print(f" User Name       : {credentials['UserName']}")
                print(f" Access Key ID   : {credentials['AccessKeyId']}")
                print(f" Secret Key      : {credentials['SecretAccessKey']}")
                print(" Assigned Group  : " + group_name)
                print(" Scoped Buckets  : " + ", ".join(args.buckets))
                print(" Mode            : " + ("Read-Only" if args.read_only else "Read-Write"))
                print("========================================================\n")
                logger.info("Keep these credentials secure. Secret keys cannot be retrieved again.")

        except Exception as err:
            logger.critical(f"Provisioning failed: {err}")
            sys.exit(1)


if __name__ == "__main__":
    main()
```

---

## 6. Execution & Verification Guide

### 6.1 Executing the Provisioning CLI

Provision a dedicated backup sub-user accessing buckets in both US and EU regions:

```bash
# Set bootstrap credentials
export WASABI_ADMIN_ACCESS_KEY="W4S4B1ADM1NEXAMPLE"
export WASABI_ADMIN_SECRET_KEY="s3cr3tk3yAdminExample123456789"

# Execute provisioning
python3 wasabi_provisioner.py provision \
  --group "App-Backups-Prod" \
  --user "srv-backup-prod" \
  --buckets "prod-backup-us-east" "prod-backup-eu-central"
```

### 6.2 Validating Regional S3 Access with Generated Keys

Test write capability using the generated sub-user keys against specific regional endpoints:

```bash
# 1. Configure the generated sub-user credentials
export AWS_ACCESS_KEY_ID="<GENERATED_ACCESS_KEY_ID>"
export AWS_SECRET_ACCESS_KEY="<GENERATED_SECRET_ACCESS_KEY>"

# 2. Test writing to US-East Bucket (Default Endpoint)
aws s3 cp ./test.log s3://prod-backup-us-east/test.log \
  --endpoint-url=https://s3.wasabisys.com

# 3. Test writing to EU-Central Bucket (Regional Endpoint)
aws s3 cp ./test.log s3://prod-backup-eu-central/test.log \
  --endpoint-url=https://s3.eu-central-1.wasabisys.com

# 4. Verify negative test (Attempting to list unowned bucket must return 403 Access Denied)
aws s3 ls s3://unauthorized-finance-bucket/ \
  --endpoint-url=https://s3.wasabisys.com
```

---

## 7. Security Hardening & Operational Guardrails

1. **Strict Secret Storage:** Pipe `--output-json` directly into your secrets manager (e.g., HashiCorp Vault, AWS Secrets Manager, Doppler, or SOPS-encrypted repositories). Never commit raw keys to version control.
2. **Periodic Key Rotation:** Implement a 90-day rotation cadence:
   - Generate a secondary access key on the sub-user (`iam:CreateAccessKey`).
   - Deploy new key to downstream consumers.
   - Deactivate the legacy key (`iam:UpdateAccessKey --status Inactive`).
   - Delete legacy key (`iam:DeleteAccessKey`).
3. **No `s3:ListAllMyBuckets`:** Never grant `s3:ListAllMyBuckets` to workload service users. Requiring explicit bucket targets prevents lateral discovery across tenants.
