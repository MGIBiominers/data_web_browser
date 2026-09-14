"""get_sample_details: full raw+normalized detail for specific samples."""
from __future__ import annotations

from mcp.types import CallToolResult

import resource_links as rl
from catalog_cache import get_samples
from tool_response import build_result


def get_sample_details(study_id: str, sample_ids: list[str]) -> CallToolResult:
    """Get complete detail for specific samples within one study, including
    fields search_samples doesn't return.

    search_samples returns a lean, normalized view (one consistent field set
    across the whole collection). This returns everything recorded for each
    requested sample, including source-specific raw fields (the original GEO
    characteristics dict, exact sample title, supplementary file names,
    library strategy/source, instrument model) -- useful once you've found
    specific samples of interest and want the full original record.

    Args:
        study_id: which study these sample_ids belong to.
        sample_ids: sample_id or accession values (from search_samples or
            get_study_overview).

    Returns:
        One entry per requested id, each with both the normalized fields and
        a "raw" sub-object (original source fields, or null if no matching
        raw record exists for that sample). status="not_found" for an id
        that doesn't exist in this study. Attaches a resource link to the
        normalized sample metadata field reference.
    """
    samples = get_samples()
    by_key: dict[str, dict] = {}
    for s in samples:
        if s.get("study_id") != study_id:
            continue
        for key in (s.get("sample_id"), s.get("accession")):
            if key:
                by_key[key] = s

    out = []
    for sample_id in sample_ids:
        s = by_key.get(sample_id)
        out.append({"sample_id": sample_id, "status": "not_found"} if s is None
                    else {"status": "ok", **s})

    summary = f"Retrieved detail for {len(sample_ids)} sample id(s) in {study_id}."
    return build_result(summary, {"samples": out}, extra_content=[rl.sample_metadata_link()])
