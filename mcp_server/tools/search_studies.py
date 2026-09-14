"""search_studies: find studies matching filters and/or free-text."""
from __future__ import annotations

from mcp.types import CallToolResult

import resource_links as rl
from catalog_cache import get_catalog
from format import format_label
from tool_response import build_result


def search_studies(
    organism: str | None = None,
    disease_status: str | None = None,
    tissue: str | None = None,
    assay_type: str | None = None,
    query: str | None = None,
) -> CallToolResult:
    """Search the ALS/neurodegeneration dataset catalog for studies matching criteria.

    Use this as the starting point for almost any request -- the fastest way
    to narrow ~40 studies down to a relevant few before pulling full detail
    with get_study_overview. All filters are optional and combine with AND
    logic; omit any you don't need. `query` does a case-insensitive substring
    search across each study's title, summary, journal, notes, assay types,
    disease statuses, tissues, and accessions (GEO/BioProject/DOI/PMID) -- use
    it for natural-language topics ("TDP-43 aggregation", "iPSC motor
    neuron") that don't map cleanly to one of the other filters.

    Args:
        organism: e.g. "Homo sapiens", "Mus musculus".
        disease_status: e.g. "ALS", "Control", "sporadic ALS", "C9orf72".
            Values vary by study -- call with no filters first if unsure
            what's available, and inspect the returned disease_statuses.
        tissue: e.g. "spinal cord", "motor cortex", "iPSC-derived motor neuron".
        assay_type: e.g. "scRNA-seq", "snRNA-seq", "bulk RNA-seq", "snATAC-seq".
        query: free-text search across descriptive fields (see above).

    Returns:
        A list of study summaries (not full detail -- call get_study_overview
        for that): study_id, title, summary, journal, year, primary
        accession, sample count, organisms, disease_statuses, tissues,
        assay_types, access_restricted, and two related-but-different
        fields -- data_formats (which formats this study's data has been
        processed into, e.g. h5ad/parquet, regardless of whether it's been
        published here yet) and available_externally (whether it's actually
        downloadable via get_download_links right now). A non-empty
        data_formats does NOT imply available_externally=true -- check that
        field explicitly before telling someone a study is downloadable.
        Attached resource links point to the format-structure reference(s)
        relevant to the formats present across the returned studies.
    """
    catalog = get_catalog()
    results = []
    for study in catalog["studies"]:
        if organism and organism not in study.get("organisms", []):
            continue
        if disease_status and disease_status not in study.get("disease_statuses", []):
            continue
        if tissue and tissue not in study.get("tissues", []):
            continue
        if assay_type and assay_type not in study.get("assay_types", []):
            continue
        if query:
            haystack = " ".join(str(v) for v in [
                study.get("title"), study.get("summary"), study.get("journal"),
                study.get("notes"), study.get("doi"), study.get("pmid"),
                study.get("bioproject"), " ".join(study.get("gse") or []),
                " ".join(study.get("assay_types") or []),
                " ".join(study.get("disease_statuses") or []),
                " ".join(study.get("tissues") or []),
            ] if v).lower()
            if query.lower() not in haystack:
                continue
        results.append({
            "study_id": study["study_id"],
            "title": study.get("title"),
            "summary": study.get("summary"),
            "journal": study.get("journal"),
            "year": study.get("year"),
            "accession": (study.get("gse") or [None])[0] or study.get("bioproject")
                         or study.get("cellxgene_collection") or study.get("synapse"),
            "n_samples": study.get("n_samples"),
            "organisms": study.get("organisms", []),
            "disease_statuses": study.get("disease_statuses", []),
            "tissues": study.get("tissues", []),
            "assay_types": study.get("assay_types", []),
            "data_formats": sorted({
                format_label(f["name"]) for f in study.get("processed_files", [])
                if f.get("category") == "data"
            }),
            "available_externally": study.get("available_externally", False),
            "access_restricted": study.get("access_restricted", False),
        })

    formats_seen = {fmt for r in results for fmt in r["data_formats"]}
    links = rl.for_formats(formats_seen)
    summary = f"Found {len(results)} matching studies."
    return build_result(summary, {"studies": results}, extra_content=links)
