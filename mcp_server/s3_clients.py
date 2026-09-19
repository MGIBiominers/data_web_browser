"""The one boto3 identity this server needs.

Used to be two -- a presigning identity existed only to generate download
URLs for processed files. That whole mechanism (and the long-lived
mcp_presign IAM user + SSM-stored static credentials it depended on) was
removed 2026-09-18 when get_download_links was replaced by
get_data_locations: the server now hands back real HTCF filesystem paths
instead of ever letting someone download a file through it, so there's
nothing left to sign a URL for. See DESIGN.md's "MCP server reactivated"
section.

Passes region_name explicitly (from S3_REGION, set by Terraform -- see
infra/mcp.tf) rather than letting boto3 guess.
"""
from __future__ import annotations

import os

import boto3

# Explicit via Terraform (infra/mcp.tf), not left to Lambda's own AWS_REGION --
# AWS_REGION is documented as always injected, but wasn't reliably observed
# when actually tested end to end against the deployed function.
_REGION = os.environ.get("S3_REGION") or os.environ.get("AWS_REGION")


def default_client():
    """Normal execution-role client: reads metadata/*, reads/writes requests/*."""
    return boto3.client("s3", region_name=_REGION)
