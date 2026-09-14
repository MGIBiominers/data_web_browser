"""request_dataset_download: queue a not-yet-collected dataset for a future download/processing pass."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone

import botocore
from mcp.types import CallToolResult

from catalog_cache import get_catalog
from s3_clients import default_client
from tool_response import build_result


def request_dataset_download(identifier: str, notes: str | None = None) -> CallToolResult:
    """Request that a dataset not currently in this collection be downloaded
    and processed in a future pipeline run.

    Checks first whether the dataset is already part of this collection (use
    search_studies/get_study_overview instead if so -- no need to request
    it) and whether it's already been requested by someone else (in which
    case it's already in line, no duplicate is added). Only writes a new
    entry when neither is true. This does not trigger an immediate download
    -- it adds the identifier to a queue a human/pipeline session on HTCF
    reviews and acts on later.

    Args:
        identifier: any accession identifying the dataset -- a GEO series
            (GSE...), BioProject (PRJNA...), DOI, PMID, Synapse ID, or
            CELLxGENE collection ID. Whatever's on hand.
        notes: optional free text -- why this dataset matters, expected
            assay/format, anything useful for prioritizing it.

    Returns:
        status="already_available" (+ study_id) if this collection already
        has it; status="already_tracked_restricted" (+ study_id) if it's
        tracked but access-restricted (e.g. dbGaP); status="already_queued"
        (+ requested_at) if someone already asked for it; status="queued" if
        this is a new request just added.
    """
    norm = identifier.strip().lower()

    for study in get_catalog()["studies"]:
        candidates = [
            study.get("study_id"), study.get("bioproject"), study.get("doi"),
            study.get("pmid"), study.get("cellxgene_collection"), study.get("synapse"),
            *(study.get("gse") or []),
        ]
        if any(c and c.strip().lower() == norm for c in candidates):
            if study.get("access_restricted"):
                result = {
                    "status": "already_tracked_restricted",
                    "study_id": study["study_id"],
                    "message": f"'{identifier}' is already tracked as {study['study_id']}, but it's "
                               f"access-restricted (dbGaP) -- a download request can't change that.",
                }
            else:
                result = {
                    "status": "already_available",
                    "study_id": study["study_id"],
                    "message": f"'{identifier}' is already in this collection as {study['study_id']} -- "
                               f"use get_study_overview to see what's available.",
                }
            return build_result(result["message"], result)

    bucket = os.environ["BUCKET_NAME"]
    queue_key = os.environ.get("DOWNLOAD_QUEUE_KEY", "requests/download_next.json")
    client = default_client()

    for _attempt in range(3):
        try:
            head = client.get_object(Bucket=bucket, Key=queue_key)
            queue = json.loads(head["Body"].read())
            etag = head["ETag"]
        except client.exceptions.NoSuchKey:
            queue, etag = [], None

        existing = next((e for e in queue if e["identifier"].strip().lower() == norm), None)
        if existing:
            result = {
                "status": "already_queued",
                "requested_at": existing["requested_at"],
                "message": f"'{identifier}' was already requested on {existing['requested_at']} -- "
                           f"it's in line for a future download/processing pass.",
            }
            return build_result(result["message"], result)

        queue.append({
            "identifier": identifier, "notes": notes,
            "requested_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        })
        put_kwargs = {
            "Bucket": bucket, "Key": queue_key,
            "Body": json.dumps(queue, indent=2).encode("utf-8"),
            "ContentType": "application/json",
            **({"IfMatch": etag} if etag else {"IfNoneMatch": "*"}),
        }
        try:
            client.put_object(**put_kwargs)
            result = {"status": "queued", "message": f"'{identifier}' has been added to the download queue."}
            return build_result(result["message"], result)
        except botocore.exceptions.ClientError as e:
            if e.response["Error"]["Code"] in ("PreconditionFailed", "412"):
                continue  # someone else wrote concurrently -- retry with fresh state
            raise

    result = {"status": "error", "message": "Could not queue the request after several attempts -- try again."}
    return build_result(result["message"], result)
