#!/usr/bin/env python3
"""Sync eligible studies' processed/ files up to S3.

A study is eligible only if ALL of the following hold:
  1. It has a real study_dir (not one of build_summary.json's explicitly
     skipped entries, e.g. the dbGaP-controlled HNSCC study).
  2. Its conversion phase (per conversion_status.json) is "converted" or
     "converted_partial".
  3. Its studies/<id>/processed/ directory actually contains at least one
     "data"-category file (not just doc/metadata sidecars).

Every eligible file is uploaded with its sha256 stored as S3 object
metadata, so re-running this script is idempotent -- unchanged files are
not re-uploaded. Every study's outcome (synced or skipped, and why) is
written to a skip/sync log so a run can be audited without re-deriving it
from S3 state.

Usage:
    python s3_sync.py \\
        --root /lts/rmlab/rmlab_shared3/BioMiners/EXTERNAL_DATASETS \\
        --coordination-root /lts/rmlab/rmlab_shared3/azamat/als_pipeline_coordination \\
        --bucket my-bucket \\
        --out-dir ./out \\
        [--dry-run] [--only STUDY_ID ...]
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import sources

try:
    import boto3
    from botocore.exceptions import ClientError
except ImportError:
    boto3 = None
    ClientError = Exception


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def eligible_studies(root: Path, coordination_root: Path) -> tuple[list[str], dict[str, str]]:
    """Return (eligible_study_ids, {skipped_study_id: reason})."""
    studies_tsv = sources.load_studies_tsv(root)
    dir_ids = sources.list_study_ids(root)
    all_ids = sorted(set(studies_tsv.keys()) | set(dir_ids))

    build_summary = sources.load_build_summary(root)
    hard_skipped = sources.skipped_study_ids(build_summary)

    conversion_status = sources.load_status_json(coordination_root, "conversion_status.json")

    eligible = []
    skipped: dict[str, str] = {}
    for study_id in all_ids:
        if study_id in hard_skipped:
            skipped[study_id] = "explicitly skipped in build_summary.json (no study_dir)"
            continue

        phase, _note = sources.get_study_phase(conversion_status, study_id)
        if phase not in ("converted", "converted_partial"):
            skipped[study_id] = f"conversion phase is {phase!r}, not converted/converted_partial"
            continue

        files = sources.list_processed_files(root, study_id)
        data_files = [f for f in files if f["category"] == "data"]
        if not data_files:
            skipped[study_id] = "processed/ has no 'data'-category files (only docs/metadata, or empty)"
            continue

        eligible.append(study_id)

    return eligible, skipped


def _existing_sha256(client, bucket: str, key: str) -> str | None:
    try:
        head = client.head_object(Bucket=bucket, Key=key)
    except ClientError:
        return None
    return head.get("Metadata", {}).get("sha256")


def sync_study(
    client,
    root: Path,
    study_id: str,
    bucket: str,
    dry_run: bool,
) -> dict:
    """Upload every "data"-category file in processed/ for one study (doc/
    metadata sidecars like conversion_log.md are deliberately left off the
    public bucket). Returns a receipt dict.

    On a dry run, files are listed but never hashed or read -- hashing every
    candidate file's real content (some are many GB) is far too slow to be
    a "preview," and isn't needed just to report what *would* be synced.
    """
    files = [f for f in sources.list_processed_files(root, study_id) if f["category"] == "data"]
    prefix = f"processed/{study_id}/"
    uploaded = []
    skipped_unchanged = []

    for f in files:
        if dry_run:
            uploaded.append({"name": f["name"], "bytes": f["bytes"], "category": f["category"], "sha256": None})
            continue

        local_path = root / "studies" / study_id / "processed" / f["name"]
        key = f"{prefix}{f['name']}"
        sha256 = _sha256_file(local_path)

        existing_sha = _existing_sha256(client, bucket, key)
        if existing_sha == sha256:
            skipped_unchanged.append(f["name"])
            continue
        client.upload_file(
            str(local_path),
            bucket,
            key,
            ExtraArgs={"Metadata": {"sha256": sha256}},
        )
        uploaded.append({"name": f["name"], "bytes": f["bytes"], "category": f["category"], "sha256": sha256})

    return {
        "study_id": study_id,
        "s3_prefix": prefix,
        "uploaded": uploaded,
        "skipped_unchanged": skipped_unchanged,
        "dry_run": dry_run,
        "synced_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--coordination-root", required=True, type=Path)
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--region", default=None)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--only", action="append", default=None, help="Limit to specific study_id(s)")
    args = parser.parse_args()

    if boto3 is None:
        raise SystemExit("boto3 is required to run s3_sync.py; pip install boto3")

    args.out_dir.mkdir(parents=True, exist_ok=True)
    receipts_dir = args.out_dir / "receipts"
    receipts_dir.mkdir(exist_ok=True)

    eligible, skipped = eligible_studies(args.root, args.coordination_root)

    if args.only:
        wanted = set(args.only)
        skipped.update({sid: "not in --only list" for sid in eligible if sid not in wanted})
        eligible = [sid for sid in eligible if sid in wanted]

    client = boto3.client("s3", region_name=args.region)

    receipts = []
    for study_id in eligible:
        receipt = sync_study(client, args.root, study_id, args.bucket, args.dry_run)
        receipts.append(receipt)
        (receipts_dir / f"{study_id}.receipt.json").write_text(json.dumps(receipt, indent=2))
        print(
            f"{study_id}: uploaded {len(receipt['uploaded'])}, "
            f"unchanged {len(receipt['skipped_unchanged'])}"
            + (" [dry-run]" if args.dry_run else "")
        )

    skip_log = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "bucket": args.bucket,
        "eligible_count": len(eligible),
        "skipped_count": len(skipped),
        "skipped": skipped,
    }
    (args.out_dir / "s3_sync_skip_log.json").write_text(json.dumps(skip_log, indent=2))

    print(f"\nSynced {len(eligible)} studies, skipped {len(skipped)}.")
    print(f"Skip log: {args.out_dir / 's3_sync_skip_log.json'}")


if __name__ == "__main__":
    main()
