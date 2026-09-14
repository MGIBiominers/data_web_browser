"""get_study_overview: comprehensive per-study metadata, batched."""
from __future__ import annotations

from mcp.types import CallToolResult

import resource_links as rl
from catalog_cache import get_catalog, get_samples
from format import format_label
from tool_response import build_result

HTCF_STUDIES_ROOT = "/lts/rmlab/rmlab_shared3/BioMiners/EXTERNAL_DATASETS/studies"
STUDY_SAMPLE_CAP = 100


def get_study_overview(study_ids: list[str]) -> CallToolResult:
    """Get comprehensive metadata for one or more studies: the full study
    write-up, original source (GEO) series information, the complete
    processed-file inventory, and the samples in that study.

    Call this after search_studies has narrowed down candidates -- pass every
    study_id you're considering in one call rather than one call per study.
    Returns much more than search_studies: the full README write-up (not
    just the short summary), original GEO series titles/summaries/designs
    when sourced from GEO, every processed file with size and format, and
    each sample's key fields.

    For a deep technical explanation of what's actually inside a specific
    processed file (obs columns, QC results, exact conversion steps used),
    use explain_data_file instead -- this tool gives the file's name/size/
    format but not its internal structure or provenance.

    Args:
        study_ids: one or more study_id values (from search_studies or a
            known accession).

    Returns:
        One entry per requested study_id. An unrecognized study_id gets
        status="not_found". A study with access_restricted=true (currently:
        dbGaP-controlled studies) never includes htcf_processed_path -- its
        data isn't available through this server; the description is still
        shown so you know the study exists and why it's gated. `processed_files`
        lists every file this study has been converted to, each with its own
        "downloadable" flag -- a file can exist (has a format/size) without
        being downloadable yet if it hasn't been published to S3 here; check
        available_externally (study-level) or a file's own "downloadable"
        flag before telling someone get_download_links will work for it.
        Sample lists are capped at 100 (see samples_truncated/total_samples)
        -- use search_samples with study_id set for the full set if a study
        has more. Attached resource links point to the format-structure and
        sample-metadata references relevant to the returned studies.
    """
    catalog = get_catalog()
    by_id = {s["study_id"]: s for s in catalog["studies"]}
    samples = get_samples()

    out = []
    formats_seen: set[str] = set()
    any_samples = False
    for study_id in study_ids:
        study = by_id.get(study_id)
        if study is None:
            out.append({"study_id": study_id, "status": "not_found"})
            continue

        study_samples = [s for s in samples if s.get("study_id") == study_id]
        any_samples = any_samples or bool(study_samples)
        data_files = [f for f in study.get("processed_files", []) if f.get("category") == "data"]
        formats_seen.update(format_label(f["name"]) for f in data_files)

        entry = {
            "study_id": study_id,
            "status": "ok",
            "title": study.get("title"),
            "journal": study.get("journal"),
            "year": study.get("year"),
            "doi": study.get("doi"),
            "pmid": study.get("pmid"),
            "accessions": {
                "bioproject": study.get("bioproject"),
                "gse": study.get("gse"),
                "cellxgene_collection": study.get("cellxgene_collection"),
                "synapse": study.get("synapse"),
            },
            "summary": study.get("summary"),
            "readme": study.get("readme_body"),
            "notes": study.get("notes"),
            "original_geo_series": study.get("series_summaries", []),
            "organisms": study.get("organisms", []),
            "disease_statuses": study.get("disease_statuses", []),
            "tissues": study.get("tissues", []),
            "assay_types": study.get("assay_types", []),
            "n_samples": study.get("n_samples"),
            "processed_files": [
                {
                    "name": f["name"], "format": format_label(f["name"]), "bytes": f["bytes"],
                    "downloadable": bool(f.get("s3_key")),
                }
                for f in data_files
            ],
            "available_externally": study.get("available_externally", False),
            "samples": [
                {
                    "sample_id": s.get("sample_id") or s.get("accession"),
                    "disease_status": s.get("disease_status"),
                    "tissue_or_cell_type": s.get("tissue_or_cell_type"),
                    "sex": s.get("sex"),
                    "treatment": s.get("treatment"),
                    "platform": s.get("platform"),
                }
                for s in study_samples[:STUDY_SAMPLE_CAP]
            ],
            "samples_truncated": len(study_samples) > STUDY_SAMPLE_CAP,
            "total_samples": len(study_samples),
            "access_restricted": study.get("access_restricted", False),
        }
        if not study.get("access_restricted", False):
            entry["htcf_processed_path"] = f"{HTCF_STUDIES_ROOT}/{study_id}/processed/"
        out.append(entry)

    links = rl.for_formats(formats_seen)
    if any_samples:
        links = [*links, rl.sample_metadata_link()]
    summary = f"Retrieved overview for {len(study_ids)} study id(s)."
    return build_result(summary, {"studies": out}, extra_content=links)
