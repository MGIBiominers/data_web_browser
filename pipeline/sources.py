"""Readers for EXTERNAL_DATASETS' own native files.

Nothing in this module reads from, or knows about, any other project's
schema (registry.yaml, signatures/, etc.) -- every function here reads
exactly one file format that already exists in the ALS pipeline's
collection, documented in CATALOG.md / schema/metadata_dictionary.md.
"""

from __future__ import annotations

import ast
import csv
import json
import re
from collections import Counter
from pathlib import Path

# Extensions that count as an actual data payload worth publishing, vs.
# sidecar documentation/QC output that's useful context but isn't itself
# a dataset file. Uploaded either way (see s3_sync.py) but tagged so the
# web app can distinguish them.
_DATA_EXTENSIONS = {
    ".h5ad", ".h5mu", ".h5", ".parquet", ".tsv", ".csv",
    ".tsv.gz", ".csv.gz", ".loom", ".mtx", ".mtx.gz",
}
_DOC_EXTENSIONS = {".md"}
_METADATA_EXTENSIONS = {".json"}


def classify_file(name: str) -> str:
    """Return "data" | "doc" | "metadata" | "other" for a filename."""
    lower = name.lower()
    for ext in _DATA_EXTENSIONS:
        if lower.endswith(ext):
            return "data"
    for ext in _DOC_EXTENSIONS:
        if lower.endswith(ext):
            return "doc"
    for ext in _METADATA_EXTENSIONS:
        if lower.endswith(ext):
            return "metadata"
    return "other"


def normalize_organism(value: str | None) -> str | None:
    """Clean up an all_samples.tsv `organism` cell.

    Most rows are already a plain string ("Homo sapiens"). The two
    CELLxGENE-sourced studies (Brain2025_Multiome,
    CrypticExon_ActaNeuropathol2023) instead carry CELLxGENE's raw
    ontology-mapped API response, Python-repr'd into the TSV cell as a
    string like `"[{'label': 'Homo sapiens', 'ontology_term_id':
    'NCBITaxon:9606'}]"` -- confirmed directly in all_samples.tsv,
    2026-09-05. Left as-is, that string renders literally in the UI's
    organism filter. Detect that shape and pull out just the label(s).
    """
    if not value:
        return value
    stripped = value.strip()
    if not stripped.startswith("[{"):
        return value
    try:
        parsed = ast.literal_eval(stripped)
    except (ValueError, SyntaxError):
        return value
    if not isinstance(parsed, list):
        return value
    labels = [entry.get("label") for entry in parsed if isinstance(entry, dict) and entry.get("label")]
    return "; ".join(labels) if labels else value


def load_studies_tsv(root: Path) -> dict[str, dict]:
    """Read studies.tsv -> {study_id: row_dict}."""
    path = root / "studies.tsv"
    out: dict[str, dict] = {}
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh, delimiter="\t")
        for row in reader:
            study_id = (row.get("study_id") or "").strip()
            if not study_id:
                continue
            out[study_id] = row
    return out


def load_all_samples(root: Path) -> list[dict]:
    """Read all_samples.tsv -> list of row dicts, one per sample."""
    path = root / "all_samples.tsv"
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh, delimiter="\t")
        return [dict(row) for row in reader]


def load_build_summary(root: Path) -> list[dict]:
    """Read build_summary.json -> list of {study_id, n_samples, study_dir, status, source}."""
    path = root / "build_summary.json"
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def skipped_study_ids(build_summary: list[dict]) -> set[str]:
    """Studies deliberately excluded from the collection (e.g. dbGaP-controlled).

    Keys on the entry's `status` text starting with "SKIPPED" -- NOT on
    `study_dir` being null, which is a weaker signal than it looks: a real,
    fully-downloaded study (e.g. SRP566214_dataset, status "COMPLETE...")
    can also have a null `study_dir` in this file, apparently just an
    unpopulated field rather than a deliberate exclusion. Confirmed by
    checking build_summary.json directly against studies/ on 2026-09-05:
    of two entries with study_dir=None, only the dbGaP one's status
    actually says SKIPPED.
    """
    return {
        entry["study_id"]
        for entry in build_summary
        if entry.get("study_id") and str(entry.get("status", "")).strip().upper().startswith("SKIPPED")
    }


def load_status_json(coordination_root: Path, filename: str) -> dict:
    """Read one of the coordination dir's *_status.json role files."""
    path = coordination_root / filename
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def get_study_phase(status_doc: dict, study_id: str) -> tuple[str | None, str | None]:
    """Return (phase, note) for a study from a loaded *_status.json doc.

    Handles the "_default_for_unlisted" convention used by every role's
    status file: a study not explicitly listed inherits that string as an
    informational note with no phase, rather than being treated as an
    error.
    """
    studies = status_doc.get("studies", {})
    entry = studies.get(study_id)
    if isinstance(entry, dict):
        return entry.get("phase"), entry.get("note")
    default = studies.get("_default_for_unlisted")
    if isinstance(default, str):
        return None, default
    return None, None


def list_study_ids(root: Path) -> list[str]:
    """List studies/<id> directory names.

    This is the authoritative list of studies that exist -- studies.tsv is
    owned and written by the download_metadata role and can lag behind the
    directories it's already created (observed directly: as of this
    writing studies.tsv has 22 rows while studies/ has 41 directories, all
    with real README.md/samples.json content). Treat a directory with no
    matching studies.tsv row as "metadata not yet backfilled," not as
    "doesn't exist" -- see load_readme_header() for the fallback.
    """
    studies_dir = root / "studies"
    if not studies_dir.is_dir():
        return []
    return sorted(p.name for p in studies_dir.iterdir() if p.is_dir())


def load_readme_header(root: Path, study_id: str) -> dict | None:
    """Best-effort studies.tsv-shaped row parsed from a study's README.md.

    Used only as a fallback when a study directory exists but studies.tsv
    doesn't (yet) have a row for it -- see list_study_ids(). Every field
    name matches studies.tsv's own columns so callers don't need to know
    which source a row came from.
    """
    path = root / "studies" / study_id / "README.md"
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8")

    title_match = re.search(r"^#\s*(.+?)\s*$", text, re.M)
    journal_match = re.search(r"^\*\*Journal:\*\*\s*(.+?)\s*\((.+?)\)\s*$", text, re.M)
    accessions_match = re.search(r"^\*\*Accessions:\*\*\s*(\{.*\})\s*$", text, re.M)
    assay_match = re.search(r"^\*\*Assay types:\*\*\s*(.+?)\s*$", text, re.M)
    route_match = re.search(r"^\*\*Primary data route:\*\*\s*(.+?)\s*$", text, re.M)

    accessions: dict = {}
    if accessions_match:
        try:
            accessions = json.loads(accessions_match.group(1))
        except json.JSONDecodeError:
            accessions = {}

    gse = accessions.get("gse") or []
    if isinstance(gse, str):
        gse = [gse]

    return {
        "study_id": study_id,
        "journal": journal_match.group(1) if journal_match else None,
        "year": journal_match.group(2) if journal_match else None,
        "title": title_match.group(1) if title_match else None,
        "pmid": None,
        "doi": None,
        "bioproject": accessions.get("bioproject"),
        "gse": ";".join(gse) if gse else None,
        "cellxgene_collection": accessions.get("cellxgene"),
        "synapse": accessions.get("synapse"),
        "assay_types": assay_match.group(1) if assay_match else None,
        "primary_route": route_match.group(1) if route_match else None,
        "notes": "Fallback metadata parsed from README.md -- not yet in studies.tsv.",
    }


def _load_readme_section(root: Path, study_id: str, section: str) -> str | None:
    """Extract a "## <section>" body from a study's README.md, if present."""
    path = root / "studies" / study_id / "README.md"
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8")
    match = re.search(rf"^##\s*{re.escape(section)}\s*\n(.+?)(?:\n##\s|\Z)", text, re.S | re.M)
    if not match:
        return None
    return match.group(1).strip()


def load_readme_abstract(root: Path, study_id: str) -> str | None:
    """Extract the "## Abstract" section body from a study's README.md, if present."""
    return _load_readme_section(root, study_id, "Abstract")


def load_readme_summary(root: Path, study_id: str) -> str | None:
    """Extract the "## Summary" section body from a study's README.md, if present.

    This is a short (3-5 sentence), consistently-lengthed plain-language
    summary -- distinct from the paper's own academic Abstract, which
    varies wildly in length/presence across studies and assumes background
    the tool's actual users won't have. Prefer this for display; see
    build_catalog.py's `summary` field, which prefers studies.tsv's own
    `summary` column first and falls back to this only if that's missing.
    """
    return _load_readme_section(root, study_id, "Summary")


def list_processed_files(root: Path, study_id: str) -> list[dict]:
    """List studies/<id>/processed/*, one {name, bytes, category} per file.

    Non-recursive: the collection's own convention keeps processed/ flat
    per study (see CATALOG.md / per-study conversion_log.md).
    """
    processed_dir = root / "studies" / study_id / "processed"
    if not processed_dir.is_dir():
        return []
    out = []
    for entry in sorted(processed_dir.iterdir(), key=lambda p: p.name):
        if not entry.is_file():
            continue
        out.append(
            {
                "name": entry.name,
                "bytes": entry.stat().st_size,
                "category": classify_file(entry.name),
            }
        )
    return out


def split_multi(value: str | None) -> list[str]:
    """Split a ';'-or-','-delimited studies.tsv cell into a clean list.

    Paren-aware: a ',' or ';' *inside* parentheses does not split. Real
    example that motivated this (studies.tsv `assay_types`, 2026-09-06):
    "scRNA-seq (iPSC-MN, ddSEQ + 10x)" is one assay description, not two --
    a naive split on every comma breaks it into "scRNA-seq (iPSC-MN" and
    "ddSEQ + 10x)", an orphaned '(' in one fragment and an orphaned ')' in
    the other.
    """
    if not value:
        return []
    value = value.strip()
    if not value or value.upper() == "NONE":
        return []

    parts = []
    current = []
    depth = 0
    for ch in value:
        if ch == "(":
            depth += 1
            current.append(ch)
        elif ch == ")":
            depth = max(0, depth - 1)
            current.append(ch)
        elif ch in ";," and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(ch)
    parts.append("".join(current))
    return [p.strip() for p in parts if p.strip()]


def dedupe_joined(value: str | None, sep: str = ";") -> str | None:
    """Collapse a `sep`-joined cell where all parts are identical -- e.g.
    all_samples.tsv `tissue_or_cell_type` cells like "Cerebellum; Cerebellum"
    (a real, common pattern in this collection, 2026-09-06) -- down to just
    the one distinct value. Cells with genuinely different parts (e.g.
    "skin; iN") are left untouched.
    """
    if not value:
        return value
    parts = [p.strip() for p in value.split(sep)]
    distinct = list(dict.fromkeys(p for p in parts if p))
    if not distinct:
        return value
    return f"{sep} ".join(distinct)


def build_case_insensitive_canon(values) -> dict[str, str]:
    """Build a {value: canonical_value} map that merges values which differ
    only by letter case (e.g. all_samples.tsv `disease_status` has both
    "Control" and "control", 112 rows each, and "Other Neurological
    Disorders"/"Other Neurological DIsorders" -- the second an outright
    typo that happens to be a pure case variant of the first). The
    canonical form is whichever original casing is most frequent; ties
    break alphabetically for determinism.

    Deliberately generic/mechanical -- this is not a hardcoded disease
    taxonomy, just case-fold dedup. Values that differ by more than casing
    (e.g. "Control" vs "CTL") are left as distinct entries.
    """
    counts: dict[str, Counter] = {}
    raw_by_stripped: dict[str, set] = {}
    for v in values:
        if not v:
            continue
        stripped = v.strip()
        key = stripped.lower()
        counts.setdefault(key, Counter())[stripped] += 1
        raw_by_stripped.setdefault(stripped, set()).add(v)
    canon = {}
    for key, variants in counts.items():
        best = sorted(variants.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
        for variant in variants:
            canon[variant] = best
            # Also map every original (possibly whitespace-padded) raw
            # value seen for this stripped form, so callers don't have to
            # remember to strip before looking a value up.
            for raw in raw_by_stripped.get(variant, ()):
                canon[raw] = best
    return canon


def samples_by_study(samples: list[dict]) -> dict[str, list[dict]]:
    """Group all_samples.tsv rows by study_id."""
    out: dict[str, list[dict]] = {}
    for row in samples:
        study_id = row.get("study_id")
        if not study_id:
            continue
        out.setdefault(study_id, []).append(row)
    return out
