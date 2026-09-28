#!/usr/bin/env python3
"""Scan every study's real processed gene-level data files and build a
gene -> [study_id, ...] presence index -- "does this collection even measure
gene X" (the actual data value in the file, e.g. STMN2 expression, is NOT
read or stored; only whether the gene appears in a file's own gene axis).

Deliberately a SEPARATE script from build_catalog.py, not folded into it:
build_catalog.py only ever reads small text/metadata files (studies.tsv,
all_samples.tsv, README.md); this opens the actual processed data files
(h5ad up to several GB) to read their gene axis. Needs a real scientific-
Python environment with h5py + pyarrow, unlike build_catalog.py which only
needs the stdlib -- use the same env `conversion` already relies on:

    /ref/rmlab/software/azamat/als_pipeline_env/bin/python3 build_gene_presence.py \\
        --root /lts/rmlab/rmlab_shared3/BioMiners/EXTERNAL_DATASETS \\
        --out gene_presence.json

Real, verified findings that shaped this script's design (2026-09-28):
- h5ad files store gene SYMBOLS directly as var_names (checked against
  Zelic2025_Immunity's human and mouse h5ad files) -- used as-is.
- Bulk parquet files are inconsistent: some already have gene symbols as
  column names (e.g. Cho2020_GSE126044 -- 'OR4F5', 'SAMD11', ...), others
  have unversioned Ensembl gene IDs as columns (e.g. Zelic2025_Immunity --
  'ENSG00000284733', ...). Detected per-file by checking whether most
  column names match an Ensembl-gene-ID pattern, not assumed from a fixed
  rule. Only 7 of the real collection's ~50 bulk parquet files have a
  companion `<same-prefix>_gene_symbol_map.tsv` to translate Ensembl IDs;
  the rest, if Ensembl-ID-keyed, are indexed under their raw Ensembl IDs as
  a documented fallback (see `id_type` in the output) rather than silently
  guessing a translation.
- Deliberately excludes non-gene-level feature files by filename pattern --
  transposable-element counts (`_te_`, `_geneTE_`), splice-junction tables
  (`_splicing`), transcript-level quantification (`_transcript_quant`), and
  small-RNA counts (`_smallrna_`). Conflating any of these with plain genes
  would make gene_presence's answer actively wrong, not just incomplete.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import h5py
import pyarrow.parquet as pq

_EXCLUDED_SUBSTRINGS = ("_te_", "_splicing", "_transcript_quant", "_smallrna_", "_genete_")
_GENE_PARQUET_SUFFIXES = ("_counts.parquet", "_normalized.parquet", "_fpkm.parquet", "_tpm.parquet")
_ENSEMBL_PATTERN = re.compile(r"^ENS[A-Z]*G\d+")


def _h5ad_genes(path: Path) -> list[str]:
    """var_names read directly via h5py, not anndata.read_h5ad(backed='r')
    -- confirmed against the real collection that h5py reading only
    /var/_index takes ~0.05s even on a 4.6GB file, while anndata's backed
    mode (which still eagerly reads obs/var) was slow enough over HTCF's
    filesystem to time out a 100s SSH session on the same file."""
    with h5py.File(path, "r") as f:
        idx_name = f["var"].attrs.get("_index", "_index")
        raw = f["var"][idx_name][:]
    return [g.decode("utf-8") if isinstance(g, bytes) else str(g) for g in raw]


def _load_symbol_map(directory: Path, data_filename: str) -> dict[str, str] | None:
    """This file's own companion map, if one exists -- e.g.
    'Zelic2025_Immunity_bulk_GSE287256_counts.parquet' pairs exactly with
    'Zelic2025_Immunity_bulk_GSE287256_gene_symbol_map.tsv'. Matched on the
    full shared prefix (not just study_id), since some studies (e.g.
    SRP566214_dataset) have multiple bulk file groups each with their own
    distinct map."""
    prefix = re.sub(r"_(counts|normalized|fpkm|tpm)\.parquet$", "", data_filename)
    candidate = directory / f"{prefix}_gene_symbol_map.tsv"
    if not candidate.exists():
        return None
    mapping: dict[str, str] = {}
    with candidate.open(encoding="utf-8") as fh:
        next(fh, None)  # header: gene_id\tgene_symbol
        for line in fh:
            parts = line.rstrip("\n").split("\t")
            if len(parts) == 2:
                mapping[parts[0]] = parts[1]
    return mapping


def _parquet_genes(path: Path) -> tuple[list[str], str]:
    """Returns (gene_ids, id_type) -- id_type is "symbol" or "ensembl_id",
    telling the caller which identifier space this particular file's
    entries are actually in."""
    columns = pq.read_schema(path).names
    ensembl_like = sum(1 for c in columns if _ENSEMBL_PATTERN.match(c))
    if ensembl_like < len(columns) / 2:
        return columns, "symbol"

    symbol_map = _load_symbol_map(path.parent, path.name)
    if not symbol_map:
        return columns, "ensembl_id"
    return [symbol_map.get(c, c) for c in columns], "symbol"


def scan(root: Path) -> dict[str, dict[str, list[str]]]:
    """gene -> {"symbol": [study_id, ...], "ensembl_id": [study_id, ...]} --
    study-level and deduplicated, NOT one entry per (gene, file) pair.

    An earlier version of this script kept a {study_id, filename, id_type}
    entry per (gene, file) pair -- real run against the full collection
    (2026-09-28): 513,090 distinct identifiers, 3,031,716 pairs, **512MB**
    of JSON. Completely unusable as a Lambda-cached artifact (the Lambda's
    own memory limit is 512MB total -- a parsed-into-Python-objects copy of
    a 512MB JSON file runs 1.5-2.5x larger than that on its own, before
    anything else the request needs). The redundancy was structural, not a
    bug: a study with 3 h5ad files sharing ~30K common genes was recording
    that gene 3 times for the same study. Collapsing to one
    study_id-per-gene-per-id_type entry (a set, not a list, while scanning)
    removes exactly that redundancy; switching from a list of {3-key dict}
    entries to a plain list of study_id strings removes the second big cost
    (JSON repeating "study_id"/"filename"/"id_type" as literal text
    millions of times). filename is no longer tracked at all -- the review
    only asked for study-level presence ("even a precomputed gene x study
    presence bitmap would do"), and get_data_locations already gives every
    file a study has once you know which study to look at.
    """
    presence: dict[str, dict[str, set[str]]] = {}
    studies_dir = root / "studies"
    for study_dir in sorted(p for p in studies_dir.iterdir() if p.is_dir()):
        processed = study_dir / "processed"
        if not processed.is_dir():
            continue

        # Collected once across this whole study's files, not per file --
        # see the redundancy note above.
        study_genes: dict[str, set[str]] = {"symbol": set(), "ensembl_id": set()}
        for f in sorted(processed.iterdir()):
            name_lower = f.name.lower()
            if f.suffix == ".h5ad":
                genes, id_type = _h5ad_genes(f), "symbol"
            elif (
                f.suffix == ".parquet"
                and name_lower.endswith(_GENE_PARQUET_SUFFIXES)
                and not any(x in name_lower for x in _EXCLUDED_SUBSTRINGS)
            ):
                genes, id_type = _parquet_genes(f)
            else:
                continue
            study_genes[id_type].update(genes)

        for id_type, genes in study_genes.items():
            for g in genes:
                presence.setdefault(g, {}).setdefault(id_type, set()).add(study_dir.name)

    return {
        gene: {id_type: sorted(study_ids) for id_type, study_ids in by_type.items()}
        for gene, by_type in presence.items()
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path, help="EXTERNAL_DATASETS root")
    parser.add_argument("--out", required=True, type=Path, help="Output JSON path")
    args = parser.parse_args()

    presence = scan(args.root)
    files_scanned = sum(1 for entries in presence.values() for _ in entries)
    args.out.write_text(
        json.dumps({"genes": presence}, indent=2, sort_keys=True), encoding="utf-8"
    )
    print(f"Wrote presence for {len(presence)} distinct gene identifiers "
          f"({files_scanned} (gene, file) pairs total) to {args.out}")


if __name__ == "__main__":
    main()
