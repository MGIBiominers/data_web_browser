"""The two boto3 identities this server needs.

A presigned URL signed with Lambda's own execution-role credentials
(temporary STS credentials) expires when that STS session expires --
regardless of the requested ExpiresIn -- typically well under the 24h TTL
download links need. The fix is to sign with a long-lived IAM user's static
access key instead, read once per cold start from SSM Parameter Store
(SecureString) -- never from Terraform state, never baked into the
deployment package as a plain env var.

Both clients pass region_name explicitly (from S3_REGION, set by Terraform --
see infra/mcp.tf) rather than letting boto3 guess.

presign_client() ALSO forces virtual-hosted-style addressing
(Config(s3={"addressing_style": "virtual"})). This is the one that actually
matters and was confirmed the hard way against the real deployed bucket:
generate_presigned_url() never makes a real HTTP request, so there's no
redirect for botocore's own retry logic to silently correct, unlike a real
GetObject/PutObject call (default_client()), which botocore transparently
re-signs and retries on a redirect. Passing region_name alone was NOT enough
-- boto3's default S3 addressing style still produced a presigned URL against
the legacy global `bucket.s3.amazonaws.com` host even with the correct
region_name set, which then 307-redirected to the real regional host and
broke the query-string signature (computed over the original Host, so it
stops matching once the request lands on a different one). Forcing
addressing_style="virtual" makes generate_presigned_url() build the URL
against the correct regional host (`bucket.s3.<region>.amazonaws.com`) up
front, with no redirect at all -- confirmed by actually downloading a real
file through the resulting URL, not just inspecting its shape.
"""
from __future__ import annotations

import json
import os

import boto3
from botocore.config import Config

_presign_client = None
# Explicit via Terraform (infra/mcp.tf), not left to Lambda's own AWS_REGION --
# AWS_REGION is documented as always injected, but wasn't reliably observed
# when actually tested end to end against the deployed function.
_REGION = os.environ.get("S3_REGION") or os.environ.get("AWS_REGION")


def default_client():
    """Normal execution-role client: reads metadata/*, writes manifests/*
    and requests/*."""
    return boto3.client("s3", region_name=_REGION)


def presign_client():
    """Long-lived-credential client, used ONLY for generate_presigned_url."""
    global _presign_client
    if _presign_client is not None:
        return _presign_client
    ssm = boto3.client("ssm", region_name=_REGION)
    param_name = os.environ["PRESIGN_CREDENTIALS_PARAM"]
    creds = json.loads(
        ssm.get_parameter(Name=param_name, WithDecryption=True)["Parameter"]["Value"]
    )
    _presign_client = boto3.client(
        "s3",
        region_name=_REGION,
        config=Config(s3={"addressing_style": "virtual"}),
        aws_access_key_id=creds["access_key_id"],
        aws_secret_access_key=creds["secret_access_key"],
    )
    return _presign_client
