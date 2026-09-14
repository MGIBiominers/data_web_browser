"""get_download_links: presigned S3 URLs for processed data files, across one or more studies."""
from __future__ import annotations

import json
import os
import uuid

from mcp.types import CallToolResult

import resource_links as rl
from catalog_cache import get_catalog
from format import format_label
from s3_clients import default_client, presign_client
from tool_response import build_result


def get_download_links(study_ids: list[str], formats: list[str] | None = None) -> CallToolResult:
    """Get download links for processed data files from one or more studies.

    Handles both single-file and bulk multi-study downloads in one call --
    pass every study_id you want at once rather than calling repeatedly. If
    the total number of eligible files is 5 or fewer, you get the presigned
    URLs directly. If there are more (e.g. requesting several whole
    studies), instead of returning dozens of raw URLs, this writes a single
    manifest file listing them all and returns ONE link to that manifest --
    download it and use its contents to fetch each file. All links are
    valid for 24 hours from when this tool is called.

    Studies that are access-restricted (e.g. dbGaP-controlled) never
    produce a download link -- they get an explicit "restricted" entry
    explaining why, rather than being silently skipped.

    Args:
        study_ids: one or more study_id values.
        formats: optional filter, e.g. ["h5ad"], to skip other formats
            present in the same study. Omit to get every eligible file.

    Returns:
        {"mode": "direct", "files": [{study_id, filename, format, bytes,
        url}, ...]} or {"mode": "manifest", "manifest_url", "file_count",
        "total_bytes"}. Either way, also "excluded": [{study_id, status,
        reason}] for any requested study_id that was restricted or not
        found. Attaches resource links to the format-structure reference(s)
        for whichever formats are actually being downloaded.
    """
    bucket = os.environ["BUCKET_NAME"]
    direct_link_threshold = int(os.environ.get("DOWNLOAD_LINK_MANIFEST_THRESHOLD", "5"))
    presign_ttl_seconds = int(os.environ.get("PRESIGN_TTL_SECONDS", "86400"))
    catalog = get_catalog()
    by_id = {s["study_id"]: s for s in catalog["studies"]}

    eligible_files, excluded = [], []
    for study_id in study_ids:
        study = by_id.get(study_id)
        if study is None:
            excluded.append({"study_id": study_id, "status": "not_found"})
            continue
        if study.get("access_restricted", False):
            excluded.append({
                "study_id": study_id, "status": "restricted",
                "reason": "requires dbGaP application -- not available through this server",
            })
            continue
        for f in study.get("processed_files", []):
            if f.get("category") != "data" or not f.get("s3_key"):
                continue
            fmt = format_label(f["name"])
            if formats and fmt not in formats:
                continue
            eligible_files.append({
                "study_id": study_id, "filename": f["name"], "format": fmt,
                "bytes": f["bytes"], "s3_key": f["s3_key"],
            })

    signer = presign_client()
    for f in eligible_files:
        f["url"] = signer.generate_presigned_url(
            "get_object", Params={"Bucket": bucket, "Key": f.pop("s3_key")},
            ExpiresIn=presign_ttl_seconds,
        )

    links = rl.for_formats({f["format"] for f in eligible_files})

    if len(eligible_files) <= direct_link_threshold:
        result = {"mode": "direct", "files": eligible_files, "excluded": excluded}
        summary = f"{len(eligible_files)} download link(s) ready."
        return build_result(summary, result, extra_content=links)

    manifest_key = f"manifests/{uuid.uuid4().hex}.json"
    default_client().put_object(
        Bucket=bucket, Key=manifest_key,
        Body=json.dumps(eligible_files, indent=2).encode("utf-8"),
        ContentType="application/json",
    )
    manifest_url = signer.generate_presigned_url(
        "get_object", Params={"Bucket": bucket, "Key": manifest_key}, ExpiresIn=presign_ttl_seconds,
    )
    result = {
        "mode": "manifest", "manifest_url": manifest_url,
        "file_count": len(eligible_files),
        "total_bytes": sum(f["bytes"] for f in eligible_files),
        "excluded": excluded,
    }
    summary = f"{len(eligible_files)} files across {len(study_ids)} studies -- manifest link ready."
    return build_result(summary, result, extra_content=links)
