#!/usr/bin/env python3
"""Full publish cycle: sync eligible studies to S3, rebuild the catalog with
the resulting live S3 state, push the refreshed metadata JSON to S3, and
invalidate CloudFront so it's visible immediately.

This is the one script an "upload new data" run actually needs -- it
composes s3_sync.py and build_catalog.py rather than duplicating their
logic, and is the only piece that also talks to the coordination dir (the
other two scripts are read-only with respect to it).

Usage:
    python publish.py \\
        --root /lts/rmlab/rmlab_shared3/BioMiners/EXTERNAL_DATASETS \\
        --coordination-root /lts/rmlab/rmlab_shared3/azamat/als_pipeline_coordination \\
        --bucket my-bucket \\
        --distribution-id EDFDVBD6EXAMPLE \\
        --out-dir ./out \\
        [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import uuid
from pathlib import Path

import build_catalog
import coordination
import s3_sync

try:
    import boto3
except ImportError:
    boto3 = None


def _invalidate(distribution_id: str, paths: list[str]) -> None:
    if boto3 is None:
        raise RuntimeError("boto3 is required for CloudFront invalidation")
    client = boto3.client("cloudfront")
    client.create_invalidation(
        DistributionId=distribution_id,
        InvalidationBatch={
            "Paths": {"Quantity": len(paths), "Items": paths},
            "CallerReference": uuid.uuid4().hex,
        },
    )


def run(
    root: Path,
    coordination_root: Path,
    bucket: str,
    out_dir: Path,
    region: str | None = None,
    distribution_id: str | None = None,
    dry_run: bool = False,
) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1. Sync eligible studies' processed/ files to S3.
    eligible, skipped = s3_sync.eligible_studies(root, coordination_root)
    if boto3 is None and not dry_run:
        raise RuntimeError("boto3 is required to publish (pass --dry-run to skip S3 calls)")

    client = boto3.client("s3", region_name=region) if not dry_run else None

    sync_receipts = []
    if not dry_run:
        for study_id in eligible:
            sync_receipts.append(s3_sync.sync_study(client, root, study_id, bucket, dry_run=False))

    # 2. Rebuild the catalog, folding in the S3 state that now reflects step 1.
    catalog = build_catalog.build(root, coordination_root, bucket=None if dry_run else bucket, region=region)
    (out_dir / "catalog.json").write_text(json.dumps(catalog.to_dict(), indent=2))
    samples = build_catalog.build_sample_records(root)
    samples_doc = {"generated_at": catalog.generated_at, "samples": [s.to_dict() for s in samples]}
    (out_dir / "samples.json").write_text(json.dumps(samples_doc, indent=2))
    last_updated = {
        "timestamp": catalog.generated_at,
        "dry_run": dry_run,
        "n_studies": len(catalog.studies),
        "n_samples": len(samples),
        "n_available_externally": sum(1 for s in catalog.studies if s.available_externally),
        # Studies this run judged eligible -- actually synced to S3 only when
        # dry_run is false; on a dry run these are a preview, not a fact.
        "studies_matched_this_run": eligible,
    }
    (out_dir / "last_updated.json").write_text(json.dumps(last_updated, indent=2))

    # 3. Push the refreshed metadata to S3 and invalidate CloudFront.
    if not dry_run:
        for name in ("catalog.json", "samples.json", "last_updated.json"):
            client.upload_file(str(out_dir / name), bucket, f"metadata/{name}")
        if distribution_id:
            _invalidate(distribution_id, ["/metadata/*"] + [f"/processed/{sid}/*" for sid in eligible])

    # 4. Record this run in the shared coordination dir.
    changed_files = [f"metadata/{n}" for n in ("catalog.json", "samples.json", "last_updated.json")]
    changed_files += [f"processed/{sid}/*" for sid in eligible]
    coordination.append_changelog(
        coordination_root,
        action="published" if not dry_run else "dry_run_published",
        study_id=None,
        files=changed_files,
        note=(
            f"Synced {len(eligible)} studies, skipped {len(skipped)}. "
            f"Catalog now has {len(catalog.studies)} studies, "
            f"{last_updated['n_available_externally']} available externally."
        ),
    )
    # Record every study this run considered, not just the ones that made
    # it -- a study that flips from eligible to skipped between runs (e.g.
    # a re-verification demoted its conversion phase) needs its stale
    # "published" status corrected, not silently left in place.
    #
    # Only do this for a real run: write_status overwrites the shared
    # s3_publish_status.json outright, and a dry run must not claim studies
    # were "published" when nothing actually reached S3 -- a later real run
    # (or another role reading this status) would otherwise wrongly treat
    # them as already done.
    if not dry_run:
        status_studies = {sid: {"phase": "published", "note": None} for sid in eligible}
        status_studies.update({sid: {"phase": "skipped", "note": reason} for sid, reason in skipped.items()})
        coordination.write_status(coordination_root, studies=status_studies)

    return {
        "eligible": eligible,
        "skipped": skipped,
        "sync_receipts": sync_receipts,
        "last_updated": last_updated,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--coordination-root", required=True, type=Path)
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--region", default=None)
    parser.add_argument("--distribution-id", default=None)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    result = run(
        root=args.root,
        coordination_root=args.coordination_root,
        bucket=args.bucket,
        out_dir=args.out_dir,
        region=args.region,
        distribution_id=args.distribution_id,
        dry_run=args.dry_run,
    )

    print(f"Eligible: {len(result['eligible'])}, skipped: {len(result['skipped'])}")
    print(f"Catalog: {result['last_updated']['n_studies']} studies, "
          f"{result['last_updated']['n_available_externally']} available externally")
    if args.dry_run:
        print("[dry-run] no S3 writes or CloudFront invalidation performed")


if __name__ == "__main__":
    main()
