"""search_samples: cross-study sample-level search."""
from __future__ import annotations

from mcp.types import CallToolResult

import resource_links as rl
from catalog_cache import get_samples
from sample_filters import matches
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
    get_data_locations next.

    For full per-sample detail (including raw, non-normalized fields like
    the original GEO characteristics), use get_sample_details on the
    specific samples this returns.

    Case-insensitive on every field below. disease_status and tissue prefer
    each sample's canonical vocabulary value (disease_status_canonical/
    tissue) when populated, falling back to the raw field otherwise -- so
    e.g. tissue="Motor Cortex (BA4)" matches samples recorded under any of
    that region's real raw spelling variants ("motor cortex (BA4)",
    "Cortex_Motor_BA4", etc.), not just one exact string.

    Args:
        disease_status: e.g. "ALS", "Control", "sporadic ALS".
        sex: "male" / "female" (only populated where the source reported it).
        tissue: matched against the canonical tissue field first, then
            tissue_or_cell_type for samples without one (e.g. cell cultures).
        treatment: matched against the treatment field, where recorded.
        platform: sequencing platform/instrument.
        study_id: restrict the search to one study (exact match).

    Returns:
        {"total_matches": int, "truncated": bool, "samples": [...]} -- capped
        at 50 rows even if more match (check total_matches); narrow your
        filters or add study_id if you hit the cap and need more. Attaches
        a resource link to the normalized sample metadata field reference.
    """
    samples = get_samples()
    matched = [
        s for s in samples
        if (not study_id or s.get("study_id") == study_id)
        and matches(s, disease_status, "disease_status_canonical", "disease_status")
        and matches(s, sex, "sex")
        and matches(s, tissue, "tissue", "tissue_or_cell_type")
        and matches(s, treatment, "treatment")
        and matches(s, platform, "platform")
    ]
    result = {
        "total_matches": len(matched),
        "truncated": len(matched) > SAMPLE_RESULT_CAP,
        "samples": matched[:SAMPLE_RESULT_CAP],
    }
    summary = f"Found {result['total_matches']} matching sample(s)."
    return build_result(summary, result, extra_content=[rl.sample_metadata_link()])
