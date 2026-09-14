"""Helpers for participating in the ALS pipeline's existing multi-session
coordination protocol, documented in full at
/lts/rmlab/rmlab_shared3/azamat/als_pipeline_coordination/PROTOCOL.md.

This pipeline registers as a new role, "s3_publish", alongside the existing
download_metadata / conversion / verification / alignment roles. Per the
protocol's ownership rules:
  - CHANGELOG.jsonl is shared and append-only -- anyone may append a line,
    nobody may rewrite an existing one. append_changelog() does exactly
    that, in the documented {ts, session, action, study_id, files, note}
    shape.
  - A role's own *_status.json is owned exclusively by that role.
    write_status() creates/overwrites s3_publish_status.json, which is a
    new file this pipeline owns -- it does not touch any other role's
    status file.

Note: adding "s3_publish" to PROTOCOL.md's role table itself is NOT done
here -- that file is edited only at explicit user request per its own
ownership rule. See DESIGN.md for that open item.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

SESSION_NAME = "s3_publish"


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def append_changelog(coordination_root: Path, action: str, study_id: str | None, files: list[str], note: str) -> None:
    """Append one line to the shared CHANGELOG.jsonl. Never rewrites existing lines."""
    entry = {
        "ts": _now_iso(),
        "session": SESSION_NAME,
        "action": action,
        "study_id": study_id,
        "files": files,
        "note": note,
    }
    path = coordination_root / "CHANGELOG.jsonl"
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")


def write_status(coordination_root: Path, studies: dict[str, dict]) -> None:
    """Overwrite this role's own s3_publish_status.json.

    `studies` maps study_id -> {"phase": ..., "note": ...}, matching the
    shape every other role's status file already uses.
    """
    doc = {
        "session": SESSION_NAME,
        "updated_at": _now_iso(),
        "source_of_seed": (
            "Written by pipeline/publish.py after each sync+catalog-rebuild run."
        ),
        "studies": studies,
    }
    path = coordination_root / "s3_publish_status.json"
    path.write_text(json.dumps(doc, indent=2))
