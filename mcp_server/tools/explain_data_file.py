"""explain_data_file: what's actually inside a specific processed file."""
from __future__ import annotations

import os
import re

from mcp.types import CallToolResult

import resource_links as rl
from catalog_cache import get_study
from format import format_label, strip_known_extension
from tool_response import build_result


def explain_data_file(study_id: str, filename: str) -> CallToolResult:
    """Explain what's actually inside a specific processed data file -- its
    format, internal structure, and exactly how it was produced -- so you
    can tell a user what they're getting before they download it.

    Combines three things: (1) a resource link to this collection's general
    schema reference for that file type (obs columns, layers like "raw" and
    "decontx_corrected", what's always present), (2) this specific file's
    own conversion record (source data, filtering/correction applied,
    before/after dimensions, caveats), and (3) this file's automated QC/
    validation results if one was run (cell/gene counts, which obs columns
    are actually present, pass/fail).

    Args:
        study_id: the study this file belongs to.
        filename: exact filename, as returned by search_studies/
            get_study_overview's processed_files list.

    Returns:
        status="not_found" if the study or filename doesn't exist. Otherwise:
        format, conversion_note (this file's own best-effort-extracted
        section of the study's conversion log, or the whole log if a
        specific section couldn't be isolated), and qc (this file's entry
        from the study's validation report, or null if none was run --
        expected for bulk RNA-seq files, which don't go through that check).
        Attaches a resource link to the relevant format-structure reference.
    """
    study = get_study(study_id)
    if study is None:
        result = {"status": "not_found", "reason": "no such study_id"}
        return build_result(result["reason"], result)

    files = {f["name"] for f in study.get("processed_files", []) if f.get("category") == "data"}
    if filename not in files:
        result = {"status": "not_found", "reason": "no such file in this study"}
        return build_result(result["reason"], result)

    fmt = format_label(filename)
    qc = next(
        (
            e for e in study.get("qc_report", [])
            if os.path.basename(str(e.get("path", ""))) == filename
        ),
        None,
    )
    result = {
        "status": "ok",
        "study_id": study_id,
        "filename": filename,
        "format": fmt,
        "conversion_note": _extract_file_section(study.get("conversion_log_raw"), filename),
        "qc": qc,
    }
    links = rl.for_formats({fmt})
    summary = f"{filename} is a {fmt} file."
    return build_result(summary, result, extra_content=links)


def _extract_file_section(conversion_log: str | None, filename: str) -> str | None:
    """conversion_log.md is organized as one section per output file
    (H1/H2 headers). Find the section whose heading or body mentions this
    filename; fall back to the whole log if no single clear match exists --
    an unsplit but complete answer beats a confidently wrong split."""
    if not conversion_log:
        return None
    stem = strip_known_extension(filename)
    sections = re.split(r"\n(?=#{1,2} )", conversion_log)
    matches = [s for s in sections if stem in s or filename in s]
    return matches[0].strip() if len(matches) == 1 else conversion_log
