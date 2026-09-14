"""Python port of web/src/format.js's extension -> friendly-label mapping.
Keep in sync with that file if either changes."""
from __future__ import annotations

_EXTENSION_LABELS = [
    (".h5ad", "h5ad"), (".h5mu", "h5mu"), (".h5", "h5"),
    (".parquet", "parquet"),
    (".tsv.gz", "tsv"), (".tsv", "tsv"),
    (".csv.gz", "csv"), (".csv", "csv"),
    (".loom", "loom"),
    (".mtx.gz", "mtx"), (".mtx", "mtx"),
]


def format_label(filename: str) -> str:
    lower = filename.lower()
    for ext, label in _EXTENSION_LABELS:
        if lower.endswith(ext):
            return label
    return "other"


def strip_known_extension(filename: str) -> str:
    """Strip a recognized (possibly compound, e.g. ".tsv.gz") extension from
    a filename. Falls back to stripping just the last "." segment for an
    unrecognized extension, and returns the filename unchanged if it has no
    extension at all. Naive single-dot splitting alone under-strips compound
    extensions -- "study_counts.tsv.gz".rsplit(".", 1)[0] leaves
    "study_counts.tsv", not "study_counts" -- which matters here since
    .tsv.gz/.csv.gz/.mtx.gz are real formats in this collection.
    """
    lower = filename.lower()
    for ext, _ in _EXTENSION_LABELS:
        if lower.endswith(ext):
            return filename[: -len(ext)]
    return filename.rsplit(".", 1)[0] if "." in filename else filename
