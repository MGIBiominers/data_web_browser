"""get_data_locations: real HTCF filesystem paths for processed data files, across one or more studies."""
from __future__ import annotations

from mcp.types import CallToolResult

import resource_links as rl
from catalog_cache import get_catalog
from format import format_label
from tool_response import build_result

# Replaces the old get_download_links (removed 2026-09-18) -- this server no
# longer hands out a copy of any file, presigned or otherwise. It only ever
# points to where the data already lives on HTCF, for someone who has
# filesystem access there (a lab member, or a Claude Code session running on
# HTCF) to read it directly. See DESIGN.md's "MCP server reactivated"
# section for why.
#
# Known gap, pre-existing and not introduced by this change: the catalog has
# no per-study "access_restricted" flag today (the one dbGaP-controlled
# study is excluded from S3 sync via a separate mechanism -- see
# pipeline/sources.py's skipped_study_ids -- but that check was never wired
# into catalog.json itself), so this tool can't specifically withhold that
# one study's path. In practice this doesn't grant real access to anything:
# real access is still gated by HTCF's own filesystem permissions, not by
# whether a path string is known.


def get_data_locations(study_ids: list[str], formats: list[str] | None = None) -> CallToolResult:
    """Get the real HTCF filesystem location of processed data files for one
    or more studies. This does NOT download or transfer any file -- it
    tells you where the data already lives on HTCF so you (or a Claude Code
    session with HTCF access) can read/copy it directly from there.

    Pass every study_id you want at once rather than calling repeatedly.

    Args:
        study_ids: one or more study_id values.
        formats: optional filter, e.g. ["h5ad"], to skip other formats
            present in the same study. Omit to get every eligible file.

    Returns:
        {"studies": [{study_id, directory, files: [{filename, format,
        bytes}, ...]}, ...], "excluded": [{study_id, status}]}. "directory"
        is the real HTCF path (`<source_root>/studies/<study_id>/processed/`).
        A requested study_id lands in "excluded" (status="not_found" or
        "no_processed_data") rather than in "studies" if it doesn't exist or
        has no matching processed files yet. Attaches resource links to the
        format-structure reference(s) for whichever formats are present.
    """
    catalog = get_catalog()
    source_root = catalog["source_root"]
    by_id = {s["study_id"]: s for s in catalog["studies"]}

    results: list[dict] = []
    excluded: list[dict] = []
    all_formats: set[str] = set()

    for study_id in study_ids:
        study = by_id.get(study_id)
        if study is None:
            excluded.append({"study_id": study_id, "status": "not_found"})
            continue

        files = []
        for f in study.get("processed_files", []):
            if f.get("category") != "data":
                continue
            fmt = format_label(f["name"])
            if formats and fmt not in formats:
                continue
            files.append({"filename": f["name"], "format": fmt, "bytes": f["bytes"]})
            all_formats.add(fmt)

        if not files:
            excluded.append({"study_id": study_id, "status": "no_processed_data"})
            continue

        results.append({
            "study_id": study_id,
            "directory": f"{source_root}/studies/{study_id}/processed/",
            "files": files,
        })

    links = rl.for_formats(all_formats)
    summary = f"HTCF processed-data location(s) for {len(results)} of {len(study_ids)} requested studies."
    return build_result(summary, {"studies": results, "excluded": excluded}, extra_content=links)
