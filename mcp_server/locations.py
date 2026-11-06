"""Absolute data-root prefixes for each system the collection lives on.

The EXTERNAL_DATASETS tree has the same layout on every system, so a path
inside it is `<root>/<relative path>`; only the root differs. The catalog
carries the roots (`catalog["roots"]`, written by pipeline/build_catalog.py);
the defaults below cover catalogs built before that field existed.
"""
from __future__ import annotations

HTCF_ROOT_DEFAULT = "/lts/rmlab/rmlab_shared3/BioMiners/EXTERNAL_DATASETS"
RIS_ROOT_DEFAULT = "/storage3/fs1/rmitra-cajal/Active/EXTERNAL_DATASETS"

SYSTEM_LABELS = {"htcf": "HTCF", "ris": "RIS (Compute2 / Storage3)"}


def get_roots(catalog: dict) -> dict[str, str]:
    """{"htcf": <abs root>, "ris": <abs root>} for this catalog."""
    roots = dict(catalog.get("roots") or {})
    roots.setdefault("htcf", catalog.get("source_root") or HTCF_ROOT_DEFAULT)
    roots.setdefault("ris", RIS_ROOT_DEFAULT)
    return roots


def processed_dirs(roots: dict[str, str], study_id: str) -> dict[str, str]:
    """Absolute processed/ directory of a study on each system."""
    return {
        system: f"{root.rstrip('/')}/studies/{study_id}/processed/"
        for system, root in roots.items()
    }


def roots_note(roots: dict[str, str]) -> str:
    """One-line explanation for a Claude Code session on either system."""
    where = "; ".join(f"{SYSTEM_LABELS.get(k, k)}: {v}" for k, v in roots.items())
    return (
        "The same data lives on both systems with an identical layout below "
        f"the root -- use the root for the system you are on. {where}."
    )
