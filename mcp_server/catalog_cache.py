"""Lazy, per-object, ETag-gated cache for catalog.json/samples.json.

A head_object check (cheap, no data transfer) runs on every call that needs
an object; the full body is only re-fetched and re-parsed when the ETag
changed since this warm execution environment last saw it -- i.e. right
after a real publish.py run. Relies on publish.py uploading these files via
a plain (non-multipart) call, so ETag is a reliable MD5-based change signal.

Note: samples.json on disk/S3 is a wrapper object,
{"generated_at": ..., "samples": [...]} -- not a bare list (see
pipeline/build_catalog.py's main()). get_samples() unwraps it.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path

import boto3

logger = logging.getLogger(__name__)

_BUCKET = os.environ.get("BUCKET_NAME")
_CATALOG_KEY = os.environ.get("CATALOG_KEY", "metadata/catalog.json")
_SAMPLES_KEY = os.environ.get("SAMPLES_KEY", "metadata/samples.json")
_GENE_PRESENCE_KEY = os.environ.get("GENE_PRESENCE_KEY", "metadata/gene_presence.json")
_LOCAL_SOURCE = os.environ.get("CATALOG_SOURCE") == "local"
_LOCAL_DIR = Path(os.environ.get("CATALOG_LOCAL_DIR", "./fixtures"))

_state: dict[str, object] = {}


def _get_cached(key: str, cache_name: str):
    if _LOCAL_SOURCE:
        return json.loads((_LOCAL_DIR / Path(key).name).read_text(encoding="utf-8"))

    client = boto3.client("s3")
    etag = client.head_object(Bucket=_BUCKET, Key=key)["ETag"]
    if _state.get(f"{cache_name}_etag") != etag:
        body = client.get_object(Bucket=_BUCKET, Key=key)["Body"].read()
        _state[cache_name] = json.loads(body)
        _state[f"{cache_name}_etag"] = etag
        logger.info("catalog_cache: refreshed %s (etag=%s)", cache_name, etag)
    else:
        logger.info("catalog_cache: cache hit for %s", cache_name)
    return _state[cache_name]


def get_catalog() -> dict:
    """Full catalog.json: {"generated_at", "source_root", "studies": [...]}."""
    return _get_cached(_CATALOG_KEY, "catalog")


def get_samples() -> list[dict]:
    """Full sample list (unwraps samples.json's {"samples": [...]} shape)."""
    return _get_cached(_SAMPLES_KEY, "samples")["samples"]


def get_study(study_id: str) -> dict | None:
    for study in get_catalog()["studies"]:
        if study["study_id"] == study_id:
            return study
    return None


def get_gene_presence() -> dict:
    """Full gene_presence.json: {"genes": {symbol: [{study_id, filename,
    id_type}, ...]}} -- built by pipeline/build_gene_presence.py, a
    separate script from build_catalog.py since it needs to open real
    processed data files (h5ad/parquet), not just small metadata.

    Unlike catalog.json/samples.json, this is a newer, optional artifact --
    a bucket with none published yet (or CATALOG_SOURCE=local without a
    fixtures/gene_presence.json) returns an empty index rather than raising,
    so gene_presence's own tool can report "not found" honestly instead of
    the whole server erroring on an unrelated call.
    """
    if _LOCAL_SOURCE:
        path = _LOCAL_DIR / Path(_GENE_PRESENCE_KEY).name
        if not path.exists():
            return {"genes": {}}
        return json.loads(path.read_text(encoding="utf-8"))

    import botocore

    try:
        return _get_cached(_GENE_PRESENCE_KEY, "gene_presence")
    except botocore.exceptions.ClientError as e:
        if e.response.get("Error", {}).get("Code") in ("404", "NoSuchKey"):
            logger.info("catalog_cache: gene_presence.json not published yet")
            return {"genes": {}}
        raise
