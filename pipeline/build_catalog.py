#!/usr/bin/env python3
"""Assemble catalog.json + samples.json from EXTERNAL_DATASETS' own files.

Usage:
    python build_catalog.py \\
        --root /lts/rmlab/rmlab_shared3/BioMiners/EXTERNAL_DATASETS \\
        --coordination-root /lts/rmlab/rmlab_shared3/azamat/als_pipeline_coordination \\
        --out-dir ./out

Optionally pass --bucket to fold in the *live* S3 state (which studies are
actually published, from where) instead of leaving `available_externally`
false for everything. Without --bucket this runs with read-only access to
the HTCF collection and no AWS credentials needed at all -- useful for local
testing of the reader/assembly logic on its own.

Nothing here reads from, links to, or otherwise depends on any project
outside EXTERNAL_DATASETS itself.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import sources
from catalog_schema import Catalog, ProcessedFile, RolePhase, SampleRecord, StudyRecord

try:
    import boto3
except ImportError:  # boto3 is only needed when --bucket is passed
    boto3 = None

STATUS_FILES = {
    "download": "download_status.json",
    "conversion": "conversion_status.json",
    "verification": "verification_status.json",
    "alignment": "alignment_status.json",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _live_s3_state(bucket: str | None, region: str | None) -> dict[str, dict]:
    """Return {study_id: {"prefix": ..., "files": {name: {bytes, sha256}}}}
    by listing what's actually under processed/ in the bucket right now.

    This is what makes `available_externally` ground-truth rather than a
    guess based on conversion_status alone. Safe to call unconditionally --
    with no bucket there's nothing to check, so it returns {} rather than
    making the caller decide whether it's meaningful to call.
    """
    if not bucket:
        return {}
    if boto3 is None:
        raise RuntimeError("boto3 is required to use --bucket; pip install boto3")

    client = boto3.client("s3", region_name=region)
    paginator = client.get_paginator("list_objects_v2")
    state: dict[str, dict] = {}
    for page in paginator.paginate(Bucket=bucket, Prefix="processed/"):
        for obj in page.get("Contents", []):
            # key shape: processed/<study_id>/<filename> -- study_id and
            # filename never themselves contain "/" in this collection's
            # convention (processed/ is kept flat per study), but split
            # defensively rather than assuming exactly 3 parts.
            parts = obj["Key"].split("/")
            if len(parts) < 3:
                continue
            study_id = parts[1]
            filename = "/".join(parts[2:])
            if not study_id or not filename:
                continue
            entry = state.setdefault(study_id, {"prefix": f"processed/{study_id}/", "files": {}})
            head = client.head_object(Bucket=bucket, Key=obj["Key"])
            entry["files"][filename] = {
                "bytes": obj["Size"],
                "sha256": head.get("Metadata", {}).get("sha256"),
            }
    return state


def build(
    root: Path,
    coordination_root: Path,
    bucket: str | None = None,
    region: str | None = None,
) -> Catalog:
    studies_tsv = sources.load_studies_tsv(root)
    all_samples = sources.load_all_samples(root)
    grouped_samples = sources.samples_by_study(all_samples)

    # Corpus-wide case-insensitive canonicalization for the two messiest
    # sample fields (verified against the real collection, 2026-09-06):
    # disease_status has e.g. both "Control" and "control" (112 rows each),
    # and tissue_or_cell_type both "Motor cortex" and "motor cortex" --
    # built from ALL samples up front so a value merges consistently no
    # matter which study it's aggregated from. dedupe_joined runs first on
    # tissue values since many are literally "X; X" (the same value
    # repeated) before case-canonicalization ever sees them.
    disease_canon = sources.build_case_insensitive_canon(
        s.get("disease_status") for s in all_samples
    )
    tissue_canon = sources.build_case_insensitive_canon(
        sources.dedupe_joined(s.get("tissue_or_cell_type")) for s in all_samples
    )

    status_docs = {
        role: sources.load_status_json(coordination_root, fname)
        for role, fname in STATUS_FILES.items()
    }

    s3_state = _live_s3_state(bucket, region)

    # studies.tsv is owned and written by the download_metadata role and can
    # lag behind the study directories it's already created -- observed
    # directly against the real collection (studies.tsv had 22 rows while
    # studies/ had 41 directories, all with real README.md content). Treat
    # the directory listing as the authoritative set of studies that exist,
    # falling back to a README.md-derived row for any not yet in the tsv,
    # rather than silently dropping them from the catalog.
    study_ids = sorted(set(studies_tsv.keys()) | set(sources.list_study_ids(root)))

    studies: list[StudyRecord] = []
    for study_id in study_ids:
        row = studies_tsv.get(study_id) or sources.load_readme_header(root, study_id) or {}
        samples = grouped_samples.get(study_id, [])
        organisms = sorted(
            {sources.normalize_organism(s["organism"]) for s in samples if s.get("organism")}
        )
        disease_statuses = sorted(
            {
                disease_canon.get(s["disease_status"], s["disease_status"])
                for s in samples
                if s.get("disease_status")
            }
        )
        tissues = sorted(
            {
                tissue_canon.get(deduped, deduped)
                for s in samples
                if s.get("tissue_or_cell_type")
                for deduped in [sources.dedupe_joined(s["tissue_or_cell_type"])]
            }
        )

        # The four columns below were already canonicalized once, corpus-wide,
        # by the HTCF collection's own vocabulary-normalization pass (see
        # EXTERNAL_DATASETS/vocabulary/CHANGES.md) -- no case-fold/dedup step
        # needed here, just aggregate whatever distinct values a study's
        # samples actually carry.
        disease_statuses_canonical = sorted(
            {s["disease_status_canonical"] for s in samples if s.get("disease_status_canonical")}
        )
        tissues_canonical = sorted({s["tissue"] for s in samples if s.get("tissue")})
        cell_types = sorted({s["cell_type"] for s in samples if s.get("cell_type")})
        genotypes_canonical = sorted(
            {s["genotype_canonical"] for s in samples if s.get("genotype_canonical")}
        )

        local_files = sources.list_processed_files(root, study_id)
        s3_entry = s3_state.get(study_id)
        processed_files = []
        for f in local_files:
            s3_file = (s3_entry or {}).get("files", {}).get(f["name"])
            processed_files.append(
                ProcessedFile(
                    name=f["name"],
                    bytes=f["bytes"],
                    category=f["category"],
                    sha256=(s3_file or {}).get("sha256"),
                    s3_key=f"{s3_entry['prefix']}{f['name']}" if s3_entry and s3_file else None,
                )
            )

        # A study only counts as available externally once EVERY local
        # "data"-category file has a confirmed match in S3 -- not merely
        # because *some* object exists under its prefix. This avoids
        # advertising a study mid-upload (or one where a prior sync failed
        # partway through) as externally accessible.
        local_data_names = {f["name"] for f in local_files if f["category"] == "data"}
        synced_data_names = {
            pf.name for pf in processed_files if pf.category == "data" and pf.s3_key
        }
        available_externally = bool(local_data_names) and local_data_names <= synced_data_names

        roles = {}
        for role in STATUS_FILES:
            phase, note = sources.get_study_phase(status_docs[role], study_id)
            roles[role] = RolePhase(phase=phase, note=note)

        studies.append(
            StudyRecord(
                study_id=study_id,
                journal=row.get("journal") or None,
                year=row.get("year") or None,
                title=row.get("title") or None,
                pmid=row.get("pmid") or None,
                doi=row.get("doi") or None,
                bioproject=row.get("bioproject") or None,
                gse=sources.split_multi(row.get("gse")),
                cellxgene_collection=row.get("cellxgene_collection") or None,
                synapse=row.get("synapse") or None,
                assay_types=sources.split_multi(row.get("assay_types")),
                primary_route=row.get("primary_route") or None,
                notes=row.get("notes") or None,
                # studies.tsv's own `summary` column is the primary source
                # (a consistent, plain-language 3-5 sentence summary, unlike
                # the paper's own Abstract which varies wildly in length and
                # presence); fall back to the README's "## Summary" section
                # only for a study not yet in studies.tsv at all.
                summary=row.get("summary") or sources.load_readme_summary(root, study_id),
                n_samples=len(samples),
                organisms=organisms,
                disease_statuses=disease_statuses,
                tissues=tissues,
                disease_statuses_canonical=disease_statuses_canonical,
                tissues_canonical=tissues_canonical,
                cell_types=cell_types,
                genotypes_canonical=genotypes_canonical,
                abstract=sources.load_readme_abstract(root, study_id),
                download=roles["download"],
                conversion=roles["conversion"],
                verification=roles["verification"],
                alignment=roles["alignment"],
                processed_files=processed_files,
                available_externally=available_externally,
                s3_prefix=(s3_entry or {}).get("prefix"),
            )
        )

    studies.sort(key=lambda s: s.study_id)
    return Catalog(generated_at=_now_iso(), source_root=str(root), studies=studies)


def build_sample_records(root: Path) -> list[SampleRecord]:
    rows = sources.load_all_samples(root)

    # Same corpus-wide normalization as build()'s study-level aggregation
    # (see the comment there) -- built fresh here since this function can
    # be called on its own (e.g. from publish.py) without build() having
    # run first.
    disease_canon = sources.build_case_insensitive_canon(
        r.get("disease_status") for r in rows
    )
    tissue_canon = sources.build_case_insensitive_canon(
        sources.dedupe_joined(r.get("tissue_or_cell_type")) for r in rows
    )

    records = []
    for row in rows:
        tissue = sources.dedupe_joined(row.get("tissue_or_cell_type")) or None
        disease = row.get("disease_status") or None
        records.append(
            SampleRecord(
                study_id=row.get("study_id") or "",
                accession=row.get("accession") or None,
                sample_id=row.get("sample_id") or None,
                assay_type=row.get("assay_type") or None,
                sample_source=row.get("sample_source") or None,
                organism=sources.normalize_organism(row.get("organism")) or None,
                cell_line_or_donor=row.get("cell_line_or_donor") or None,
                genotype=row.get("genotype") or None,
                disease_status=disease_canon.get(disease, disease) if disease else None,
                tissue_or_cell_type=tissue_canon.get(tissue, tissue) if tissue else None,
                timepoint_or_age=row.get("timepoint_or_age") or None,
                treatment=row.get("treatment") or None,
                sex=row.get("sex") or None,
                platform=row.get("platform") or None,
                batch=row.get("batch") or None,
                file_names=row.get("file_names") or None,
                is_filtered=row.get("is_filtered") or None,
                source_doi_or_pmid=row.get("source_doi_or_pmid") or None,
                extra_disease_onset_site=row.get("extra_disease_onset_site") or None,
                extra_chip_antibody=row.get("extra_chip_antibody") or None,
                disease_status_canonical=row.get("disease_status_canonical") or None,
                tissue=row.get("tissue") or None,
                cell_type=row.get("cell_type") or None,
                genotype_canonical=row.get("genotype_canonical") or None,
            )
        )
    return records


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path, help="EXTERNAL_DATASETS root")
    parser.add_argument("--coordination-root", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--bucket", default=None, help="If set, fold in live S3 state")
    parser.add_argument("--region", default=None)
    args = parser.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)

    catalog = build(args.root, args.coordination_root, bucket=args.bucket, region=args.region)
    (args.out_dir / "catalog.json").write_text(json.dumps(catalog.to_dict(), indent=2))

    samples = build_sample_records(args.root)
    samples_doc = {
        "generated_at": catalog.generated_at,
        "samples": [s.to_dict() for s in samples],
    }
    (args.out_dir / "samples.json").write_text(json.dumps(samples_doc, indent=2))

    last_updated = {
        "timestamp": catalog.generated_at,
        "n_studies": len(catalog.studies),
        "n_samples": len(samples),
        "n_available_externally": sum(1 for s in catalog.studies if s.available_externally),
    }
    (args.out_dir / "last_updated.json").write_text(json.dumps(last_updated, indent=2))

    phase_counts = Counter(s.conversion.phase for s in catalog.studies)
    print(f"Wrote catalog for {len(catalog.studies)} studies, {len(samples)} samples "
          f"to {args.out_dir}")
    print(f"Conversion phases: {dict(phase_counts)}")
    print(f"Available externally: {last_updated['n_available_externally']}")


if __name__ == "__main__":
    main()
