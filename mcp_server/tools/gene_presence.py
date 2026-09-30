"""gene_presence: which studies actually measure a given gene."""
from __future__ import annotations

from mcp.types import CallToolResult

from catalog_cache import get_gene_presence
from tool_response import build_result


def _lookup(presence: dict, symbol: str) -> dict:
    entry = presence.get("genes", {}).get(symbol, {})
    symbol_studies = entry.get("symbol", [])
    ensembl_studies = entry.get("ensembl_id", [])
    return {
        "present": bool(symbol_studies or ensembl_studies),
        "studies": symbol_studies,
        "ensembl_id_only_studies": ensembl_studies,
    }


def gene_presence(symbol: str | list[str]) -> CallToolResult:
    """Check whether a gene -- or a list of genes -- is actually measured
    anywhere in this collection, and if so, in which studies -- NOT
    expression values, just presence/absence in each study's own gene set.
    Read from a precomputed, study-level index (built by
    pipeline/build_gene_presence.py, which scans every real h5ad/parquet
    file's gene axis directly), not searched live against the actual data
    files.

    A gene's absence here means one of two different things, and this tool
    can't fully distinguish them: either the gene really wasn't captured by
    that study's assay (e.g. a targeted panel with a few thousand genes,
    not full transcriptome -- a real trap in this collection, confirmed
    directly: some files have as few as ~8,000 genes), or -- for some bulk
    RNA-seq studies specifically -- their files use raw Ensembl gene IDs
    with no symbol translation available. If a plain symbol query comes back
    empty, try the same query again with the gene's Ensembl ID -- studies
    only reachable that way show up under "ensembl_id_only_studies", not
    "studies".

    Args:
        symbol: a single gene symbol/Ensembl ID, OR a list of them to check
            in one call (e.g. checking a whole gene panel) -- case-sensitive
            exact match against the index (e.g. "STMN2", "UNC13A",
            "ENSG00000104435"). Mouse gene symbols use their own species'
            casing convention (e.g. mouse "Stmn2", not "STMN2") -- this tool
            does not normalize casing across species.

    Returns:
        Single symbol (a plain string): {"symbol": ..., "present": bool,
        "studies": [study_id, ...], "ensembl_id_only_studies": [study_id,
        ...]}.

        A list of symbols: {"genes": {symbol: {"present": bool, "studies":
        [...], "ensembl_id_only_studies": [...]}, ...}} -- one entry per
        gene in the input list, same per-gene shape as the single-symbol
        case minus the redundant "symbol" key (it's already the dict key).

        In both shapes, "studies" is where the gene was found as a
        confirmed symbol match; "ensembl_id_only_studies" is populated only
        when querying by an actual Ensembl ID that some study's file uses
        without a symbol translation. Both empty (present=false) means the
        exact identifier wasn't found in any indexed study -- try alternate
        casing/species convention or the gene's Ensembl ID before
        concluding it's truly absent.
    """
    presence = get_gene_presence()

    if isinstance(symbol, str):
        lookup = _lookup(presence, symbol)
        result = {"symbol": symbol, **lookup}
        summary = (
            f"'{symbol}' is present in {len(lookup['studies'])} study(ies)." if lookup["studies"]
            else (
                f"'{symbol}' not found as a gene symbol, but present in "
                f"{len(lookup['ensembl_id_only_studies'])} study(ies) under that exact Ensembl ID."
            ) if lookup["ensembl_id_only_studies"]
            else f"'{symbol}' was not found in the gene presence index."
        )
        return build_result(summary, result)

    genes = {sym: _lookup(presence, sym) for sym in symbol}
    found = sum(1 for r in genes.values() if r["present"])
    summary = f"{found}/{len(symbol)} gene(s) found in the collection."
    return build_result(summary, {"genes": genes})
