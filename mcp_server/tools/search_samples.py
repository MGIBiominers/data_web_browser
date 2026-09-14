"""search_samples: cross-study sample-level search."""
from __future__ import annotations

from mcp.types import CallToolResult

import resource_links as rl
from catalog_cache import get_samples
from tool_response import build_result

SAMPLE_RESULT_CAP = 50


def search_samples(
    disease_status: str | None = None,
    sex: str | None = None,
    tissue: str | None = None,
    treatment: str | None = None,
    platform: str | None = None,
    study_id: str | None = None,
) -> CallToolResult:
    """Search individual samples across all studies by their own attributes,
    independent of which study they belong to.

    Use this when the criteria that matter are about the sample itself
    (disease status, sex, tissue, treatment, platform) rather than the study
    as a whole -- e.g. "all female sporadic ALS motor-cortex samples" might
    span several studies, and this finds them directly rather than requiring
    you to check each study one at a time. The study_id values in the
    results tell you which studies to pass to get_study_overview or
    get_download_links next.

    For full per-sample detail (including raw, non-normalized fields like
    the original GEO characteristics), use get_sample_details on the
    specific samples this returns.

    Args:
        disease_status: exact match, e.g. "ALS", "Control", "sporadic ALS".
        sex: "male" / "female" (only populated where the source reported it).
        tissue: matched against tissue_or_cell_type.
        treatment: matched against the treatment field, where recorded.
        platform: sequencing platform/instrument.
        study_id: restrict the search to one study.

    Returns:
        {"total_matches": int, "truncated": bool, "samples": [...]} -- capped
        at 50 rows even if more match (check total_matches); narrow your
        filters or add study_id if you hit the cap and need more. Attaches
        a resource link to the normalized sample metadata field reference.
    """
    samples = get_samples()
    matches = [
        s for s in samples
        if (not study_id or s.get("study_id") == study_id)
        and (not disease_status or s.get("disease_status") == disease_status)
        and (not sex or s.get("sex") == sex)
        and (not tissue or s.get("tissue_or_cell_type") == tissue)
        and (not treatment or s.get("treatment") == treatment)
        and (not platform or s.get("platform") == platform)
    ]
    result = {
        "total_matches": len(matches),
        "truncated": len(matches) > SAMPLE_RESULT_CAP,
        "samples": matches[:SAMPLE_RESULT_CAP],
    }
    summary = f"Found {result['total_matches']} matching sample(s)."
    return build_result(summary, result, extra_content=[rl.sample_metadata_link()])
