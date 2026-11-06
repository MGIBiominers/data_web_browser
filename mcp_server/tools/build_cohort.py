"""build_cohort: matched samples plus exactly which files to open to assemble them."""
from __future__ import annotations

from mcp.types import CallToolResult

import resource_links as rl
from catalog_cache import get_catalog, get_samples
from format import format_label
from locations import get_roots, processed_dirs, roots_note
from sample_filters import matches
from tool_response import build_result


def build_cohort(
    disease_status: str | None = None,
    sex: str | None = None,
    tissue: str | None = None,
    treatment: str | None = None,
    platform: str | None = None,
    genotype: str | None = None,
    study_id: str | None = None,
) -> CallToolResult:
    """Find samples matching the given criteria, and -- unlike
    search_samples -- also resolve exactly which real HTCF processed files
    each matched study's samples live in, so you can go open the right
    files without a separate get_data_locations call.

    Matches against the collection's canonical vocabulary fields
    (disease_status_canonical/tissue/genotype_canonical), not the raw
    disease_status/tissue_or_cell_type/genotype text search_samples matches
    against today -- more reliable, same fields the web app's own filters
    use, and the fields Asano2025-style studies where raw disease_status is
    null but disease_status_canonical is populated actually need.

    Real limitation, stated plainly rather than guessed around: the catalog
    does not record which specific processed file a given sample's data is
    in when a study has more than one "data"-category file (e.g. separate
    human/mouse/tri-culture h5ad files, or several bulk file groups for the
    same study). In that case every one of the study's data files is
    listed, all paired with the same matched sample_ids -- whoever opens a
    file still needs to check its own obs/columns to confirm which one
    actually contains those particular samples. This tool narrows down
    *which study and which files* are worth opening; it doesn't claim to
    resolve sample-to-file assignment the catalog doesn't have.

    Case-insensitive on every field below.

    Args:
        disease_status: matched against disease_status_canonical,
            e.g. "ALS", "Control".
        sex: "male" / "female".
        tissue: matched against the canonical tissue field.
        treatment: matched against the treatment field (not
            canonicalized -- same free-text field search_samples uses).
        platform: sequencing platform/instrument.
        genotype: matched against genotype_canonical, e.g.
            "TARDBP_M337V", "C9orf72 repeat expansion (positive)".
        study_id: restrict to one study (exact match).

    Returns:
        {"total_matched_samples": int, "cohort": [{study_id, directory,
        sample_ids, files: [{filename, format, bytes}, ...]}, ...],
        "excluded_studies": [{study_id, status, sample_count}]}.
        "directories" gives the absolute path on
        each system ("htcf", "ris") -- `<root>/studies/<study_id>/processed/`
        -- and "directory" is the HTCF one (kept for older callers). A study whose
        matched samples have no processed data file yet lands in
        "excluded_studies" (status="no_processed_data") rather than
        "cohort". Attaches resource links to the format-structure
        reference(s) for whichever formats are actually present.
    """
    samples = get_samples()
    matched = [
        s for s in samples
        if (not study_id or s.get("study_id") == study_id)
        and matches(s, disease_status, "disease_status_canonical")
        and matches(s, sex, "sex")
        and matches(s, tissue, "tissue")
        and matches(s, treatment, "treatment")
        and matches(s, platform, "platform")
        and matches(s, genotype, "genotype_canonical")
    ]

    sample_ids_by_study: dict[str, list[str]] = {}
    for s in matched:
        sid = s.get("sample_id") or s.get("accession")
        if sid:
            sample_ids_by_study.setdefault(s["study_id"], []).append(sid)

    catalog = get_catalog()
    roots = get_roots(catalog)
    by_id = {s["study_id"]: s for s in catalog["studies"]}

    cohort: list[dict] = []
    excluded_studies: list[dict] = []
    all_formats: set[str] = set()

    for sid, sample_ids in sample_ids_by_study.items():
        study = by_id.get(sid) or {}
        data_files = [f for f in study.get("processed_files", []) if f.get("category") == "data"]
        if not data_files:
            excluded_studies.append({
                "study_id": sid, "status": "no_processed_data", "sample_count": len(sample_ids),
            })
            continue

        files = []
        for f in data_files:
            fmt = format_label(f["name"])
            files.append({"filename": f["name"], "format": fmt, "bytes": f["bytes"]})
            all_formats.add(fmt)

        dirs = processed_dirs(roots, sid)
        cohort.append({
            "study_id": sid,
            "directories": dirs,
            "directory": dirs["htcf"],
            "sample_ids": sorted(sample_ids),
            "files": files,
        })

    cohort.sort(key=lambda c: c["study_id"])
    links = rl.for_formats(all_formats)
    result = {
        "total_matched_samples": len(matched),
        "roots": roots,
        "note": roots_note(roots),
        "cohort": cohort,
        "excluded_studies": excluded_studies,
    }
    summary = f"{len(matched)} matching sample(s) across {len(cohort)} studies with processed data."
    return build_result(summary, result, extra_content=links)
